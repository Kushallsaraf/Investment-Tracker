"""The in-app AI analyst: a chat about one ticker, grounded in a compact pack of the screen's facts.

The model only explains numbers the app has already calculated. It is told never to compute
prices, targets, or signals, and never to recommend buying or selling. The facts it sees are
returned to the page too, so the investor can check every claim.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any

from app.providers.llm import ChatModel, LlmUnavailableError
from app.providers.prices import normalize_symbol

NA = "NOT AVAILABLE"
MAX_TURNS = 6
MAX_MESSAGE = 2_000
MAX_ANSWER_TOKENS = 320

QUICK_PROMPTS = (
    {
        "key": "setup",
        "label": "Explain the setup",
        "prompt": "Explain the current technical setup in plain English.",
    },
    {
        "key": "case",
        "label": "Bull vs bear",
        "prompt": "Give me the bull case and the bear case, using only these facts.",
    },
    {
        "key": "value",
        "label": "Is it expensive?",
        "prompt": "Is the valuation high or low against its own history and what it earns?",
    },
    {
        "key": "news",
        "label": "What's in the news?",
        "prompt": "Summarize what the news this week says and how it might matter.",
    },
    {
        "key": "watch",
        "label": "What should I watch?",
        "prompt": "What would change the picture? List what to watch next.",
    },
)

RULES = """You are the research assistant inside Investment Tracker, a personal research tool for a
retail investor. Answer questions about {symbol} using ONLY the facts below.

Rules:
- Cite the numbers you use, with their dates, exactly as written in the facts.
- If something isn't in the facts or says NOT AVAILABLE, say you don't have it. Never estimate it.
- Never calculate new prices, price targets, stop levels, or trading signals.
- Valuation means the valuation facts only (P/E, P/S, EV/EBITDA, FCF yield). A falling price or
  a low spot in the 52-week range does not make a stock cheap or undervalued.
- Never tell the investor to buy, sell, or hold, and never call anything a buying or selling
  opportunity. Describe the evidence; the decision is theirs.
- Daily data only: there are no live quotes.
- Plain English, short bullets, under about 150 words unless asked for more.
  Explain jargon briefly the first time you use it.

