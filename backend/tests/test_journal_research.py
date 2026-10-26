from __future__ import annotations

from pathlib import Path
from typing import Any

from app.database import Database
from app.importers.wealthsimple import load_or_create_secret
from app.journal_repository import JournalRepository
from app.repository import PortfolioRepository
from app.services.activities import normalize_snaptrade_activity, summarize_activity_preview
from app.services.imports import ImportService
from app.services.journal import JournalService
from app.services.portfolio import PortfolioService
from app.services.research import ResearchService
from app.services.sectors import SectorService


class FixedPrice:
    source = "Synthetic adjusted-safe quote fixture"
    supports_automatic_refresh = False
    automatic_refresh_seconds = None

    def quote(self, instrument: dict[str, Any]) -> dict[str, Any]:
        return {
            "price": "120",
            "currency": instrument["trading_currency"],
            "observed_at": "2026-09-11T14:00:00+00:00",
            "fetched_at": "2026-09-11T14:01:00+00:00",
            "source": self.source,
            "source_url": "https://example.invalid/synthetic",
            "quote_status": "end_of_day",
            "delay_minutes": None,
            "stale": False,
        }


class NoFx:
    def usd_cad(self) -> dict[str, Any]:
        raise AssertionError("CAD fixture must not request FX")


def build_services(
    tmp_path: Path,
) -> tuple[
    PortfolioRepository,
    JournalRepository,
    JournalService,
    ResearchService,
    str,
]:
    database = Database(tmp_path / "journal.sqlite3")
    portfolio_repository = PortfolioRepository(database)
    portfolio_service = PortfolioService(
        portfolio_repository, price_provider=FixedPrice(), fx_provider=NoFx()
    )
    source = tmp_path / "synthetic.csv"
    source.write_text(
        "Account Type,Account Number,Symbol,Security Name,Security Type,"
        "Exchange,Currency,Quantity,Average Cost\n"
        "TFSA,SYNTHETIC-ONLY,ACME,Acme Inc.,Stock,TSX,CAD,2,50\n",
        encoding="utf-8",
    )
    preview = ImportService(portfolio_repository).preview(source)
    snapshot_id = ImportService(portfolio_repository).confirm(
        preview["draft_id"], accept_warnings=True
    )
    portfolio_service.refresh(snapshot_id)
    holding = portfolio_repository.latest_portfolio()["holdings"][0]
    journal_repository = JournalRepository(database)
    journal = JournalService(journal_repository, portfolio_repository)
    sectors = SectorService(portfolio_repository)
    research = ResearchService(journal_repository, portfolio_repository, sectors)
    return portfolio_repository, journal_repository, journal, research, holding["instrument_id"]


def test_decision_history_is_append_only_and_ai_cannot_overwrite_it(tmp_path: Path) -> None:
    _portfolio, repository, journal, research, instrument_id = build_services(tmp_path)
    journal.save_decision(
        instrument_id,
        {"decision": "HOLD", "decision_date": "2026-09-10", "reason": "Synthetic reason"},
    )
    journal.save_decision(
        instrument_id,
        {
            "decision": "CONSIDER_REDUCE",
            "decision_date": "2026-09-11",
            "reason": "Review concentration",
        },
    )
    before = repository.decisions()[0]["decision"]
    research.save_ai_review(
        instrument_id,
        {
            "review_date": "2026-09-11",
            "evidence_as_of": "2026-09-10",
            "suggestion": "CONSIDER_EXIT",
            "disposition": "CONSIDERING",
            "original_markdown": "# Synthetic Claude response",
        },
    )
    assert repository.decisions()[0]["decision"] == before == "CONSIDER_REDUCE"
    history = repository.decision_history(instrument_id)
    assert len(history) == 2
    assert history[0]["previous_decision"] == "HOLD"
    assert history[1]["previous_decision"] is None


def test_trigger_creates_local_alert_and_freezes_snapshot_without_external_action(tmp_path: Path) -> None:
    portfolio, repository, journal, _research, instrument_id = build_services(tmp_path)
    journal.create_trigger(
        instrument_id,
        {
            "trigger_type": "PRICE_ABOVE",
            "upper_value": "100",
            "reason": "Synthetic review threshold",
        },
    )
    trigger = repository.triggers(instrument_id)[0]
    latest = portfolio.latest_portfolio()
    assert trigger["state"] == "TRIGGERED"
    assert trigger["observed_value"] == "120"
    assert trigger["frozen_holding_snapshot_id"] == latest["holding_snapshot_id"]
    assert trigger["frozen_valuation_snapshot_id"] == latest["valuation_snapshot_id"]
    assert "no order" in repository.alerts()[0]["message"].lower()


def test_review_pack_privacy_and_missing_evidence_are_explicit(tmp_path: Path) -> None:
    _portfolio, _repository, journal, research, instrument_id = build_services(tmp_path)
    journal.save_profile(
        instrument_id,
        {
            "portfolio_role": "SPECULATIVE",
            "thesis_strength": 3,
            "why_owned": "Synthetic thesis",
            "supporting_evidence": "Synthetic only",
            "principal_risks": "Synthetic risk",
            "invalidation_conditions": "Synthetic invalidation",
            "maximum_weight": "0.1",
            "source_links": [],
        },
    )
    prompt = research.prompts()[0]
    pack = research.generate_pack(
        instrument_id=instrument_id,
        prompt_id=prompt["id"],
        trigger_id=None,
        privacy={
            "weights_only": True,
            "include_quantities": False,
            "include_dollar_values": False,
            "include_account_type": False,
        },
        save=False,
    )
    markdown = pack["markdown"]
    assert "Quantity:" not in markdown
    assert "Average cost:" not in markdown
    assert "Account type:" not in markdown
    assert "Adjusted total-return performance is not available" in markdown
    assert "Manual copy/export to Claude" in markdown
    assert "No order or brokerage action" in markdown


def test_activity_identity_is_hashed_deterministic_and_changed_records_are_visible(tmp_path: Path) -> None:
    secret = load_or_create_secret(tmp_path / "local.key")
    raw = {
        "id": "RAW-EXTERNAL-ID-MUST-NOT-BE-STORED",
        "type": "DIVIDEND",
        "symbol": {"symbol": "XIC", "exchange": {"suffix": ".TO"}},
        "trade_date": "2026-06-30T00:00:00Z",
        "amount": "10",
        "currency": {"code": "CAD"},
    }
    first, warnings = normalize_snaptrade_activity(
        raw,
        account_fingerprint="LOCAL-HASH",
        local_secret=secret,
        source_as_of="2026-09-10T00:00:00Z",
    )
    changed, _ = normalize_snaptrade_activity(
        {**raw, "amount": "11"},
        account_fingerprint="LOCAL-HASH",
        local_secret=secret,
        source_as_of="2026-09-10T00:00:00Z",
    )
    assert warnings == []
    assert first["activity_key"] == changed["activity_key"]
    assert first["record_hash"] != changed["record_hash"]
    assert raw["id"] not in str(first)
    refreshed, _ = normalize_snaptrade_activity(
        raw,
        account_fingerprint="LOCAL-HASH",
        local_secret=secret,
        source_as_of="2026-09-11T00:00:00Z",
    )
    assert refreshed["record_hash"] == first["record_hash"]
    summary = summarize_activity_preview(
        [changed],
        {changed["activity_key"]: first["record_hash"]},
        accounts=[],
        unsupported_activity_types=set(),
        incomplete=False,
    )
    assert summary["additions"] == 0
    assert summary["changed_records"] == 1
