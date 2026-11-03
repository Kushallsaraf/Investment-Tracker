"""Rate-limited, read-only client for SEC EDGAR's free public endpoints."""

from __future__ import annotations

import threading
import time
import xml.etree.ElementTree as ElementTree
from typing import Any, Protocol

import httpx

SEC_SOURCE = "SEC EDGAR"
# SEC allows at most 10 requests per second per client.
MIN_INTERVAL_SECONDS = 0.12


class SecNotConfiguredError(RuntimeError):
    """SEC requires a User-Agent naming the requester and a contact email."""


class SecClientProtocol(Protocol):
    def company_tickers(self) -> list[dict[str, Any]]: ...

    def submissions(self, cik: int) -> dict[str, Any]: ...

    def company_facts(self, cik: int) -> dict[str, Any]: ...

    def filing_document(self, cik: int, accession: str, document: str) -> str: ...

    def companies_by_sic(self, sic: str) -> list[int]: ...


def cik10(cik: int) -> str:
    return f"{int(cik):010d}"


def filing_index_url(cik: int, accession: str) -> str:
    folder = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}"
    return f"{folder}/{accession}-index.htm"


class SecClient:
    def __init__(self, user_agent: str | None, client: httpx.Client | None = None) -> None:
        self.user_agent = user_agent
        self.client = client or httpx.Client(timeout=30, follow_redirects=True)
        self._lock = threading.Lock()
        self._last_request = 0.0

    def _get(self, url: str, params: dict[str, str] | None = None) -> httpx.Response:
        if not self.user_agent:
            raise SecNotConfiguredError(
                "SEC EDGAR needs a contact. Set PORTFOLIO_MANAGER_SEC_USER_AGENT to your name and email."
            )
        with self._lock:
            wait = MIN_INTERVAL_SECONDS - (time.monotonic() - self._last_request)
            if wait > 0:
                time.sleep(wait)
            self._last_request = time.monotonic()
        response = self.client.get(
            url, params=params, headers={"User-Agent": self.user_agent, "Accept-Encoding": "gzip, deflate"}
        )
        response.raise_for_status()
        return response

    def company_tickers(self) -> list[dict[str, Any]]:
        """Return listed companies in the order SEC publishes them."""
        payload = self._get("https://www.sec.gov/files/company_tickers.json").json()
        rows = payload.values() if isinstance(payload, dict) else payload
        return [
            {"ticker": str(row["ticker"]).upper(), "cik": int(row["cik_str"]), "title": str(row["title"])}
            for row in rows
        ]

    def submissions(self, cik: int) -> dict[str, Any]:
        return self._get(f"https://data.sec.gov/submissions/CIK{cik10(cik)}.json").json()

    def company_facts(self, cik: int) -> dict[str, Any]:
        return self._get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10(cik)}.json").json()

    def filing_document(self, cik: int, accession: str, document: str) -> str:
        url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/{document}"
        return self._get(url).text

    def companies_by_sic(self, sic: str) -> list[int]:
        """CIKs of annual-report filers in one SIC industry code, from EDGAR's company browse feed."""
        feed = self._get(
            "https://www.sec.gov/cgi-bin/browse-edgar",
            params={"action": "getcompany", "SIC": sic, "type": "10-K", "count": "100", "output": "atom"},
        ).text
        return parse_cik_feed(feed)


def parse_cik_feed(feed: str) -> list[int]:
    """Collect every <cik> element, ignoring namespaces, so small layout changes still parse."""
    root = ElementTree.fromstring(feed)
    ciks: list[int] = []
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1].lower() == "cik" and (element.text or "").strip().isdigit():
            cik = int(element.text.strip())
            if cik not in ciks:
                ciks.append(cik)
    return ciks
