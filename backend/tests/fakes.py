"""Synthetic, network-free test doubles shared by the backend tests."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.providers.prices import UnsupportedSymbolError, normalize_symbol

OBSERVED_AT = "2026-09-11T20:00:00+00:00"
FETCHED_AT = "2026-09-11T20:01:00+00:00"

IDENTITIES: dict[str, dict[str, str]] = {
    "ACME": {"security_name": "Acme Corporation", "asset_type": "STOCK", "exchange": "NYSE"},
    "SYNE": {"security_name": "Synthetic Equity ETF", "asset_type": "ETF", "exchange": "NYSEArca"},
    "BRK.B": {"security_name": "Berkshire Hathaway Inc.", "asset_type": "STOCK", "exchange": "NYSE"},
}


class FakePrices:
    """Return fixed USD prices and identities; unknown symbols are rejected like a non-US listing."""

    source = "Synthetic quote"
    supports_automatic_refresh = False
    automatic_refresh_seconds = None

    def __init__(self, prices: dict[str, str] | None = None, *, stale: bool = False) -> None:
        self.prices = prices or {"ACME": "120", "SYNE": "50", "BRK.B": "400"}
        self.stale = stale
        self.lookups: list[str] = []

    def lookup(self, symbol: str) -> dict[str, Any]:
        canonical = normalize_symbol(symbol)
        self.lookups.append(canonical)
        if canonical not in IDENTITIES:
            raise UnsupportedSymbolError(f"{canonical} was not found")
        return {"canonical_symbol": canonical, **IDENTITIES[canonical]}

    def quote(self, instrument: dict[str, Any]) -> dict[str, Any]:
        return {
            "price": self.prices[instrument["canonical_symbol"]],
            "observed_at": OBSERVED_AT,
            "fetched_at": FETCHED_AT,
            "source": self.source,
            "source_url": "https://example.invalid/synthetic",
            "quote_status": "end_of_day",
            "delay_minutes": None,
            "stale": self.stale,
        }


def synthetic_bars(count: int, *, base: float = 100.0, step: float = 0.5) -> list[dict[str, Any]]:
    """Weekday bars rising by `step` each session, with a fixed 2-point high-low range."""
    bars: list[dict[str, Any]] = []
    day = date(2023, 1, 2)
    while len(bars) < count:
        if day.weekday() < 5:
            close = base + step * len(bars)
            bars.append(
                {
                    "date": day.isoformat(),
                    "open": close - 0.2,
                    "high": close + 1,
                    "low": close - 1,
                    "close": close,
                    "adj_close": close,
                    "volume": 1_000,
                }
            )
        day += timedelta(days=1)
    return bars


def listing(name: str, *, currency: str = "USD", instrument_type: str = "EQUITY") -> dict[str, Any]:
    return {
        "currency": currency,
        "instrument_type": instrument_type,
        "name": name,
        "exchange": "NYSE",
        "market_price": None,
        "market_time": None,
    }


class FakeHistory:
    """Serve full history for the initial period and only recent bars for incremental refreshes."""

    def __init__(self, series: dict[str, dict[str, Any]]) -> None:
        self.series = series
        self.calls: list[tuple[str, str]] = []
        self.offline = False

    def daily_bars(self, provider_symbol: str, period: str) -> dict[str, Any]:
        self.calls.append((provider_symbol, period))
        if self.offline:
            raise RuntimeError("synthetic outage")
        if provider_symbol not in self.series:
            raise UnsupportedSymbolError(f"{provider_symbol} was not found")
        payload = self.series[provider_symbol]
        bars = payload["bars"] if period == "10y" else payload["bars"][-5:]
        return {"meta": payload["meta"], "bars": bars}


QUARTER_STARTS = ("01-01", "04-01", "07-01", "10-01")
QUARTER_ENDS = ("03-31", "06-30", "09-30", "12-31")


def _fact(start: str | None, end: str, value: float, form: str) -> dict[str, Any]:
    filed = (date.fromisoformat(end) + timedelta(days=40)).isoformat()
    row = {"end": end, "val": value, "form": form, "filed": filed, "accn": f"0000-{end}"}
    if start:
        row["start"] = start
    return row


def synthetic_company_facts(last_year: int = 2026, last_quarter: int = 2) -> dict[str, Any]:
    """Calendar-year filer shaped like SEC company facts.

    Quarter n (counting from 2021 Q1) has revenue 100 + 5n, net income 10 + n,
    operating income 15 + n, gross profit 40 + 2n, depreciation 3, operating cash
    flow 20 + n, and capex 5. Like real 10-Qs, income items are filed for the quarter
    and year to date, cash-flow items only year to date, and Q4 only inside the 10-K.
    2021 revenue uses the older SalesRevenueNet concept. A 2:1 split doubles the
    share count from mid-2024.
    """
    facts: dict[str, dict[str, Any]] = {"us-gaap": {}, "dei": {}}

    def add(taxonomy: str, concept: str, unit: str, row: dict[str, Any]) -> None:
        facts[taxonomy].setdefault(concept, {"units": {unit: []}})["units"][unit].append(row)

    for year in range(2021, last_year + 1):
        quarters = 4 if year < last_year else last_quarter
        totals: dict[str, float] = {}
        for quarter in range(quarters):
            n = (year - 2021) * 4 + quarter
            start, end = f"{year}-{QUARTER_STARTS[quarter]}", f"{year}-{QUARTER_ENDS[quarter]}"
            form = "10-K" if quarter == 3 else "10-Q"
            values = {
                "revenue": 100 + 5 * n,
                "NetIncomeLoss": 10 + n,
                "OperatingIncomeLoss": 15 + n,
                "GrossProfit": 40 + 2 * n,
                "DepreciationDepletionAndAmortization": 3,
                "NetCashProvidedByUsedInOperatingActivities": 20 + n,
                "PaymentsToAcquirePropertyPlantAndEquipment": 5,
            }
            for name, value in values.items():
                totals[name] = totals.get(name, 0) + value
                concept = name
                if name == "revenue":
                    concept = (
                        "SalesRevenueNet"
                        if year == 2021
                        else "RevenueFromContractWithCustomerExcludingAssessedTax"
                    )
                cash_flow = name in {
                    "NetCashProvidedByUsedInOperatingActivities",
                    "PaymentsToAcquirePropertyPlantAndEquipment",
                }
                if quarter < 3 and not cash_flow:
                    add("us-gaap", concept, "USD", _fact(start, end, value, form))
                if quarter > 0 or cash_flow:
                    add("us-gaap", concept, "USD", _fact(f"{year}-01-01", end, totals[name], form))
            for concept, value in (
                ("CashAndCashEquivalentsAtCarryingValue", 200),
                ("ShortTermInvestments", 50),
                ("LongTermDebt", 300),
                ("StockholdersEquity", 400),
            ):
                add("us-gaap", concept, "USD", _fact(None, end, value, form))
            cover = (date.fromisoformat(end) + timedelta(days=30)).isoformat()
            shares = 500 if end < "2024-06-30" else 1000
            add("dei", "EntityCommonStockSharesOutstanding", "shares", _fact(None, cover, shares, form))
    return {"cik": 1234, "entityName": "ACME CORP", "facts": facts}


FORM4_XML = """<?xml version="1.0"?>
<ownershipDocument>
  <periodOfReport>2026-10-01</periodOfReport>
  <aff10b5One>{plan}</aff10b5One>
  <issuer><issuerCik>0000001234</issuerCik><issuerTradingSymbol>ACME</issuerTradingSymbol></issuer>
  <reportingOwner>
    <reportingOwnerId><rptOwnerCik>0000009999</rptOwnerCik><rptOwnerName>{owner}</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship><isDirector>0</isDirector><isOfficer>1</isOfficer><officerTitle>{title}</officerTitle></reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <securityTitle><value>Common Stock</value></securityTitle>
      <transactionDate><value>{day}</value></transactionDate>
      <transactionCoding><transactionFormType>4</transactionFormType><transactionCode>{code}</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>{shares}</value></transactionShares>
        <transactionPricePerShare><value>{price}</value><footnoteId id="F1"/></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>{direction}</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
      <postTransactionAmounts><sharesOwnedFollowingTransaction><value>5000</value></sharesOwnedFollowingTransaction></postTransactionAmounts>
      <ownershipNature><directOrIndirectOwnership><value>D</value></directOrIndirectOwnership></ownershipNature>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
  <footnotes><footnote id="F1">{footnote}</footnote></footnotes>
