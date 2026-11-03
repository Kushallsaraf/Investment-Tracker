from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from app.database import Database
from app.market_repository import MarketRepository
from app.providers.sec import SecClient, SecNotConfiguredError, parse_cik_feed
from app.sec_repository import SecRepository
from app.services.fundamentals import (
    FundamentalsService,
    extract_financials,
    quarterly_series,
    split_adjusted_shares,
)
from app.services.insiders import InsiderService, parse_form4
from app.services.market import MarketService
from app.services.peers import PeerService
from app.services.sec_data import SecDataService, SecFilerNotFoundError
from fakes import SIC_FEED, FakeHistory, FakeSec, form4, listing, synthetic_bars, synthetic_company_facts


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 26, 20, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


def _services(tmp_path: Path):
    database = Database(tmp_path / "sec.sqlite3")
    clock = Clock()
    history = FakeHistory(
        {
            "ACME": {"meta": listing("Acme Corporation"), "bars": synthetic_bars(1000, base=20, step=0.05)},
            "PEER": {"meta": listing("Peer Inc."), "bars": synthetic_bars(1000, base=10, step=0.01)},
            "BIGCO": {"meta": listing("Big Co"), "bars": synthetic_bars(1000)},
            "SPY": {"meta": listing("SPDR S&P 500", instrument_type="ETF"), "bars": synthetic_bars(1000)},
            "VOO": {
                "meta": listing("Vanguard S&P 500 ETF", instrument_type="ETF"),
                "bars": synthetic_bars(1000),
            },
        }
    )
    market = MarketService(MarketRepository(database), provider=history, clock=clock)
    sec_client = FakeSec()
    repository = SecRepository(database)
    sec = SecDataService(repository, sec_client, clock=clock)
    fundamentals = FundamentalsService(sec, market)
    insiders = InsiderService(sec, market)
    peers = PeerService(sec, market, fundamentals, repository)
    return fundamentals, insiders, peers, sec_client, clock, market


def test_quarters_are_derived_from_year_to_date_and_annual_totals() -> None:
    model = extract_financials(synthetic_company_facts())
    revenue = model["flows"]["revenue"]["quarters"]
    assert len(revenue) == 22
    assert revenue[0][:3] == ["2021-01-01", "2021-03-31", 100.0]
    assert revenue[3][:3] == ["2021-10-01", "2021-12-31", 115.0]
    assert revenue[3][4] is True
    cash_flow = model["flows"]["operating_cash_flow"]["quarters"]
    assert [row[2] for row in cash_flow[-4:]] == [38.0, 39.0, 40.0, 41.0]
    assert [row[1] for row in model["flows"]["revenue"]["annual"]][-1] == "2025-12-31"


def test_q4_falls_back_to_annual_minus_three_quarters() -> None:
    rows = [
        {
            "start": "2025-01-01",
            "end": "2025-03-31",
            "val": 10,
            "form": "10-Q",
            "filed": "2025-05-01",
            "priority": 0,
        },
        {
            "start": "2025-04-01",
            "end": "2025-06-30",
            "val": 11,
            "form": "10-Q",
            "filed": "2025-08-01",
            "priority": 0,
        },
        {
            "start": "2025-07-01",
            "end": "2025-09-30",
            "val": 12,
            "form": "10-Q",
            "filed": "2025-11-01",
            "priority": 0,
        },
        {
            "start": "2025-01-01",
            "end": "2025-12-31",
            "val": 50,
            "form": "10-K",
            "filed": "2026-02-01",
            "priority": 0,
        },
    ]
    assert quarterly_series(rows)[-1] == ["2025-10-01", "2025-12-31", 17.0, "2026-02-01", True]


