"""Cached access to SEC EDGAR: ticker-to-CIK mapping, filings, financial facts, and Form 4s."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from app.providers.sec import SecClientProtocol
from app.sec_repository import SecRepository
from app.services.fundamentals import extract_financials
from app.services.insiders import parse_form4

TICKERS_TTL = timedelta(days=7)
SUBMISSIONS_TTL = timedelta(hours=12)
FINANCIALS_TTL = timedelta(hours=24)
SIC_TTL = timedelta(days=30)


class SecFilerNotFoundError(KeyError):
    """The symbol has no SEC filer in the published ticker list."""


class SecDataService:
    def __init__(
        self,
        repository: SecRepository,
        client: SecClientProtocol,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.client = client
        self.clock = clock or (lambda: datetime.now(UTC))
        self._index: tuple[str, dict[str, dict[str, Any]], dict[int, dict[str, Any]]] | None = None

    def _cached(self, key: str, ttl: timedelta | None, loader: Callable[[], Any]) -> tuple[Any, str, bool]:
        """Return (payload, fetched_at, stale); serve an expired copy only if a refresh fails."""
        cached = self.repository.cached(key)
        now = self.clock()
        if cached and (ttl is None or now - datetime.fromisoformat(cached[0]) < ttl):
            return cached[1], cached[0], False
        try:
            payload = loader()
        except Exception:
            if cached is None:
                raise
            return cached[1], cached[0], True
        fetched_at = now.isoformat()
        self.repository.store(key, payload, fetched_at)
        return payload, fetched_at, False

    def _ticker_index(self) -> tuple[dict[str, dict[str, Any]], dict[int, dict[str, Any]]]:
        rows, fetched_at, _ = self._cached("tickers", TICKERS_TTL, self.client.company_tickers)
        if self._index is None or self._index[0] != fetched_at:
            by_ticker: dict[str, dict[str, Any]] = {}
            by_cik: dict[int, dict[str, Any]] = {}
            # SEC lists a company's main class first; keep that one per CIK. The file order is
            # used later only as an approximate size ranking for peer suggestions.
            for rank, row in enumerate(rows):
                entry = {**row, "rank": rank}
                by_ticker.setdefault(row["ticker"], entry)
                by_cik.setdefault(int(row["cik"]), entry)
            self._index = (fetched_at, by_ticker, by_cik)
        return self._index[1], self._index[2]

    def company(self, symbol: str) -> dict[str, Any]:
        by_ticker, _ = self._ticker_index()
        # SEC writes class shares with a hyphen (BRK-B); the app uses a dot (BRK.B).
        entry = by_ticker.get(symbol.replace(".", "-"))
        if entry is None:
            raise SecFilerNotFoundError(f"{symbol} is not in SEC's list of company tickers")
        return entry

    def ticker_for_cik(self, cik: int) -> dict[str, Any] | None:
        _, by_cik = self._ticker_index()
        return by_cik.get(int(cik))

    def submissions(self, cik: int) -> tuple[dict[str, Any], str, bool]:
        return self._cached(f"submissions:{int(cik)}", SUBMISSIONS_TTL, lambda: self.client.submissions(cik))

    def financials(self, cik: int) -> tuple[dict[str, Any], str, bool]:
        return self._cached(
            f"financials:{int(cik)}",
            FINANCIALS_TTL,
            lambda: extract_financials(self.client.company_facts(cik)),
        )

    def form4(self, cik: int, accession: str, document: str) -> dict[str, Any]:
        # Filed documents never change, so parsed Form 4s are cached without expiry.
        payload, _, _ = self._cached(
            f"form4:{accession}",
            None,
            lambda: parse_form4(self.client.filing_document(cik, accession, document)),
        )
        return payload

    def sic_ciks(self, sic: str) -> list[int]:
        payload, _, _ = self._cached(f"sic:{sic}", SIC_TTL, lambda: self.client.companies_by_sic(sic))
        return [int(cik) for cik in payload]
