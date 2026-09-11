"""Bank of Canada CAD foreign-exchange provider."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Protocol

import httpx


class FxProvider(Protocol):
    def usd_cad(self) -> dict[str, object]: ...


class BankOfCanadaFxProvider:
    endpoint = "https://www.bankofcanada.ca/valet/observations/FXUSDCAD/json"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self.client = client or httpx.Client(
            timeout=12,
            follow_redirects=True,
            headers={"User-Agent": "Portfolio-Manager/0.1 (+local read-only dashboard)"},
        )

    def usd_cad(self) -> dict[str, object]:
        response = self.client.get(self.endpoint, params={"recent": 10})
        response.raise_for_status()
        observations = (response.json() or {}).get("observations") or []
        usable = [item for item in observations if (item.get("FXUSDCAD") or {}).get("v")]
        if not usable:
            raise RuntimeError("Bank of Canada returned no USD/CAD observation")
        latest = usable[-1]
        rate = Decimal(str(latest["FXUSDCAD"]["v"]))
        if not rate.is_finite() or rate <= 0:
            raise RuntimeError("Bank of Canada returned an invalid USD/CAD rate")
        observed = datetime.fromisoformat(str(latest["d"])).replace(tzinfo=UTC)
        fetched = datetime.now(UTC)
        return {
            "base_currency": "USD",
            "quote_currency": "CAD",
            "rate": format(rate, "f"),
            "observed_at": observed.isoformat(),
            "fetched_at": fetched.isoformat(),
            "source": "Bank of Canada Valet API",
            "source_url": "https://www.bankofcanada.ca/valet-api-how-to/",
            "stale": observed < fetched - timedelta(days=7),
        }