def test_split_adjusted_share_counts() -> None:
    points = [
        ["2023-01-31", 500, None],
        ["2023-04-30", 505, None],
        ["2023-07-31", 1010, None],
        ["2023-10-31", 1012, None],
    ]
    assert split_adjusted_shares(points) == [
        ("2023-01-31", 1000.0),
        ("2023-04-30", 1010.0),
        ("2023-07-31", 1010.0),
        ("2023-10-31", 1012.0),
    ]
    reverse = [["2023-01-31", 1000, None], ["2023-04-30", 100, None]]
    assert split_adjusted_shares(reverse) == [("2023-01-31", 100.0), ("2023-04-30", 100.0)]


def test_fundamentals_summary_values_and_valuation_history(tmp_path: Path) -> None:
    fundamentals, _, _, _, _, market = _services(tmp_path)
    data = fundamentals.fundamentals("acme")
    price = market.ensure_history("ACME")[1][-1]["close"]
    assert data["applicable"] is True
    assert data["cik"] == 1234
    assert data["sic_description"] == "Semiconductors & Related Devices"
    assert data["period"]["ttm_end"] == "2026-06-30"
    assert data["ttm"]["revenue"]["value"] == 790.0
    assert data["growth"]["revenue_ttm_yoy"]["value"] == pytest.approx(790 / 710 - 1, abs=1e-6)
    assert data["growth"]["revenue_quarter_yoy"]["value"] == pytest.approx(205 / 185 - 1, abs=1e-6)
    assert data["ttm"]["net_income"]["value"] == 118.0
    assert data["ttm"]["free_cash_flow"]["value"] == 138.0
    assert data["ttm"]["ebitda"]["value"] == pytest.approx(138 + 12)
    assert data["profitability"]["gross_margin"]["value"] == pytest.approx((160 + 2 * 78) / 790, abs=1e-6)
    market_cap = price * 1000
    assert data["valuation"]["market_cap"]["value"] == pytest.approx(market_cap)
    assert data["valuation"]["enterprise_value"]["value"] == pytest.approx(market_cap + 300 - 250)
    assert data["valuation"]["pe_ttm"]["value"] == pytest.approx(market_cap / 118, abs=1e-4)
    assert data["balance_sheet"]["net_cash"]["value"] == -50.0
    band = data["valuation_history"]["ps"]
    assert band["status"] == "available"
    assert band["observations"] >= 8
    assert band["min"] <= band["median"] <= band["max"]
    assert 0 < band["percentile"] <= 1
    assert len(data["annual"]) == 5
    assert data["annual"][-1] == {
        "fiscal_year_end": "2025-12-31",
        "revenue": 100 * 4 + 5 * (16 + 17 + 18 + 19),
        "net_income": 40 + 70,
        "free_cash_flow": 80 + 70 - 20,
    }
    assert data["latest_filing"]["form"] == "10-Q"
    assert data["latest_filing"]["url"].endswith("0001-26-000006-index.htm")


def test_fundamentals_are_cached_and_stale_copies_survive_outages(tmp_path: Path) -> None:
    fundamentals, _, _, sec_client, clock, _ = _services(tmp_path)
    fundamentals.fundamentals("ACME")
    facts_calls = [call for call in sec_client.calls if call[0] == "facts"]
    fundamentals.fundamentals("ACME")
    assert [call for call in sec_client.calls if call[0] == "facts"] == facts_calls
    clock.now += timedelta(hours=25)
    sec_client.offline = True
    data = fundamentals.fundamentals("ACME")
    assert data["stale"] is True
    assert data["ttm"]["revenue"]["value"] == 790.0


def test_etfs_and_unknown_filers_are_explicit(tmp_path: Path) -> None:
    fundamentals, insiders, peers, _, _, _ = _services(tmp_path)
    etf = fundamentals.fundamentals("VOO")
    assert etf["applicable"] is False
    assert "ETFs don't file" in etf["reason"]
    assert insiders.activity("VOO")["applicable"] is False
    assert peers.comparison("SPY")["applicable"] is False
    with pytest.raises(SecFilerNotFoundError):
        fundamentals.sec.company("NOPE")


