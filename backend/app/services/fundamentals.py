"""Company fundamentals from SEC XBRL facts, with trailing-twelve-month and valuation history.

Every value carries the period it describes. A metric that cannot be computed from
filed data is returned as None with a reason; nothing is estimated or back-filled.
"""

from __future__ import annotations

from bisect import bisect_right
from datetime import date, timedelta
from statistics import median
from typing import Any

from app.providers.sec import SEC_SOURCE, filing_index_url

ANNUAL_FORMS = {"10-K", "10-K/A", "10-KT"}
REPORT_FORMS = ANNUAL_FORMS | {"10-Q", "10-Q/A"}

# Concepts in priority order. Companies switch concepts over time (for example from
# SalesRevenueNet to RevenueFromContractWithCustomer...), so periods are merged across them.
FLOW_CONCEPTS: dict[str, tuple[tuple[str, str, str], ...]] = {
    "revenue": (
        ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax", "USD"),
        ("us-gaap", "Revenues", "USD"),
        ("us-gaap", "RevenueFromContractWithCustomerIncludingAssessedTax", "USD"),
        ("us-gaap", "SalesRevenueNet", "USD"),
    ),
    "cost_of_revenue": (
        ("us-gaap", "CostOfRevenue", "USD"),
        ("us-gaap", "CostOfGoodsAndServicesSold", "USD"),
    ),
    "gross_profit": (("us-gaap", "GrossProfit", "USD"),),
    "operating_income": (("us-gaap", "OperatingIncomeLoss", "USD"),),
    "net_income": (("us-gaap", "NetIncomeLoss", "USD"),),
    "operating_cash_flow": (("us-gaap", "NetCashProvidedByUsedInOperatingActivities", "USD"),),
    "capex": (
        ("us-gaap", "PaymentsToAcquirePropertyPlantAndEquipment", "USD"),
        ("us-gaap", "PaymentsToAcquireProductiveAssets", "USD"),
    ),
    "depreciation": (
        ("us-gaap", "DepreciationDepletionAndAmortization", "USD"),
        ("us-gaap", "DepreciationAndAmortization", "USD"),
        ("us-gaap", "DepreciationAmortizationAndAccretionNet", "USD"),
    ),
    "diluted_shares": (("us-gaap", "WeightedAverageNumberOfDilutedSharesOutstanding", "shares"),),
}
INSTANT_CONCEPTS: dict[str, tuple[tuple[str, str, str], ...]] = {
    "cash": (
        ("us-gaap", "CashAndCashEquivalentsAtCarryingValue", "USD"),
        ("us-gaap", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", "USD"),
    ),
    "short_term_investments": (
        ("us-gaap", "ShortTermInvestments", "USD"),
        ("us-gaap", "MarketableSecuritiesCurrent", "USD"),
        ("us-gaap", "AvailableForSaleSecuritiesDebtSecuritiesCurrent", "USD"),
    ),
    "long_term_debt": (("us-gaap", "LongTermDebt", "USD"),),
    "long_term_debt_noncurrent": (("us-gaap", "LongTermDebtNoncurrent", "USD"),),
    "long_term_debt_current": (
        ("us-gaap", "LongTermDebtCurrent", "USD"),
        ("us-gaap", "DebtCurrent", "USD"),
    ),
    "short_term_debt": (
        ("us-gaap", "ShortTermBorrowings", "USD"),
        ("us-gaap", "CommercialPaper", "USD"),
    ),
    "equity": (
        ("us-gaap", "StockholdersEquity", "USD"),
        ("us-gaap", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", "USD"),
    ),
    "shares_outstanding": (
        ("dei", "EntityCommonStockSharesOutstanding", "shares"),
        ("us-gaap", "CommonStockSharesOutstanding", "shares"),
    ),
}


def _days(start: str, end: str) -> int:
    return (date.fromisoformat(end) - date.fromisoformat(start)).days


def _is_quarter(days: int) -> bool:
    return 80 <= days <= 100


def _facts(company_facts: dict[str, Any], concepts: tuple[tuple[str, str, str], ...]) -> list[dict[str, Any]]:
    """Facts from periodic reports, tagged with concept priority (lower wins)."""
    rows: list[dict[str, Any]] = []
    taxonomies = company_facts.get("facts") or {}
    for priority, (taxonomy, concept, unit) in enumerate(concepts):
        units = ((taxonomies.get(taxonomy) or {}).get(concept) or {}).get("units") or {}
        for fact in units.get(unit) or []:
            if fact.get("form") in REPORT_FORMS and fact.get("end") and fact.get("val") is not None:
                rows.append({**fact, "priority": priority})
    return rows


def _latest_per_period(
    rows: list[dict[str, Any]], key: tuple[str, ...]
) -> dict[tuple[str, ...], dict[str, Any]]:
    """For each period keep the preferred concept, then the most recently filed (restated) value."""
    chosen: dict[tuple[str, ...], dict[str, Any]] = {}
    for row in rows:
        period = tuple(row.get(field) or "" for field in key)
        current = chosen.get(period)
        if current is None or (row["priority"], -_filed_ordinal(row)) < (
            current["priority"],
            -_filed_ordinal(current),
        ):
            chosen[period] = row
    return chosen


def _filed_ordinal(row: dict[str, Any]) -> int:
    filed = row.get("filed")
    return date.fromisoformat(filed).toordinal() if filed else 0


def quarterly_series(rows: list[dict[str, Any]]) -> list[list[Any]]:
    """Discrete quarters as [start, end, value, filed, derived].

    10-Q filings report income-statement items for the quarter, but cash-flow items
    only year-to-date (6 and 9 months), and Q4 appears only inside the annual total.
    Missing quarters are derived by subtracting consecutive year-to-date values that
    share a fiscal-year start.
    """
    periods = _latest_per_period([row for row in rows if row.get("start")], ("start", "end"))
    quarters: dict[str, list[Any]] = {}
    for (start, end), row in periods.items():
        if _is_quarter(_days(start, end)):
            quarters[end] = [start, end, float(row["val"]), row.get("filed"), False]
    by_start: dict[str, list[dict[str, Any]]] = {}
    for (start, end), row in periods.items():
        if _days(start, end) >= 80:
            by_start.setdefault(start, []).append(row)
    for items in by_start.values():
        items.sort(key=lambda row: row["end"])
        for previous, current in zip(items, items[1:], strict=False):
            if current["end"] in quarters or not _is_quarter(_days(previous["end"], current["end"])):
                continue
            quarter_start = (date.fromisoformat(previous["end"]) + timedelta(days=1)).isoformat()
            quarters[current["end"]] = [
                quarter_start,
                current["end"],
                float(current["val"]) - float(previous["val"]),
                current.get("filed"),
                True,
            ]
    # Some filers report Q1-Q3 only as standalone quarters; then Q4 is the year minus those three.
    for (start, end), row in periods.items():
        if end in quarters or not 350 <= _days(start, end) <= 380:
            continue
        inside = [quarter for quarter in quarters.values() if start <= quarter[0] and quarter[1] < end]
        if len(inside) == 3 and abs(_days(start, min(quarter[0] for quarter in inside))) <= 5:
            last_end = max(quarter[1] for quarter in inside)
            if _is_quarter(_days(last_end, end)):
                quarter_start = (date.fromisoformat(last_end) + timedelta(days=1)).isoformat()
                value = float(row["val"]) - sum(quarter[2] for quarter in inside)
                quarters[end] = [quarter_start, end, value, row.get("filed"), True]
    return [quarters[end] for end in sorted(quarters)]


def annual_series(rows: list[dict[str, Any]]) -> list[list[Any]]:
    periods = _latest_per_period(
        [row for row in rows if row.get("start") and row.get("form") in ANNUAL_FORMS], ("start", "end")
    )
    annual = [
        [start, end, float(row["val"]), row.get("filed")]
        for (start, end), row in periods.items()
        if 350 <= _days(start, end) <= 380
    ]
    return sorted(annual, key=lambda row: row[1])


def instant_series(rows: list[dict[str, Any]]) -> list[list[Any]]:
    periods = _latest_per_period([row for row in rows if not row.get("start")], ("end",))
    return sorted(
        ([end, float(row["val"]), row.get("filed")] for (end,), row in periods.items()), key=lambda r: r[0]
    )


def extract_financials(company_facts: dict[str, Any]) -> dict[str, Any]:
    """Reduce SEC's multi-megabyte company facts to the compact series the app uses."""
    flows = {}
    for metric, concepts in FLOW_CONCEPTS.items():
        rows = _facts(company_facts, concepts)
        flows[metric] = {"quarters": quarterly_series(rows), "annual": annual_series(rows)}
    instants = {
        metric: instant_series(_facts(company_facts, concepts))
        for metric, concepts in INSTANT_CONCEPTS.items()
    }
    return {
        "entity_name": company_facts.get("entityName"),
        # Foreign private issuers file 20-F/6-K under IFRS and have no US GAAP facts.
        "us_gaap": "us-gaap" in (company_facts.get("facts") or {}),
        "flows": flows,
        "instants": instants,
    }


def _ttm(quarters: list[list[Any]], *, ending_index: int | None = None) -> tuple[float, str] | None:
    """Sum of four consecutive quarters ending at ending_index (default: the latest)."""
    end_index = len(quarters) - 1 if ending_index is None else ending_index
    if end_index < 3:
        return None
    window = quarters[end_index - 3 : end_index + 1]
    for previous, current in zip(window, window[1:], strict=False):
        if not _is_quarter(_days(previous[1], current[1])):
            return None
    return sum(row[2] for row in window), window[-1][1]


def _ttm_at(quarters: list[list[Any]], end: str) -> float | None:
    ends = [row[1] for row in quarters]
    if end not in ends:
        return None
    result = _ttm(quarters, ending_index=ends.index(end))
    return result[0] if result else None


def _latest(instants: list[list[Any]]) -> tuple[float, str] | None:
    return (instants[-1][1], instants[-1][0]) if instants else None


def _value_at(instants: list[list[Any]], end: str) -> float | None:
    return next((row[1] for row in instants if row[0] == end), None)


def _metric(value: float | None, as_of: str | None = None, note: str | None = None) -> dict[str, Any]:
    if value is not None:
        value = round(value, 6)
    return {"value": value, "as_of": as_of, "note": None if value is not None else note or "Not available"}


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def split_adjusted_shares(points: list[list[Any]]) -> list[tuple[str, float]]:
    """Restate historical share counts onto today's basis after stock splits.

    Price history is split-adjusted, but filed share counts are as reported at the
    time. A jump between consecutive counts close to a whole ratio (2:1, 3:1, 10:1,
    or the inverse) is treated as a split and applied to all earlier counts.
    """
    adjusted = [(row[0], float(row[1])) for row in points if row[1] and row[1] > 0]
    factor = 1.0
    result: list[tuple[str, float]] = []
    for index in range(len(adjusted) - 1, -1, -1):
        end, shares = adjusted[index]
        result.append((end, shares * factor))
        if index > 0:
            ratio = shares / adjusted[index - 1][1]
            if ratio >= 1.8 and abs(ratio - round(ratio)) < 0.15:
                factor *= round(ratio)
            elif ratio <= 0.55 and abs(1 / ratio - round(1 / ratio)) < 0.15:
                factor /= round(1 / ratio)
    return list(reversed(result))


def _close_on_or_before(bars: list[dict[str, Any]], day: str) -> float | None:
    dates = [bar["date"] for bar in bars]
    index = bisect_right(dates, day) - 1
    if index < 0 or (date.fromisoformat(day) - date.fromisoformat(dates[index])).days > 7:
        return None
    return float(bars[index]["close"])


def _band(
    points: list[float], current: float | None, label: str, start: str | None, end: str | None
) -> dict[str, Any]:
    if current is None or len(points) < 8:
        return {
            "metric": label,
            "current": round(current, 2) if current is not None else None,
            "status": "not_available",
            "note": "Needs at least 8 quarters of positive history"
            if current is not None
            else "No current value",
        }
    ordered = sorted(points)
    return {
        "metric": label,
        "status": "available",
        "current": round(current, 2),
        "min": round(ordered[0], 2),
        "median": round(median(ordered), 2),
        "max": round(ordered[-1], 2),
        "percentile": round(sum(1 for point in ordered if point <= current) / len(ordered), 4),
        "observations": len(ordered),
        "start": start,
        "end": end,
    }


def valuation_history(
    model: dict[str, Any], bars: list[dict[str, Any]], current: dict[str, float | None]
) -> dict[str, Any]:
    """Quarter-end P/E and P/S over up to five years, compared with today."""
    revenue = model["flows"]["revenue"]["quarters"]
    income = model["flows"]["net_income"]["quarters"]
    shares = split_adjusted_shares(model["instants"]["shares_outstanding"])
    if not bars or not shares or not revenue:
        return {
            "pe": _band([], current.get("pe"), "P/E", None, None),
            "ps": _band([], current.get("ps"), "P/S", None, None),
        }
    cutoff = (date.fromisoformat(bars[-1]["date"]) - timedelta(days=5 * 366)).isoformat()
    share_dates = [row[0] for row in shares]
    pe_points: list[float] = []
    ps_points: list[float] = []
    ends_used: list[str] = []
    for quarter in revenue:
        end = quarter[1]
        if end < cutoff:
            continue
        price = _close_on_or_before(bars, end)
        # Cover-page share counts are dated a few weeks after the quarter they follow.
        index = bisect_right(share_dates, (date.fromisoformat(end) + timedelta(days=75)).isoformat()) - 1
        if price is None or index < 0 or _days(share_dates[index], end) > 120:
            continue
        market_cap = price * shares[index][1]
        ttm_revenue = _ttm_at(revenue, end)
        ttm_income = _ttm_at(income, end)
        if ttm_revenue and ttm_revenue > 0:
            ps_points.append(market_cap / ttm_revenue)
            ends_used.append(end)
        if ttm_income and ttm_income > 0:
            pe_points.append(market_cap / ttm_income)
    start, end = (ends_used[0], ends_used[-1]) if ends_used else (None, None)
    return {
        "pe": _band(pe_points, current.get("pe"), "P/E", start, end),
        "ps": _band(ps_points, current.get("ps"), "P/S", start, end),
    }


def summarize(
    model: dict[str, Any],
    *,
    price: float | None,
    price_as_of: str | None,
    bars: list[dict[str, Any]],
) -> dict[str, Any]:
    flows = model["flows"]
    instants = model["instants"]
    notes: list[str] = []

    def ttm(metric: str, *, ending_index: int | None = None) -> tuple[float, str] | None:
        return _ttm(flows[metric]["quarters"], ending_index=ending_index)

    revenue = ttm("revenue")
    revenue_quarters = flows["revenue"]["quarters"]
    prior_revenue = (
        ttm("revenue", ending_index=len(revenue_quarters) - 5) if len(revenue_quarters) >= 8 else None
    )
    net_income = ttm("net_income")
    income_quarters = flows["net_income"]["quarters"]
    prior_income = (
        ttm("net_income", ending_index=len(income_quarters) - 5) if len(income_quarters) >= 8 else None
    )
    operating_income = ttm("operating_income")
    gross_profit = ttm("gross_profit")
    if gross_profit is None and revenue and ttm("cost_of_revenue"):
        cost = ttm("cost_of_revenue")
        if cost and cost[1] == revenue[1]:
            gross_profit = (revenue[0] - cost[0], revenue[1])
    operating_cash_flow = ttm("operating_cash_flow")
    capex = ttm("capex")
    depreciation = ttm("depreciation")
    free_cash_flow = (
        (operating_cash_flow[0] - capex[0], operating_cash_flow[1])
        if operating_cash_flow and capex and operating_cash_flow[1] == capex[1]
        else None
    )
    ebitda = (
        (operating_income[0] + depreciation[0], operating_income[1])
        if operating_income and depreciation and operating_income[1] == depreciation[1]
        else None
    )

    shares = _latest(instants["shares_outstanding"])
    if shares and price_as_of and _days(shares[1], price_as_of) > 200:
        notes.append(
            f"The latest reported share count is from {shares[1]}, too old to value the company today."
        )
        shares = None
    market_cap = price * shares[0] if price is not None and shares else None
    cash = _latest(instants["cash"])
    cash_total = None
    if cash:
        cash_total = cash[0] + (_value_at(instants["short_term_investments"], cash[1]) or 0.0)
    debt_total, debt_as_of = None, None
    if instants["long_term_debt"]:
        debt_total, debt_as_of = instants["long_term_debt"][-1][1], instants["long_term_debt"][-1][0]
    elif instants["long_term_debt_noncurrent"]:
        debt_as_of = instants["long_term_debt_noncurrent"][-1][0]
        debt_total = instants["long_term_debt_noncurrent"][-1][1] + (
            _value_at(instants["long_term_debt_current"], debt_as_of) or 0.0
        )
    if debt_total is not None and debt_as_of:
        debt_total += _value_at(instants["short_term_debt"], debt_as_of) or 0.0
    equity = _latest(instants["equity"])
    enterprise_value = (
        market_cap + debt_total - cash_total
        if market_cap is not None and debt_total is not None and cash_total is not None
        else None
    )

    pe = _ratio(market_cap, net_income[0]) if net_income and net_income[0] > 0 else None
    if net_income and net_income[0] <= 0:
        notes.append("P/E is not meaningful because trailing twelve-month net income is negative.")
    ps = _ratio(market_cap, revenue[0]) if revenue else None
    ev_ebitda = _ratio(enterprise_value, ebitda[0]) if ebitda and ebitda[0] > 0 else None
    if not instants["shares_outstanding"]:
        notes.append("Shares outstanding were not reported, so market-value ratios are unavailable.")
    if free_cash_flow is None and operating_cash_flow:
        notes.append("Capital expenditures were not reported under the standard concept.")

    def growth(current: tuple[float, str] | None, previous: tuple[float, str] | None) -> float | None:
        if not current or not previous or previous[0] <= 0:
            return None
        return current[0] / previous[0] - 1

    quarter_growth = None
    if len(revenue_quarters) >= 5:
        latest = revenue_quarters[-1]
        year_ago = next(
            (row for row in revenue_quarters if 350 <= _days(row[1], latest[1]) <= 380),
            None,
        )
        if year_ago and year_ago[2] > 0:
            quarter_growth = latest[2] / year_ago[2] - 1

    ttm_end = revenue[1] if revenue else None
    annual_revenue = flows["revenue"]["annual"][-5:]
    annual_income = {row[1]: row[2] for row in flows["net_income"]["annual"]}
    annual_ocf = {row[1]: row[2] for row in flows["operating_cash_flow"]["annual"]}
    annual_capex = {row[1]: row[2] for row in flows["capex"]["annual"]}

    current_ratios = {"pe": pe, "ps": ps}
    return {
        "price": _metric(price, price_as_of, "No recent price"),
        "period": {
            "ttm_end": ttm_end,
            "latest_quarter_end": revenue_quarters[-1][1] if revenue_quarters else None,
        },
        "valuation": {
            "market_cap": _metric(market_cap, price_as_of, "Price or share count unavailable"),
            "enterprise_value": _metric(enterprise_value, price_as_of, "Debt or cash not reported"),
            "pe_ttm": _metric(pe, ttm_end, "Earnings negative or unavailable"),
            "ps_ttm": _metric(ps, ttm_end, "Revenue unavailable"),
            "ev_ebitda": _metric(ev_ebitda, ttm_end, "EBITDA negative or unavailable"),
            "pb": _metric(
                _ratio(market_cap, equity[0]) if equity and equity[0] > 0 else None,
                equity[1] if equity else None,
                "Equity negative or unavailable",
            ),
            "fcf_yield": _metric(
                _ratio(free_cash_flow[0], market_cap) if free_cash_flow else None,
                free_cash_flow[1] if free_cash_flow else None,
                "Free cash flow unavailable",
            ),
        },
        "growth": {
            "revenue_ttm_yoy": _metric(
                growth(revenue, prior_revenue), ttm_end, "Needs eight quarters of revenue"
            ),
            "revenue_quarter_yoy": _metric(
                quarter_growth,
                revenue_quarters[-1][1] if revenue_quarters else None,
                "Needs the same quarter a year earlier",
            ),
            "net_income_ttm_yoy": _metric(
                growth(net_income, prior_income),
                net_income[1] if net_income else None,
                "Prior-year earnings negative or unavailable",
            ),
        },
        "profitability": {
            "gross_margin": _metric(
                _ratio(gross_profit[0], revenue[0]) if gross_profit and revenue else None,
                ttm_end,
                "Gross profit not reported",
            ),
            "operating_margin": _metric(
                _ratio(operating_income[0], revenue[0]) if operating_income and revenue else None,
                ttm_end,
                "Operating income not reported",
            ),
            "net_margin": _metric(
                _ratio(net_income[0], revenue[0]) if net_income and revenue else None,
                ttm_end,
                "Net income unavailable",
            ),
            "fcf_margin": _metric(
                _ratio(free_cash_flow[0], revenue[0]) if free_cash_flow and revenue else None,
                ttm_end,
                "Free cash flow unavailable",
            ),
        },
        "ttm": {
            "revenue": _metric(revenue[0] if revenue else None, ttm_end, "Revenue not reported"),
            "net_income": _metric(
                net_income[0] if net_income else None,
                net_income[1] if net_income else None,
                "Net income unavailable",
            ),
            "free_cash_flow": _metric(
                free_cash_flow[0] if free_cash_flow else None,
                free_cash_flow[1] if free_cash_flow else None,
                "Free cash flow unavailable",
            ),
            "ebitda": _metric(
                ebitda[0] if ebitda else None, ebitda[1] if ebitda else None, "Depreciation not reported"
            ),
        },
        "balance_sheet": {
            "cash": _metric(cash_total, cash[1] if cash else None, "Cash not reported"),
            "debt": _metric(debt_total, debt_as_of, "Debt not reported under standard concepts"),
            "net_cash": _metric(
                cash_total - debt_total if cash_total is not None and debt_total is not None else None,
                debt_as_of,
                "Cash or debt unavailable",
            ),
            "debt_to_equity": _metric(
                _ratio(debt_total, equity[0])
                if debt_total is not None and equity and equity[0] > 0
                else None,
                debt_as_of,
                "Debt or positive equity unavailable",
            ),
            "shares_outstanding": _metric(
                shares[0] if shares else None, shares[1] if shares else None, "Share count not reported"
            ),
        },
        "valuation_history": valuation_history(model, bars, current_ratios),
        "annual": [
            {
                "fiscal_year_end": end,
                "revenue": round(value, 2),
                "net_income": round(annual_income[end], 2) if end in annual_income else None,
                "free_cash_flow": round(annual_ocf[end] - annual_capex[end], 2)
                if end in annual_ocf and end in annual_capex
                else None,
            }
            for _start, end, value, _filed in annual_revenue
        ],
        "notes": notes,
    }


def latest_report(submissions: dict[str, Any], cik: int) -> dict[str, Any] | None:
    recent = (submissions.get("filings") or {}).get("recent") or {}
    for index, form in enumerate(recent.get("form") or []):
        if form in {"10-K", "10-Q", "10-K/A", "10-Q/A"}:
            accession = recent["accessionNumber"][index]
            return {
                "form": form,
                "filed": recent["filingDate"][index],
                "period": (recent.get("reportDate") or [None] * (index + 1))[index] or None,
                "url": filing_index_url(cik, accession),
            }
    return None


class FundamentalsService:
    """Combine cached SEC facts with cached daily prices for one ticker."""

    def __init__(self, sec: Any, market: Any) -> None:
        self.sec = sec
        self.market = market

    def fundamentals(self, symbol: str) -> dict[str, Any]:
        meta, bars, price_stale = self.market.ensure_history(symbol)
        base = {"symbol": meta["symbol"], "name": meta["security_name"], "asset_type": meta["asset_type"]}
        if meta["asset_type"] == "ETF":
            return {
                **base,
                "applicable": False,
                "reason": (
                    "ETFs don't file company financial statements. Fund holdings are planned separately."
                ),
                "source": SEC_SOURCE,
            }
        company = self.sec.company(meta["symbol"])
        model, fetched_at, stale = self.sec.financials(company["cik"])
        if not model.get("us_gaap", True):
            return {
                **base,
                "applicable": False,
                "reason": (
                    "This company reports as a foreign filer (20-F and 6-K under IFRS), "
                    "which isn't supported yet."
                ),
                "source": SEC_SOURCE,
            }
        submissions, _, _ = self.sec.submissions(company["cik"])
        last = bars[-1] if bars else None
        summary = summarize(
            model,
            price=float(last["close"]) if last else None,
            price_as_of=last["date"] if last else None,
            bars=bars,
        )
        return {
            **base,
            "applicable": True,
            "cik": company["cik"],
            "sec_name": model.get("entity_name") or company["title"],
            "sic": submissions.get("sic") or None,
            "sic_description": submissions.get("sicDescription") or None,
            "fiscal_year_end": submissions.get("fiscalYearEnd") or None,
            "latest_filing": latest_report(submissions, company["cik"]),
            **summary,
            "source": f"{SEC_SOURCE} company facts (10-K and 10-Q) · price from daily history",
            "fetched_at": fetched_at,
            "stale": stale or price_stale,
        }
