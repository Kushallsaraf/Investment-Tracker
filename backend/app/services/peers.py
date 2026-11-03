"""Peer lists seeded from the SEC industry code, editable by the investor, with side-by-side metrics."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from typing import Any

from app.providers.prices import normalize_symbol
from app.providers.sec import SEC_SOURCE

DEFAULT_PEERS = 6
MAX_PEERS = 10


class PeerService:
    def __init__(self, sec: Any, market: Any, fundamentals: Any, repository: Any) -> None:
        self.sec = sec
        self.market = market
        self.fundamentals = fundamentals
        self.repository = repository

    def _seed(self, symbol: str) -> dict[str, Any]:
        company = self.sec.company(symbol)
        submissions, _, _ = self.sec.submissions(company["cik"])
        sic = str(submissions.get("sic") or "").strip()
        description = submissions.get("sicDescription") or None
        if not sic:
            self.repository.save_peer_list(symbol, [], source="SIC")
            return self.repository.peer_list(symbol)
        candidates = []
        for cik in self.sec.sic_ciks(sic):
            entry = self.sec.ticker_for_cik(cik)
            if entry and int(cik) != int(company["cik"]):
                candidates.append(entry)
        # SEC's ticker file lists larger companies first, which approximates "closest in size".
        candidates.sort(key=lambda entry: entry["rank"])
        peers = [entry["ticker"].replace("-", ".") for entry in candidates[:DEFAULT_PEERS]]
        self.repository.save_peer_list(symbol, peers, source="SIC", sic=sic, sic_description=description)
        return self.repository.peer_list(symbol)

    def peer_list(self, symbol: str) -> dict[str, Any]:
        canonical = normalize_symbol(symbol)
        stored = self.repository.peer_list(canonical)
        return stored if stored is not None else self._seed(canonical)

    def set_peers(self, symbol: str, peers: list[str]) -> dict[str, Any]:
        canonical = normalize_symbol(symbol)
        cleaned: list[str] = []
        for peer in peers:
            peer_symbol = normalize_symbol(peer)
            if peer_symbol != canonical and peer_symbol not in cleaned:
                cleaned.append(peer_symbol)
        if len(cleaned) > MAX_PEERS:
            raise ValueError(f"Choose at most {MAX_PEERS} peers")
        self.repository.save_peer_list(canonical, cleaned, source="USER")
        return self.repository.peer_list(canonical)

    def reset(self, symbol: str) -> dict[str, Any]:
        canonical = normalize_symbol(symbol)
        self.repository.delete_peer_list(canonical)
        return self._seed(canonical)

    def _row(self, symbol: str) -> dict[str, Any]:
        try:
            data = self.fundamentals.fundamentals(symbol)
            _, bars, _ = self.market.ensure_history(symbol)
        except Exception as exc:
            return {"symbol": symbol, "available": False, "reason": f"Not available ({type(exc).__name__})"}
        three_months = None
        if bars:
            start = (date.fromisoformat(bars[-1]["date"]) - timedelta(days=92)).isoformat()
            window = [bar for bar in bars if bar["date"] >= start]
            if len(window) > 1 and window[0]["adj_close"] > 0:
                three_months = round(window[-1]["adj_close"] / window[0]["adj_close"] - 1, 6)
        if not data.get("applicable"):
            return {
                "symbol": data["symbol"],
                "name": data["name"],
                "available": False,
                "reason": data.get("reason"),
                "return_3m": three_months,
            }
        return {
            "symbol": data["symbol"],
            "name": data["sec_name"] or data["name"],
            "available": True,
            "market_cap": data["valuation"]["market_cap"]["value"],
            "pe_ttm": data["valuation"]["pe_ttm"]["value"],
            "ps_ttm": data["valuation"]["ps_ttm"]["value"],
            "ev_ebitda": data["valuation"]["ev_ebitda"]["value"],
            "revenue_growth": data["growth"]["revenue_ttm_yoy"]["value"],
            "operating_margin": data["profitability"]["operating_margin"]["value"],
            "return_3m": three_months,
            "ttm_end": data["period"]["ttm_end"],
        }

    def comparison(self, symbol: str) -> dict[str, Any]:
        meta, _, _ = self.market.ensure_history(symbol)
        if meta["asset_type"] == "ETF":
            return {
                "symbol": meta["symbol"],
                "applicable": False,
                "reason": "Peer comparison uses company financials, which ETFs don't file.",
                "source": SEC_SOURCE,
            }
        peers = self.peer_list(meta["symbol"])
        symbols = [meta["symbol"], *peers["peers"]]
        with ThreadPoolExecutor(max_workers=3) as pool:
            rows = list(pool.map(self._row, symbols))
        return {
            "symbol": meta["symbol"],
            "applicable": True,
            "peers": peers["peers"],
            "list_source": peers["source"],
            "sic": peers.get("sic"),
            "sic_description": peers.get("sic_description"),
            "rows": rows,
            "source": f"{SEC_SOURCE} industry code and company facts · prices from daily history",
        }
