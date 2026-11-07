"""Macro picture: latest economic data, upcoming market-moving reports, and world news by theme.

Data comes from FRED (free key), meeting dates from the Federal Reserve, and headlines from
CNBC, MarketWatch, and the Fed. Themes are matched by keywords and linked to the portfolio's
sectors; the links describe where a theme usually matters, not a prediction.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from app.macro_repository import MacroRepository
from app.news_repository import NewsRepository
from app.providers.fred import FredNotConfiguredError
from app.services.news import item_id, score_pending
from app.services.sentiment import Scorer, label_for, net_score

MACRO_KEY = "@MACRO"  # never a valid ticker, so macro news can't mix with a stock's news
SERIES_TTL = timedelta(hours=6)
CALENDAR_TTL = timedelta(hours=12)
NEWS_TTL = timedelta(minutes=30)
CALENDAR_DAYS = 45
NEWS_DAYS = 7
MAX_HEADLINES = 60

logger = logging.getLogger("investment_tracker.macro")


@dataclass(frozen=True)
class Indicator:
    key: str
    label: str
    series: str
    transform: str  # level | yoy | change | mom_pct
    unit: str  # % | K | $ | pts | index
    frequency: str  # daily | weekly | monthly | quarterly
    group: str
    note: str = ""


INDICATORS: tuple[Indicator, ...] = (
    Indicator("unemployment", "Unemployment rate", "UNRATE", "level", "%", "monthly", "Jobs"),
    Indicator(
        "payrolls", "Nonfarm payrolls", "PAYEMS", "change", "K", "monthly", "Jobs", "Jobs added in the month"
    ),
    Indicator("claims", "Initial jobless claims", "ICSA", "level", "K", "weekly", "Jobs"),
    Indicator("cpi", "CPI inflation", "CPIAUCSL", "yoy", "%", "monthly", "Inflation", "Year over year"),
    Indicator(
        "core_cpi", "Core CPI", "CPILFESL", "yoy", "%", "monthly", "Inflation", "Excludes food and energy"
    ),
    Indicator(
        "core_pce", "Core PCE", "PCEPILFE", "yoy", "%", "monthly", "Inflation", "The Fed's preferred gauge"
    ),
    Indicator("fed_funds", "Fed funds target (upper)", "DFEDTARU", "level", "%", "daily", "Rates"),
    Indicator("two_year", "2-year Treasury yield", "DGS2", "level", "%", "daily", "Rates"),
    Indicator("ten_year", "10-year Treasury yield", "DGS10", "level", "%", "daily", "Rates"),
    Indicator(
        "curve", "10-year minus 2-year", "T10Y2Y", "level", "pts", "daily", "Rates", "Below 0 means inverted"
    ),
    Indicator("gdp", "Real GDP growth", "A191RL1Q225SBEA", "level", "%", "quarterly", "Growth", "Annualized"),
    Indicator("retail", "Retail sales", "RSAFS", "mom_pct", "%", "monthly", "Growth", "Month over month"),
    Indicator(
        "sentiment", "Consumer sentiment", "UMCSENT", "level", "index", "monthly", "Growth", "U. of Michigan"
    ),
    Indicator("oil", "WTI crude oil", "DCOILWTICO", "level", "$", "daily", "Energy", "Per barrel"),
)

# FRED release IDs for the reports that move markets most.
RELEASES: tuple[tuple[int, str, str, str], ...] = (
    (50, "Jobs report", "high", "Payrolls and the unemployment rate"),
    (10, "CPI inflation", "high", "Consumer prices"),
    (54, "PCE inflation and spending", "high", "The Fed's preferred inflation gauge"),
    (53, "GDP", "high", "Economic growth"),
    (46, "PPI inflation", "medium", "Producer prices"),
    (9, "Retail sales", "medium", "Consumer spending"),
    (192, "JOLTS job openings", "medium", "Labor demand"),
    (180, "Weekly jobless claims", "medium", "Layoffs, every Thursday"),
    (91, "Consumer sentiment", "low", "University of Michigan survey"),
    (13, "Industrial production", "low", "Factory output"),
)

THEMES: tuple[tuple[str, str, tuple[str, ...], tuple[str, ...]], ...] = (
    (
        "rates",
        "Fed and rates",
        (
            r"\bfed\b",
            r"fomc",
            r"powell",
            r"rate cuts?",
            r"rate hikes?",
            r"interest rates?",
            r"yields?",
            r"treasur(y|ies)",
            r"\bbonds?\b",
            r"central bank",
        ),
        ("Financials", "Real Estate", "Utilities", "Information Technology"),
    ),
    (
        "inflation",
        "Inflation",
        (r"inflation", r"\bcpi\b", r"\bpce\b", r"\bppi\b", r"consumer prices", r"price (increases|hikes)"),
        ("Consumer Staples", "Consumer Discretionary", "Materials"),
    ),
    (
        "jobs",
        "Jobs",
        (r"\bjobs?\b", r"payrolls?", r"unemployment", r"jobless", r"labor market", r"hiring", r"layoffs?"),
        ("Consumer Discretionary", "Industrials"),
    ),
    (
        "trade",
        "Trade and tariffs",
        (r"tariffs?", r"trade (war|deal|talks|deficit)", r"\bimports?\b", r"\bexports?\b", r"customs duties"),
        ("Industrials", "Materials", "Information Technology", "Consumer Discretionary"),
    ),
    (
        "geopolitics",
        "War and geopolitics",
        (
            r"\bwar\b",
            r"military",
            r"missiles?",
            r"strikes? on",
            r"invasion",
            r"ukraine",
            r"russia",
            r"israel",
            r"\biran\b",
            r"gaza",
            r"ceasefire",
            r"\bnato\b",
            r"sanctions?",
            r"troops",
            r"conflict",
            r"taiwan",
        ),
        ("Energy", "Industrials"),
    ),
    (
        "energy",
        "Energy and oil",
        (r"\boil\b", r"crude", r"\bopec", r"natural gas", r"gasoline", r"gas prices", r"energy prices"),
        ("Energy", "Materials", "Industrials"),
    ),
    (
        "china",
        "China",
        (r"china", r"chinese", r"beijing", r"\bxi\b", r"yuan"),
        ("Information Technology", "Materials", "Consumer Discretionary"),
    ),
    (
        "growth",
        "Growth and recession",
        (
            r"\bgdp\b",
            r"recession",
            r"economic growth",
            r"slowdown",
            r"consumer spending",
            r"retail sales",
            r"\beconomy\b",
            r"soft landing",
        ),
        ("Consumer Discretionary", "Industrials", "Financials"),
    ),
    (
        "policy",
        "Government and policy",
        (
            r"shutdown",
            r"congress",
            r"senate",
            r"white house",
            r"election",
            r"debt ceiling",
            r"budget",
            r"tax (cuts?|bill|plan)",
            r"supreme court",
        ),
        ("Health Care", "Financials", "Industrials"),
    ),
)
_THEME_PATTERNS = [(key, re.compile("|".join(words), re.IGNORECASE)) for key, _, words, _ in THEMES]


def themes_for(title: str) -> list[str]:
    return [key for key, pattern in _THEME_PATTERNS if pattern.search(title)]


def _shift_months(day: date, months: int) -> date:
    month_index = day.year * 12 + day.month - 1 - months
    return date(month_index // 12, month_index % 12 + 1, 1)


def summarize(indicator: Indicator, observations: list[tuple[str, float]]) -> dict[str, Any]:
    """Latest value, the comparison value, and their dates, after the indicator's transform."""
    base = {
        "key": indicator.key,
        "label": indicator.label,
        "unit": indicator.unit,
        "group": indicator.group,
        "frequency": indicator.frequency,
        "note": indicator.note,
        "series": indicator.series,
    }
    values = observations
    if indicator.transform == "yoy":
        by_date = dict(observations)
        values = []
        for day, value in observations:
            prior = by_date.get(_shift_months(date.fromisoformat(day), 12).isoformat())
            if prior:
                values.append((day, round((value / prior - 1) * 100, 2)))
    elif indicator.transform == "change":
        values = [
            (observations[i][0], round(observations[i][1] - observations[i - 1][1], 1))
            for i in range(1, len(observations))
        ]
    elif indicator.transform == "mom_pct":
        values = [
            (observations[i][0], round((observations[i][1] / observations[i - 1][1] - 1) * 100, 2))
            for i in range(1, len(observations))
            if observations[i - 1][1]
        ]
    if indicator.unit == "K" and indicator.transform == "level":
        values = [(day, round(value / 1000, 1)) for day, value in values]
    if not values:
        return {**base, "available": False, "reason": "No observations returned"}
    latest_day, latest = values[-1]
    if indicator.frequency == "daily":
        # Day-to-day moves are noise; compare with about a month earlier.
        cutoff = (date.fromisoformat(latest_day) - timedelta(days=30)).isoformat()
        earlier = [row for row in values if row[0] <= cutoff]
        previous = earlier[-1] if earlier else (values[-2] if len(values) > 1 else None)
        compared = "about a month earlier"
    else:
        previous = values[-2] if len(values) > 1 else None
        compared = "previous release"
    return {
        **base,
        "available": True,
        "value": latest,
        "as_of": latest_day,
        "previous": previous[1] if previous else None,
        "previous_as_of": previous[0] if previous else None,
        "change": round(latest - previous[1], 2) if previous else None,
        "compared_with": compared,
        "history": [value for _, value in values[-24:]],
    }


