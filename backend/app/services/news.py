"""Ticker news: RSS headlines and SEC 8-K filings, with local FinBERT sentiment.

Headlines are cached in SQLite and refetched at most every 30 minutes. Each headline is scored
once; scores describe the wording of headlines, not the stock, and are never a signal.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from app.news_repository import NewsRepository
from app.providers.news import NewsProvider
from app.providers.prices import normalize_symbol
from app.services.sentiment import Scorer, label_for, net_score

REFRESH_AFTER = timedelta(minutes=30)
WINDOW_DAYS = 7
FILING_DAYS = 30
MAX_HEADLINES = 40
SEC_SOURCE = "SEC EDGAR 8-K filings"

# 8-K item numbers that say what the filing is about. Item 9.01 (exhibits) adds nothing.
EIGHT_K_ITEMS = {
    "1.01": "Material agreement",
    "1.02": "Agreement terminated",
    "1.03": "Bankruptcy",
    "2.01": "Acquisition or sale of assets",
    "2.02": "Earnings results",
    "2.03": "New debt or obligation",
    "2.04": "Debt acceleration",
    "2.05": "Restructuring or exit costs",
    "2.06": "Impairment",
    "3.01": "Listing notice",
    "3.02": "Unregistered share sale",
    "3.03": "Shareholder rights changed",
    "4.01": "Auditor change",
    "4.02": "Earlier financials no longer reliable",
    "5.01": "Change in control",
    "5.02": "Director or officer change",
    "5.03": "Bylaws or fiscal year change",
    "5.07": "Shareholder vote results",
    "7.01": "Regulation FD disclosure",
    "8.01": "Other events",
}

logger = logging.getLogger("investment_tracker.news")


def _item_id(symbol: str, url: str) -> str:
    return hashlib.sha1(f"{symbol}|{url}".encode()).hexdigest()


def describe_8k(items: str | None) -> str:
    codes = [code.strip() for code in (items or "").split(",") if code.strip() and code.strip() != "9.01"]
    labels = [EIGHT_K_ITEMS.get(code, f"Item {code}") for code in codes]
    return "; ".join(labels) or "Current report"


class NewsService:
    def __init__(
        self,
        repository: NewsRepository,
        provider: NewsProvider,
        *,
        sec: Any = None,
        market: Any = None,
        scorer: Scorer | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.provider = provider
        self.sec = sec
        self.market = market
        self.scorer = scorer
        self.clock = clock or (lambda: datetime.now(UTC))

    def _filings(self, symbol: str, today: date) -> list[dict[str, Any]]:
        if self.sec is None:
            return []
        company = self.sec.company(symbol)
        cik = int(company["cik"])
        submissions, _, _ = self.sec.submissions(cik)
        recent = (submissions.get("filings") or {}).get("recent") or {}
        cutoff = (today - timedelta(days=FILING_DAYS)).isoformat()
        items_by_index = recent.get("items") or []
        filings = []
        for index, form in enumerate(recent.get("form") or []):
            filed = recent["filingDate"][index]
            if form not in {"8-K", "8-K/A"} or filed < cutoff:
                continue
            accession = recent["accessionNumber"][index]
            document = recent["primaryDocument"][index]
            url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}/{document}"
            codes = items_by_index[index] if index < len(items_by_index) else ""
            filings.append(
                {
                    "id": _item_id(symbol, url),
                    "kind": "FILING",
                    "title": f"{form}: {describe_8k(codes)}",
                    "summary": None,
                    "url": url,
                    "publisher": "SEC EDGAR",
                    "published_at": f"{filed}T00:00:00+00:00",
                }
            )
        return filings

    def _refresh(self, symbol: str, is_etf: bool) -> None:
        now = self.clock()
        failures: dict[str, str] = {}
        items: list[dict[str, Any]] = []
        try:
            headlines = self.provider.headlines(symbol)
            failures.update(headlines.get("failures") or {})
            for item in headlines["items"]:
                items.append({**item, "id": _item_id(symbol, item["url"]), "kind": "HEADLINE"})
        except Exception as exc:
            failures["headlines"] = f"{type(exc).__name__}: {exc}"
        if not is_etf:
            try:
                items.extend(self._filings(symbol, now.date()))
            except Exception as exc:  # unreachable SEC or a ticker SEC doesn't list
                failures["SEC EDGAR"] = f"8-K filings could not be loaded ({type(exc).__name__})"
        self.repository.save_items(symbol, items, failures, now.isoformat(timespec="seconds"))

    def _score(self, rows: list[dict[str, Any]]) -> str | None:
        """Score unscored headlines. Returns why scoring is unavailable, or None when it worked."""
        pending = [row for row in rows if row["kind"] == "HEADLINE" and row["scored_at"] is None]
        if self.scorer is None:
            return None if not pending else "FinBERT is not installed (pip install -e '.[sentiment]')"
        if not pending:
            return None
        try:
            scores = self.scorer.score([row["title"] for row in pending])
        except Exception as exc:
            logger.warning("Sentiment scoring failed: %s", exc)
            return f"FinBERT could not run ({type(exc).__name__})"
        self.repository.save_scores(
            {row["id"]: score for row, score in zip(pending, scores, strict=True)}, self.scorer.model
        )
        return None

    def news(self, raw_symbol: str) -> dict[str, Any]:
        symbol = normalize_symbol(raw_symbol)
        is_etf = False
        if self.market is not None:
            meta, _, _ = self.market.ensure_history(symbol)  # validates the ticker
            symbol = meta["symbol"]
            is_etf = meta["asset_type"] == "ETF"
        now = self.clock()
        last = self.repository.last_fetch(symbol)
        if last is None or now - datetime.fromisoformat(last["fetched_at"]) > REFRESH_AFTER:
            self._refresh(symbol, is_etf)
            last = self.repository.last_fetch(symbol)
        failures = (last or {}).get("failures", {})
        stale = "headlines" in failures

        since = (now - timedelta(days=FILING_DAYS)).isoformat(timespec="seconds")
        rows = self.repository.items(symbol, since)
        sentiment_issue = self._score(rows)
        if sentiment_issue is None:
            rows = self.repository.items(symbol, since)

        window_start = (now - timedelta(days=WINDOW_DAYS)).isoformat(timespec="seconds")
        headlines = [self._headline(row) for row in rows if row["kind"] == "HEADLINE"]
        recent = [row for row in headlines if row["published_at"] >= window_start]
        filings = [self._headline(row) for row in rows if row["kind"] == "FILING"]
        return {
            "symbol": symbol,
            "window_days": WINDOW_DAYS,
            "headlines": recent[:MAX_HEADLINES] or headlines[:10],
            "filings": filings,
            "sentiment": self._summary(recent, now.date(), sentiment_issue),
            "latest_published_at": headlines[0]["published_at"] if headlines else None,
            "fetched_at": (last or {}).get("fetched_at"),
            "stale": stale,
            "warnings": [f"{name}: {reason}" for name, reason in failures.items()],
            "sources": ["Yahoo Finance RSS", "Nasdaq RSS", *([] if is_etf else [SEC_SOURCE])],
        }

    @staticmethod
    def _headline(row: dict[str, Any]) -> dict[str, Any]:
        scored = row["scored_at"] is not None
        probabilities = {"positive": row["positive"], "neutral": row["neutral"], "negative": row["negative"]}
        return {
            "id": row["id"],
            "kind": row["kind"],
            "title": row["title"],
            "summary": row["summary"],
            "url": row["url"],
            "publisher": row["publisher"],
            "published_at": row["published_at"],
            "sentiment": {
                "label": label_for(probabilities),
                "net": net_score(probabilities),
                **probabilities,
                "model": row["sentiment_model"],
            }
            if scored
            else None,
        }

    def _summary(self, recent: list[dict[str, Any]], today: date, issue: str | None) -> dict[str, Any]:
        scored = [row for row in recent if row["sentiment"] is not None]
        if not scored:
            reason = issue or (
                "No headlines in the last 7 days" if not recent else "Headlines have not been scored yet"
            )
            return {"available": False, "reason": reason, "model": None, "trend": [], "counts": None}
        days = []
        for offset in range(WINDOW_DAYS - 1, -1, -1):
            day = (today - timedelta(days=offset)).isoformat()
            on_day = [row for row in scored if row["published_at"][:10] == day]
            days.append(
                {
                    "date": day,
                    "count": len(on_day),
                    "net": round(sum(row["sentiment"]["net"] for row in on_day) / len(on_day), 3)
                    if on_day
                    else None,
                }
            )
        counts = {
            label: sum(row["sentiment"]["label"] == label for row in scored)
            for label in ("positive", "neutral", "negative")
        }
        return {
            "available": True,
            "reason": issue,
            "model": scored[0]["sentiment"]["model"],
            "net": round(sum(row["sentiment"]["net"] for row in scored) / len(scored), 3),
            "counts": counts,
            "scored": len(scored),
            "trend": days,
        }
