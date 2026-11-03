"""FastAPI entrypoint for the loopback-only Portfolio Manager application."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import settings
from app.database import Database
from app.journal_repository import JournalRepository
from app.market_repository import MarketRepository
from app.providers.prices import UnsupportedSymbolError
from app.providers.sec import SecClient, SecNotConfiguredError
from app.repository import PortfolioRepository
from app.schemas import (
    ActivityCreate,
    AIReviewCreate,
    ClaudePromptUpsert,
    DecisionUpdate,
    DeletePortfolioDataRequest,
    InvestmentProfileUpdate,
    LoadDemoRequest,
    PeerUpdate,
    PositionUpsert,
    ReviewPackRequest,
    SectorUpdateRequest,
    TriggerCreate,
    WatchlistAdd,
)
from app.sec_repository import SecRepository
from app.services.activities import ActivityService
from app.services.analytics import AnalyticsService
from app.services.fundamentals import FundamentalsService
from app.services.insiders import InsiderService
from app.services.journal import JournalService
from app.services.market import MarketService
from app.services.peers import PeerService
from app.services.portfolio import PortfolioService
from app.services.research import ResearchService
from app.services.sec_data import SecDataService, SecFilerNotFoundError
from app.services.sectors import SectorService

T = TypeVar("T")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"


def require_local_write(
    marker: str | None = Header(default=None, alias="X-Portfolio-Manager"),
) -> None:
    if marker != "local-ui":
        raise HTTPException(status_code=403, detail="Missing local write-request marker")


app = FastAPI(
    title="Investment Tracker",
    version="0.4.0",
    docs_url="/api/docs",
    redoc_url=None,
)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["127.0.0.1", "localhost", "testserver"],
)

_database = Database()
_repository = PortfolioRepository(_database)
_journal_repository = JournalRepository(_database)
_portfolio_service = PortfolioService(_repository)
_sector_service = SectorService(_repository)
_activity_service = ActivityService(_repository)
_analytics_service = AnalyticsService(_repository, _sector_service)
_journal_service = JournalService(_journal_repository, _repository)
_research_service = ResearchService(_journal_repository, _repository, _sector_service)
_market_service = MarketService(MarketRepository(_database))
_sec_repository = SecRepository(_database)
_sec_data = SecDataService(_sec_repository, SecClient(settings.sec_user_agent))
_fundamentals_service = FundamentalsService(_sec_data, _market_service)
_insider_service = InsiderService(_sec_data, _market_service)
_peer_service = PeerService(_sec_data, _market_service, _fundamentals_service, _sec_repository)

def portfolio_service() -> PortfolioService:
    return _portfolio_service


def sector_service() -> SectorService:
    return _sector_service


def activity_service() -> ActivityService:
    return _activity_service


def analytics_service() -> AnalyticsService:
    return _analytics_service


def journal_service() -> JournalService:
    return _journal_service


def research_service() -> ResearchService:
    return _research_service


def market_service() -> MarketService:
    return _market_service


def fundamentals_service() -> FundamentalsService:
    return _fundamentals_service


def insider_service() -> InsiderService:
    return _insider_service


def peer_service() -> PeerService:
    return _peer_service


def _sec_call(action: Callable[[], T]) -> T:
    """Map SEC EDGAR failures to HTTP errors; price-history failures reuse the market mapping."""
    try:
        return _market_call(action)
    except HTTPException as exc:
        cause = exc.__cause__
        if isinstance(cause, SecNotConfiguredError):
            raise HTTPException(status_code=503, detail=str(cause)) from cause
        if isinstance(cause, SecFilerNotFoundError):
            raise HTTPException(status_code=404, detail=str(cause.args[0])) from cause
        if isinstance(cause, httpx.HTTPError):
            raise HTTPException(
                status_code=502,
                detail=(
                    f"Couldn't reach SEC EDGAR ({type(cause).__name__}). "
                    "Check your network and try again."
                ),
            ) from cause
        raise


def _market_call(action: Callable[[], T]) -> T:
    """Map market-data failures to HTTP errors shared by the market routes."""
    try:
        return action()
    except UnsupportedSymbolError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Market data is unavailable ({type(exc).__name__}); try again later"
        ) from exc


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "storage": str(settings.runtime_root)}


@app.get("/api/portfolio")
def latest_portfolio(service: PortfolioService = Depends(portfolio_service)) -> dict:
    portfolio = service.latest()
    return {"status": "ok" if portfolio else "empty", "portfolio": portfolio}


@app.post("/api/portfolio/refresh", dependencies=[Depends(require_local_write)])
def refresh_portfolio(service: PortfolioService = Depends(portfolio_service)) -> dict[str, str]:
    try:
        return {"status": "ok", "valuation_snapshot_id": service.refresh()}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/prices/capabilities")
def price_capabilities(service: PortfolioService = Depends(portfolio_service)) -> dict:
    return service.price_capabilities()


@app.get("/api/market/strip")
def market_strip(service: MarketService = Depends(market_service)) -> dict:
    return service.market_strip()


@app.get("/api/market/{symbol}/chart")
def market_chart(
    symbol: str,
    period: str = Query(default="1Y", alias="range", max_length=4),
    service: MarketService = Depends(market_service),
) -> dict:
    return _market_call(lambda: service.chart(symbol, period))


@app.get("/api/market/{symbol}/technicals")
def market_technicals(symbol: str, service: MarketService = Depends(market_service)) -> dict:
    return _market_call(lambda: service.technicals(symbol))


@app.get("/api/market/{symbol}/fundamentals")
def market_fundamentals(symbol: str, service: FundamentalsService = Depends(fundamentals_service)) -> dict:
    return _sec_call(lambda: service.fundamentals(symbol))


@app.get("/api/market/{symbol}/insiders")
def market_insiders(
    symbol: str,
    days: int = Query(default=90, ge=7, le=365),
    service: InsiderService = Depends(insider_service),
) -> dict:
    return _sec_call(lambda: service.activity(symbol, days=days))


@app.get("/api/market/{symbol}/peers")
def market_peers(symbol: str, service: PeerService = Depends(peer_service)) -> dict:
    return _sec_call(lambda: service.comparison(symbol))


@app.put("/api/market/{symbol}/peers", dependencies=[Depends(require_local_write)])
def update_market_peers(
    symbol: str, request: PeerUpdate, service: PeerService = Depends(peer_service)
) -> dict:
    _sec_call(lambda: service.set_peers(symbol, request.symbols))
    return _sec_call(lambda: service.comparison(symbol))


@app.delete("/api/market/{symbol}/peers", dependencies=[Depends(require_local_write)])
def reset_market_peers(symbol: str, service: PeerService = Depends(peer_service)) -> dict:
    _sec_call(lambda: service.reset(symbol))
    return _sec_call(lambda: service.comparison(symbol))


@app.get("/api/watchlist")
def watchlist(service: MarketService = Depends(market_service)) -> dict:
    return service.watchlist()


@app.post("/api/watchlist", dependencies=[Depends(require_local_write)])
def add_watchlist_symbol(request: WatchlistAdd, service: MarketService = Depends(market_service)) -> dict:
    return {"status": "ok", "symbol": _market_call(lambda: service.add_to_watchlist(request.symbol))}


@app.delete("/api/watchlist/{symbol}", dependencies=[Depends(require_local_write)])
def remove_watchlist_symbol(symbol: str, service: MarketService = Depends(market_service)) -> dict:
    _market_call(lambda: service.remove_from_watchlist(symbol))
    return {"status": "deleted"}


@app.get("/api/portfolio/status")
def portfolio_status(service: PortfolioService = Depends(portfolio_service)) -> dict:
    return service.status()


@app.post("/api/portfolio/positions", dependencies=[Depends(require_local_write)])
def upsert_portfolio_position(
    request: PositionUpsert,
    service: PortfolioService = Depends(portfolio_service),
) -> dict[str, str]:
    try:
        return {"status": "ok", **service.upsert_position(**request.model_dump())}
    except (UnsupportedSymbolError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Symbol lookup failed ({type(exc).__name__}); try again later"
        ) from exc


@app.post("/api/portfolio/demo", dependencies=[Depends(require_local_write)])
def load_demo_portfolio(
    request: LoadDemoRequest,
    service: PortfolioService = Depends(portfolio_service),
) -> dict[str, str]:
    try:
        return {"status": "ok", **service.load_demo()}
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.delete("/api/portfolio/local-data", dependencies=[Depends(require_local_write)])
def delete_portfolio_data(
    request: DeletePortfolioDataRequest,
    service: PortfolioService = Depends(portfolio_service),
) -> dict[str, int | str]:
    return {"status": "deleted", "snapshots": service.delete_data()}


@app.delete(
    "/api/portfolio/positions/{position_id}",
    dependencies=[Depends(require_local_write)],
)
def remove_portfolio_position(
    position_id: str,
    service: PortfolioService = Depends(portfolio_service),
) -> dict[str, str]:
    try:
        return {"status": "deleted", **service.remove_position(position_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/portfolio/history")
def portfolio_history(
    limit: int = Query(default=180, ge=1, le=1_000),
    service: PortfolioService = Depends(portfolio_service),
) -> dict:
    return {"status": "ok", "history": service.history(limit)}


@app.get("/api/portfolio/sectors")
def portfolio_sectors(service: SectorService = Depends(sector_service)) -> dict:
    analysis = service.latest()
    return {"status": "ok" if analysis else "empty", "analysis": analysis}


@app.get("/api/analytics")
def portfolio_analytics(service: AnalyticsService = Depends(analytics_service)) -> dict:
    return {"status": "ok", "analytics": service.overview()}


@app.get("/api/activity")
def activity_ledger(
    activity_type: str | None = Query(default=None, max_length=40),
    symbol: str | None = Query(default=None, max_length=40),
    start_date: str | None = Query(default=None, max_length=40),
    end_date: str | None = Query(default=None, max_length=40),
    limit: int = Query(default=500, ge=1, le=5_000),
    service: ActivityService = Depends(activity_service),
) -> dict:
    try:
        return {"status": "ok", **service.list(
            activity_type=activity_type,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/activity", dependencies=[Depends(require_local_write)])
def record_activity(
    request: ActivityCreate,
    service: ActivityService = Depends(activity_service),
) -> dict[str, str]:
    try:
        return {"status": "ok", "id": service.record(request.model_dump(mode="json"))}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.delete("/api/activity/{activity_id}", dependencies=[Depends(require_local_write)])
def delete_activity(
    activity_id: str,
    service: ActivityService = Depends(activity_service),
) -> dict[str, str]:
    try:
        service.delete(activity_id)
        return {"status": "deleted"}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/income")
def portfolio_income(service: ActivityService = Depends(activity_service)) -> dict:
    return {"status": "ok", "income": service.income()}


@app.get("/api/journal")
def investment_journal(service: JournalService = Depends(journal_service)) -> dict:
    return {"status": "ok", "journal": service.overview()}


@app.put(
    "/api/journal/instruments/{instrument_id}/profile",
    dependencies=[Depends(require_local_write)],
)
def update_investment_profile(
    instrument_id: str,
    request: InvestmentProfileUpdate,
    service: JournalService = Depends(journal_service),
) -> dict:
    try:
        profile = service.save_profile(instrument_id, request.model_dump(mode="json"))
        return {"status": "ok", "profile": profile}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post(
    "/api/journal/instruments/{instrument_id}/decisions",
    dependencies=[Depends(require_local_write)],
)
def record_investment_decision(
    instrument_id: str,
    request: DecisionUpdate,
    service: JournalService = Depends(journal_service),
) -> dict:
    try:
        history = service.save_decision(instrument_id, request.model_dump(mode="json"))
        return {"status": "ok", "history": history}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post(
    "/api/journal/instruments/{instrument_id}/triggers",
    dependencies=[Depends(require_local_write)],
)
def create_review_trigger(
    instrument_id: str,
    request: TriggerCreate,
    service: JournalService = Depends(journal_service),
) -> dict:
    try:
        trigger = service.create_trigger(instrument_id, request.model_dump(mode="json"))
        return {"status": "ok", "trigger": trigger}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/research/prompts")
def reusable_prompts(service: ResearchService = Depends(research_service)) -> dict:
    return {"status": "ok", "prompts": service.prompts()}


@app.put("/api/research/prompts", dependencies=[Depends(require_local_write)])
def save_reusable_prompt(
    request: ClaudePromptUpsert,
    service: ResearchService = Depends(research_service),
) -> dict:
    try:
        prompt = service.save_prompt(request.id, request.name, request.prompt_text)
        return {"status": "ok", "prompt": prompt}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/research/packs/preview")
def preview_research_pack(
    request: ReviewPackRequest,
    service: ResearchService = Depends(research_service),
) -> dict:
    try:
        pack = service.generate_pack(**request.model_dump(), save=False)
        return {"status": "ok", "pack": pack}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/research/packs/export", dependencies=[Depends(require_local_write)])
def export_research_pack(
    request: ReviewPackRequest,
    service: ResearchService = Depends(research_service),
) -> dict:
    try:
        pack = service.generate_pack(**request.model_dump(), save=True)
        return {"status": "ok", "pack": pack}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/research/reviews")
def saved_ai_reviews(service: ResearchService = Depends(research_service)) -> dict:
    return {"status": "ok", "reviews": service.reviews()}


@app.post("/api/research/reviews", dependencies=[Depends(require_local_write)])
def import_ai_review(
    request: AIReviewCreate,
    service: ResearchService = Depends(research_service),
) -> dict:
    try:
        review = service.save_ai_review(
            request.instrument_id, request.model_dump(mode="json", exclude={"instrument_id"})
        )
        return {"status": "ok", "review": review}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.put(
    "/api/instruments/{instrument_id}/sector",
    dependencies=[Depends(require_local_write)],
)
def update_instrument_sector(
    instrument_id: str,
    request: SectorUpdateRequest,
    service: SectorService = Depends(sector_service),
) -> dict[str, str]:
    try:
        service.update_direct_sector(instrument_id, request.sector)
        return {"status": "ok"}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


if FRONTEND_DIST.exists():
    assets = FRONTEND_DIST / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}")
    def frontend(path: str) -> FileResponse:
        candidate = (FRONTEND_DIST / path).resolve()
        if path and candidate.is_relative_to(FRONTEND_DIST) and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")


def run() -> None:
    import uvicorn

    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    run()