class MacroService:
    def __init__(
        self,
        repository: MacroRepository,
        news_repository: NewsRepository,
        *,
        fred: Any,
        fed_calendar: Any,
        news: Any,
        scorer: Scorer | None = None,
        portfolio_repository: Any = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.news_repository = news_repository
        self.fred = fred
        self.fed_calendar = fed_calendar
        self.news = news
        self.scorer = scorer
        self.portfolio_repository = portfolio_repository
        self.clock = clock or (lambda: datetime.now(UTC))

    def _cached(self, key: str, ttl: timedelta, loader: Callable[[], Any]) -> tuple[Any, str, bool]:
        """(payload, fetched_at, stale). A failed refresh falls back to the saved copy."""
        now = self.clock()
        saved = self.repository.get(key)
        if saved and now - datetime.fromisoformat(saved[1]) <= ttl:
            return saved[0], saved[1], False
        try:
            payload = loader()
        except FredNotConfiguredError:
            raise
        except Exception:
            if saved:
                return saved[0], saved[1], True
            raise
        fetched_at = now.isoformat(timespec="seconds")
        self.repository.put(key, payload, fetched_at)
        return payload, fetched_at, False

    def indicators(self) -> dict[str, Any]:
        start = self.clock().date() - timedelta(days=3 * 365)

        def load(indicator: Indicator) -> dict[str, Any]:
            try:
                observations, fetched_at, stale = self._cached(
                    f"series:{indicator.series}",
                    SERIES_TTL,
                    lambda: self.fred.observations(indicator.series, start),
                )
            except FredNotConfiguredError:
                raise
            except Exception as exc:
                return {
                    "key": indicator.key,
                    "label": indicator.label,
                    "unit": indicator.unit,
                    "group": indicator.group,
                    "available": False,
                    "reason": str(exc),
                }
            return {
                **summarize(indicator, [tuple(row) for row in observations]),
                "fetched_at": fetched_at,
                "stale": stale,
            }

        with ThreadPoolExecutor(max_workers=6) as pool:
            rows = list(pool.map(load, INDICATORS))
        return {"items": rows, "source": "FRED, Federal Reserve Bank of St. Louis"}

    def calendar(self, days: int = CALENDAR_DAYS) -> dict[str, Any]:
        today = self.clock().date()
        end = (today + timedelta(days=days)).isoformat()
        events: list[dict[str, Any]] = []
        warnings: list[str] = []

        def load(release: tuple[int, str, str, str]) -> list[dict[str, Any]]:
            release_id, name, impact, detail = release
            dates, _, _ = self._cached(
                f"release:{release_id}:{today.isoformat()}",
                CALENDAR_TTL,
                lambda: self.fred.release_dates(release_id, today),
            )
            upcoming = [day for day in dates if today.isoformat() <= day <= end]
            # Weekly reports would crowd the list, so show only the next one.
            if release_id == 180:
                upcoming = upcoming[:1]
            return [
                {"date": day, "name": name, "impact": impact, "detail": detail, "source": "FRED"}
                for day in upcoming
            ]

        unavailable: str | None = None
        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = [(release[1], pool.submit(load, release)) for release in RELEASES]
            for name, future in futures:
                try:
                    events.extend(future.result())
                except FredNotConfiguredError as exc:
                    unavailable = str(exc)
                except Exception as exc:
                    warnings.append(f"{name}: {exc}")
        try:
            meetings, _, _ = self._cached("fomc", CALENDAR_TTL, self.fed_calendar.fomc_meetings)
            for meeting in meetings:
                if today.isoformat() <= meeting["end"] <= end:
                    detail = "Rate decision" + (
                        " with economic projections" if meeting["projections"] else ""
                    )
                    events.append(
                        {
                            "date": meeting["end"],
                            "name": "Fed rate decision (FOMC)",
                            "impact": "high",
                            "detail": detail,
                            "source": "Federal Reserve",
                        }
                    )
        except Exception as exc:
            warnings.append(f"FOMC calendar: {type(exc).__name__}")
        events.sort(key=lambda row: (row["date"], {"high": 0, "medium": 1, "low": 2}[row["impact"]]))
        return {"events": events, "days": days, "warnings": warnings, "unavailable": unavailable}

    def _exposure(self) -> dict[str, list[dict[str, Any]]]:
        """Holdings per sector, so each theme can name the positions it usually touches."""
        if self.portfolio_repository is None:
            return {}
        portfolio = self.portfolio_repository.latest_portfolio()
        by_sector: dict[str, list[dict[str, Any]]] = {}
        for holding in (portfolio or {}).get("holdings", []):
            sector = holding.get("manual_sector")
            if holding["asset_type"] != "STOCK" or not sector:
                continue
            weight = float(holding["portfolio_weight"]) if holding.get("portfolio_weight") else None
            by_sector.setdefault(sector, []).append({"symbol": holding["canonical_symbol"], "weight": weight})
        return by_sector

    def headlines(self) -> dict[str, Any]:
        now = self.clock()
        last = self.news_repository.last_fetch(MACRO_KEY)
        if last is None or now - datetime.fromisoformat(last["fetched_at"]) > NEWS_TTL:
            failures: dict[str, str] = {}
            items: list[dict[str, Any]] = []
            try:
                fetched = self.news.headlines()
                failures.update(fetched.get("failures") or {})
                for item in fetched["items"]:
                    if themes_for(item["title"]):
                        items.append({**item, "id": item_id(MACRO_KEY, item["url"]), "kind": "HEADLINE"})
            except Exception as exc:
                failures["headlines"] = f"{type(exc).__name__}: {exc}"
            self.news_repository.save_items(MACRO_KEY, items, failures, now.isoformat(timespec="seconds"))
            last = self.news_repository.last_fetch(MACRO_KEY)
        failures = (last or {}).get("failures", {})
        since = (now - timedelta(days=NEWS_DAYS)).isoformat(timespec="seconds")
        rows = self.news_repository.items(MACRO_KEY, since)
        issue = score_pending(self.news_repository, self.scorer, rows)
        if issue is None:
            rows = self.news_repository.items(MACRO_KEY, since)

        headlines = []
        for row in rows[:MAX_HEADLINES]:
            scored = row["scored_at"] is not None
            probabilities = {
                "positive": row["positive"],
                "neutral": row["neutral"],
                "negative": row["negative"],
            }
            headlines.append(
                {
                    "id": row["id"],
                    "title": row["title"],
                    "summary": row["summary"],
                    "url": row["url"],
                    "publisher": row["publisher"],
                    "published_at": row["published_at"],
                    "themes": themes_for(row["title"]),
                    "sentiment": {"label": label_for(probabilities), "net": net_score(probabilities)}
                    if scored
                    else None,
                }
            )

        exposure = self._exposure()
        day_ago = (now - timedelta(days=1)).isoformat(timespec="seconds")
        themes = []
        for key, label, _, sectors in THEMES:
            matching = [row for row in headlines if key in row["themes"]]
            scored = [row["sentiment"]["net"] for row in matching if row["sentiment"]]
            holdings = sorted(
                (holding for sector in sectors for holding in exposure.get(sector, [])),
                key=lambda row: -(row["weight"] or 0),
            )
            themes.append(
                {
                    "key": key,
                    "label": label,
                    "count": len(matching),
                    "last_day": sum(row["published_at"] >= day_ago for row in matching),
                    "net": round(sum(scored) / len(scored), 3) if scored else None,
                    "sectors": list(sectors),
                    "holdings": holdings,
                    "holdings_weight": round(sum(row["weight"] or 0 for row in holdings), 4)
                    if holdings
                    else None,
                }
            )
        themes.sort(key=lambda row: -row["count"])
        return {
            "headlines": headlines,
            "themes": themes,
            "days": NEWS_DAYS,
            "sentiment_reason": issue,
            "fetched_at": (last or {}).get("fetched_at"),
            "stale": "headlines" in failures,
            "warnings": [f"{name}: {reason}" for name, reason in failures.items()],
            "sources": ["CNBC", "MarketWatch", "Federal Reserve"],
        }

    def snapshot(self) -> dict[str, Any]:
        """Everything the Macro drawer and Claude need. Missing FRED access never hides the news."""
        result: dict[str, Any] = {"generated_at": self.clock().isoformat(timespec="seconds")}
        try:
            result["indicators"] = self.indicators()
            result["fred_configured"] = True
        except FredNotConfiguredError as exc:
            result["indicators"] = {"items": [], "unavailable": str(exc)}
            result["fred_configured"] = False
        result["calendar"] = self.calendar()
        result["news"] = self.headlines()
        return result