</ownershipDocument>
"""


def form4(
    *,
    owner: str,
    title: str,
    day: str,
    code: str,
    shares: int,
    price: float,
    plan: str = "0",
    footnote: str = "",
) -> str:
    direction = "A" if code in {"P", "A", "M"} else "D"
    return FORM4_XML.format(
        owner=owner,
        title=title,
        day=day,
        code=code,
        shares=shares,
        price=price,
        direction=direction,
        plan=plan,
        footnote=footnote or "Weighted average price.",
    )


SIC_FEED = """<?xml version="1.0" encoding="ISO-8859-1" ?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Companies in SIC 3674</title>
  {entries}
</feed>
"""


class FakeSec:
    """In-memory SEC EDGAR with the same method surface as SecClient."""

    def __init__(self) -> None:
        self.tickers = [
            {"ticker": "BIGCO", "cik": 1111, "title": "BIG CO"},
            {"ticker": "ACME", "cik": 1234, "title": "ACME CORP"},
            {"ticker": "PEER", "cik": 2222, "title": "PEER INC"},
            {"ticker": "BRK-B", "cik": 1067983, "title": "BERKSHIRE HATHAWAY INC"},
            {"ticker": "SMALL", "cik": 3333, "title": "SMALL CO"},
            {"ticker": "VOO", "cik": 4444, "title": "VANGUARD INDEX FUNDS"},
        ]
        filings = [
            ("2026-10-03", "0001-26-000010", "xslF345X05/form4.xml", "4"),
            ("2026-09-20", "0001-26-000009", "xslF345X05/form4.xml", "4"),
            ("2026-09-15", "0001-26-000008", "xslF345X05/form4.xml", "4"),
            ("2026-09-01", "0001-26-000007", "broken.xml", "4"),
            ("2026-08-05", "0001-26-000006", "acme-10q.htm", "10-Q"),
            ("2026-03-01", "0001-26-000005", "xslF345X05/form4.xml", "4"),
        ]
        self.submissions_by_cik: dict[int, dict[str, Any]] = {
            1234: {
                "cik": "1234",
                "name": "ACME CORP",
                "sic": "3674",
                "sicDescription": "Semiconductors & Related Devices",
                "fiscalYearEnd": "1231",
                "filings": {
                    "recent": {
                        "filingDate": [row[0] for row in filings],
                        "accessionNumber": [row[1] for row in filings],
                        "primaryDocument": [row[2] for row in filings],
                        "form": [row[3] for row in filings],
                        "reportDate": ["", "", "", "", "2026-06-30", ""],
                    }
                },
            },
            2222: {"cik": "2222", "name": "PEER INC", "sic": "3674", "filings": {"recent": {}}},
        }
        self.facts_by_cik = {1234: synthetic_company_facts(), 2222: synthetic_company_facts()}
        self.documents = {
            "0001-26-000010": form4(
                owner="Jane Doe", title="CFO", day="2026-10-01", code="P", shares=1000, price=50
            ),
            "0001-26-000009": form4(
                owner="John Roe", title="CEO", day="2026-09-18", code="S", shares=2000, price=60, plan="1"
            ),
            "0001-26-000008": form4(
                owner="Ann Poe",
                title="General Counsel",
                day="2026-09-12",
                code="S",
                shares=500,
                price=58,
                footnote="Sold under a Rule 10b5-1 trading plan adopted May 1.",
            ),
            "0001-26-000005": form4(
                owner="Old Seller", title="COO", day="2026-02-27", code="S", shares=9, price=9
            ),
        }
        self.sic = {"3674": [1111, 9999, 1234, 3333, 2222]}
        self.calls: list[tuple[str, Any]] = []
        self.offline = False

    def _call(self, name: str, argument: Any = None) -> None:
        self.calls.append((name, argument))
        if self.offline:
            raise RuntimeError("synthetic SEC outage")

    def company_tickers(self) -> list[dict[str, Any]]:
        self._call("tickers")
        return list(self.tickers)

    def submissions(self, cik: int) -> dict[str, Any]:
        self._call("submissions", cik)
        return self.submissions_by_cik[cik]

    def company_facts(self, cik: int) -> dict[str, Any]:
        self._call("facts", cik)
        return self.facts_by_cik[cik]

    def filing_document(self, cik: int, accession: str, document: str) -> str:
        self._call("document", (accession, document))
        if document != "form4.xml" or accession not in self.documents:
            raise RuntimeError("document unavailable")
        return self.documents[accession]

    def companies_by_sic(self, sic: str) -> list[int]:
        self._call("sic", sic)
        return list(self.sic.get(sic, []))