Facts (generated {generated_at}):
{facts}"""

logger = logging.getLogger("investment_tracker.analyst")


def _pct(value: Any, digits: int = 1, signed: bool = False) -> str:
    if value is None:
        return NA
    number = float(value) * 100
    return f"{number:+.{digits}f}%" if signed else f"{number:.{digits}f}%"


def _money(value: Any) -> str:
    if value is None:
        return NA
    number = float(value)
    for size, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(number) >= size:
            return f"${number / size:.1f}{suffix}"
    return f"${number:,.2f}"


def _num(value: Any, digits: int = 2) -> str:
    return NA if value is None else f"{float(value):.{digits}f}"


def _metric(metric: dict[str, Any] | None, fmt: Callable[[Any], str]) -> str:
    if not metric or metric.get("value") is None:
        return NA
    as_of = f" (as of {metric['as_of']})" if metric.get("as_of") else ""
    return f"{fmt(metric['value'])}{as_of}"


class AnalystService:
    def __init__(
        self,
        model: ChatModel,
        *,
        market: Any,
        fundamentals: Any,
        insiders: Any,
        news: Any,
        journal: Any,
        exit_plans: Any,
        portfolio: Any,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.model = model
        self.market = market
        self.fundamentals = fundamentals
        self.insiders = insiders
        self.news = news
        self.journal = journal
        self.exit_plans = exit_plans
        self.portfolio = portfolio
        self.clock = clock or (lambda: datetime.now(UTC))

    def status(self) -> dict[str, Any]:
        return {
            "provider": self.model.provider,
            "model": self.model.model,
            "local": self.model.local,
            "quick_prompts": list(QUICK_PROMPTS),
            **self.model.status(),
        }

    # Fact pack

    def _price_and_trend(self, symbol: str) -> list[str]:
        data = self.market.technicals(symbol)
        trend = data["trend"]
        above = ", ".join(
            f"{'above' if flag else 'below'} the {days}-day average"
            for days, flag in (
                (20, trend["above_sma20"]),
                (50, trend["above_sma50"]),
                (200, trend["above_sma200"]),
            )
            if flag is not None
        )
        rs = data.get("relative_strength_3m") or {}
        position = data["range_52w"].get("position")
        return [
            f"Close {_num(data['close'])} on {data['as_of']} (daily data).",
            f"Trend: {trend['label'] or NA}; price is {above or NA}; "
            f"{_pct(trend['distance_sma50_pct'], signed=True)} from the 50-day average.",
            f"RSI(14) {_num(data['rsi14'], 1)} ({data['rsi_zone'] or NA}); "
            f"MACD {data['macd']['state'] or NA}.",
            f"52-week range {_num(data['range_52w']['low'])}–{_num(data['range_52w']['high'])}; "
            f"price is {_pct(position, 0)} of the way up it.",
            f"3-month return vs {rs.get('benchmark', 'SPY')}: "
            f"{_pct(rs.get('difference'), signed=True)} difference.",
            f"ATR(14) {_num(data['atr14'])} ({_pct(data['atr_pct'])} of price); "
            f"volume {_num(data['volume_ratio'])}x its 20-day average.",
        ]

    def _valuation(self, symbol: str) -> list[str]:
        data = self.fundamentals.fundamentals(symbol)
        if not data.get("applicable"):
            return [f"Not applicable: {data.get('reason', NA)}"]
        valuation, growth, profit = data["valuation"], data["growth"], data["profitability"]
        pe = data["valuation_history"]["pe"]
        band = (
            f", {round(pe['percentile'] * 100)}th percentile of its last {pe['observations']} quarters"
            if pe.get("status") == "available" and pe.get("percentile") is not None
            else ""
        )
        filing = data.get("latest_filing") or {}
        return [
            f"Market cap {_metric(valuation['market_cap'], _money)}.",
            f"P/E (TTM) {_metric(valuation['pe_ttm'], lambda v: f'{v:.1f}x')}{band}.",
            f"P/S (TTM) {_metric(valuation['ps_ttm'], lambda v: f'{v:.1f}x')}; "
            f"EV/EBITDA {_metric(valuation['ev_ebitda'], lambda v: f'{v:.1f}x')}; "
            f"FCF yield {_metric(valuation['fcf_yield'], _pct)}.",
            "Revenue growth (TTM, year over year) "
            f"{_metric(growth['revenue_ttm_yoy'], lambda v: _pct(v, signed=True))}.",
            f"Gross margin {_metric(profit['gross_margin'], _pct)}; "
            f"operating margin {_metric(profit['operating_margin'], _pct)}; "
            f"net cash {_metric(data['balance_sheet']['net_cash'], _money)}.",
            f"Source: SEC filings; latest {filing.get('form', NA)} filed {filing.get('filed', NA)}.",
        ]

    def _insiders(self, symbol: str) -> list[str]:
        data = self.insiders.activity(symbol)
        if not data.get("applicable"):
            return [f"Not applicable: {data.get('reason', NA)}"]
        summary = data["summary"]
        return [
            f"Last {data['days']} days of Form 4 filings: open-market buys "
            f"{_money(summary['purchase_value'])} by {summary['buyers']} insider(s); "
            f"sales {_money(summary['sale_value'])} by {summary['sellers']} "
            f"(of which {_money(summary['planned_sale_value'])} pre-planned 10b5-1).",
        ]

    def _news(self, symbol: str) -> list[str]:
        data = self.news.news(symbol)
        sentiment = data["sentiment"]
        if sentiment.get("available"):
            counts = sentiment["counts"]
            lines = [
                f"Headline sentiment over 7 days (FinBERT): {sentiment['net']:+.2f} on a -1 to +1 scale; "
                f"{counts['positive']} positive, {counts['neutral']} neutral, {counts['negative']} negative.",
            ]
        else:
            lines = [f"Headline sentiment: {NA} ({sentiment.get('reason')})."]
        for item in data["headlines"][:5]:
            label = item["sentiment"]["label"] if item.get("sentiment") else "unscored"
            lines.append(f"- {item['published_at'][:10]} ({label}): {item['title']}")
        for filing in data["filings"][:3]:
            lines.append(f"- {filing['published_at'][:10]} SEC {filing['title']}")
        if not data["headlines"]:
            lines.append("No headlines in the last 7 days.")
        return lines

    def _investor(self, symbol: str) -> list[str]:
        journal = self.journal.symbol_journal(symbol)
        portfolio = self.portfolio.latest()
        holding = next(
            (row for row in (portfolio or {}).get("holdings", []) if row["canonical_symbol"] == symbol), None
        )
        lines = []
        if holding:
            lines.append(
                f"The investor holds {holding['quantity']} shares at an average cost of "
                f"{holding['average_cost'] or NA}; {_pct(holding['portfolio_weight'])} of the portfolio."
            )
        else:
            lines.append("The investor doesn't hold this ticker.")
        decision = journal.get("decision")
        lines.append(
            f"Their recorded decision: {decision['decision']} (since {decision['decision_date']})."
            if decision
            else "No decision recorded (defaults to WATCH)."
        )
        plan = self.exit_plans.active(symbol)
        if plan:
            lines.append(
                f"Accepted exit plan: target {plan['target_price'] or NA}, stop {plan['stop_price'] or NA}, "
                f"review {plan['review_date'] or NA}. Reasoning: {plan['reasoning'][:200]}"
            )
        for note in journal.get("notes", [])[:3]:
            lines.append(f"- Note from {note['created_at'][:10]}: {note['body'][:200]}")
        return lines

    def facts(self, raw_symbol: str) -> dict[str, Any]:
        symbol = normalize_symbol(raw_symbol)
        self.market.ensure_history(symbol)  # validates the ticker before any section runs
        builders = (
            ("Price and trend", self._price_and_trend),
            ("Valuation (SEC filings)", self._valuation),
            ("Insider activity", self._insiders),
            ("News this week", self._news),
            ("The investor's own records", self._investor),
        )

        def build(entry: tuple[str, Callable[[str], list[str]]]) -> dict[str, Any]:
            title, builder = entry
            try:
                return {"title": title, "lines": builder(symbol), "available": True}
            except Exception as exc:  # one missing source shouldn't block the others
                logger.info("Fact section %s unavailable for %s: %s", title, symbol, exc)
                return {"title": title, "lines": [f"{NA} ({type(exc).__name__}: {exc})"], "available": False}

        with ThreadPoolExecutor(max_workers=5) as pool:
            sections = list(pool.map(build, builders))
        text = "\n\n".join(f"## {row['title']}\n" + "\n".join(row["lines"]) for row in sections)
        return {
            "symbol": symbol,
            "sections": sections,
            "text": text,
            "generated_at": self.clock().isoformat(timespec="seconds"),
        }

    # Chat

    @staticmethod
    def _conversation(messages: list[dict[str, str]]) -> list[dict[str, str]]:
        cleaned = [
            {"role": row["role"], "content": str(row["content"]).strip()[:MAX_MESSAGE]}
            for row in messages
            if row.get("role") in {"user", "assistant"} and str(row.get("content", "")).strip()
        ][-MAX_TURNS:]
        if not cleaned or cleaned[-1]["role"] != "user":
            raise ValueError("The conversation must end with a question")
        return cleaned

    def chat(self, raw_symbol: str, messages: list[dict[str, str]]) -> Iterator[str]:
        """Validate and start a streamed answer. Setup errors raise before any text is sent."""
        conversation = self._conversation(messages)
        status = self.model.status()
        if not status.get("ready"):
            raise LlmUnavailableError(status.get("reason", "The AI model isn't available"))
        pack = self.facts(raw_symbol)
        system = RULES.format(symbol=pack["symbol"], generated_at=pack["generated_at"], facts=pack["text"])
        stream = self.model.stream(
            [{"role": "system", "content": system}, *conversation], max_tokens=MAX_ANSWER_TOKENS
        )

        def answer() -> Iterator[str]:
            try:
                yield from stream
            except LlmUnavailableError as exc:
                yield f"\n\n[The answer stopped early: {exc}]"

        return answer()