def test_form4_parsing_and_insider_summary(tmp_path: Path) -> None:
    parsed = parse_form4(form4(owner="Jane Doe", title="CFO", day="2026-10-01", code="P", shares=10, price=5))
    assert parsed["owners"] == [{"name": "Jane Doe", "roles": ["CFO"]}]
    assert parsed["plan_checkbox"] is False
    assert parsed["transactions"][0]["code"] == "P"

    _, insiders, _, sec_client, _, _ = _services(tmp_path)
    activity = insiders.activity("ACME", today=date(2026, 10, 26))
    assert activity["filings"] == 4
    assert activity["summary"] == {
        "purchase_value": 50_000.0,
        "sale_value": 149_000.0,
        "net_value": -99_000.0,
        "buyers": 1,
        "sellers": 2,
        "planned_sale_value": 149_000.0,
        "other_transactions": 0,
    }
    assert [row["owner"] for row in activity["transactions"]] == ["Jane Doe", "John Roe", "Ann Poe"]
    assert activity["transactions"][0]["description"] == "Open-market purchase"
    assert activity["transactions"][1]["planned_10b5_1"] is True
    assert activity["transactions"][2]["planned_10b5_1"] is True
    assert "1 Form 4 filing(s) could not be read" in activity["warnings"][0]
    assert ("document", ("0001-26-000010", "form4.xml")) in sec_client.calls


def test_peers_are_seeded_by_industry_and_editable(tmp_path: Path) -> None:
    _, _, peers, _, _, _ = _services(tmp_path)
    seeded = peers.peer_list("ACME")
    assert seeded["peers"] == ["BIGCO", "PEER", "SMALL"]
    assert seeded["source"] == "SIC"
    assert seeded["sic"] == "3674"

    comparison = peers.comparison("ACME")
    rows = {row["symbol"]: row for row in comparison["rows"]}
    assert rows["ACME"]["available"] is True
    assert rows["PEER"]["revenue_growth"] == pytest.approx(790 / 710 - 1, abs=1e-6)
    assert rows["SMALL"]["available"] is False
    assert rows["ACME"]["return_3m"] is not None

    edited = peers.set_peers("ACME", ["peer", "brk-b", "ACME", "PEER"])
    assert edited["peers"] == ["PEER", "BRK.B"]
    assert edited["source"] == "USER"
    with pytest.raises(ValueError, match="at most 10"):
        peers.set_peers("ACME", [f"P{index}" for index in range(11)])
    assert peers.reset("ACME")["source"] == "SIC"


def test_sec_client_requires_a_contact_and_parses_the_industry_feed() -> None:
    with pytest.raises(SecNotConfiguredError, match="PORTFOLIO_MANAGER_SEC_USER_AGENT"):
        SecClient(None).company_tickers()
    feed = SIC_FEED.format(
        entries="".join(
            f"<entry><content type='text/xml'><company-info><cik>{cik:010d}</cik><name>Co {cik}</name>"
            "</company-info></content></entry>"
            for cik in (320193, 1045810, 320193)
        )
    )
    assert parse_cik_feed(feed) == [320193, 1045810]


def test_stale_share_counts_and_ifrs_filers_are_not_valued(tmp_path: Path) -> None:
    fundamentals, _, _, sec_client, _, _ = _services(tmp_path)
    facts = sec_client.facts_by_cik[1234]["facts"]["dei"]["EntityCommonStockSharesOutstanding"]["units"]
    facts["shares"] = [row for row in facts["shares"] if row["end"] < "2022-01-01"]
    data = fundamentals.fundamentals("ACME")
    assert data["valuation"]["market_cap"]["value"] is None
    assert any("too old to value" in note for note in data["notes"])

    (tmp_path / "ifrs").mkdir()
    ifrs_fundamentals, _, _, ifrs_client, _, _ = _services(tmp_path / "ifrs")
    ifrs_client.facts_by_cik[1234] = {"entityName": "ACME CORP", "facts": {"dei": {}, "ifrs-full": {}}}
    result = ifrs_fundamentals.fundamentals("ACME")
    assert result["applicable"] is False
    assert "foreign filer" in result["reason"]
