"""FastAPI entrypoint for the loopback-only Portfolio Manager application."""

from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import settings
from app.database import Database
from app.integrations.snaptrade import MacOSKeychainCredentialProvider, ReadOnlySnapTradeClient
from app.journal_repository import JournalRepository
from app.repository import PortfolioRepository
from app.schemas import (
    AIReviewCreate,
    ApplySnapTradeSyncRequest,
    ClaudePromptUpsert,
    DecisionUpdate,
    DeleteLocalBrokerageDataRequest,
    DisconnectSnapTradeRequest,
    InvestmentProfileUpdate,
    ReviewPackRequest,
    SectorUpdateRequest,
    TriggerCreate,
)
from app.services.activities import ActivityService
from app.services.analytics import AnalyticsService
from app.services.journal import JournalService
from app.services.portfolio import PortfolioService
from app.services.research import ResearchService
from app.services.sectors import SectorService
from app.services.snaptrade import (
    SnapTradeSyncError,
    SnapTradeSyncRateLimited,
    SnapTradeSyncService,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"


def require_local_write(
    marker: str | None = Header(default=None, alias="X-Portfolio-Manager"),
) -> None:
    if marker != "local-ui":
        raise HTTPException(status_code=403, detail="Missing local write-request marker")


app = FastAPI(
    title="Investment Tracker",
    version="0.3.0",
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
_snaptrade_service = SnapTradeSyncService(
    _repository,
    _portfolio_service,
    ReadOnlySnapTradeClient(MacOSKeychainCredentialProvider()),
    enabled=settings.snaptrade_enabled,
    redirect_uri=settings.snaptrade_ui_redirect,
    local_secret_path=settings.secret_path,
    min_sync_seconds=settings.snaptrade_min_sync_seconds,
)


def portfolio_service() -> PortfolioService:
    return _portfolio_service


def sector_service() -> SectorService:
    return _sector_service


def snaptrade_service() -> SnapTradeSyncService:
    return _snaptrade_service


def activity_service() -> ActivityService:
    return _activity_service


def analytics_service() -> AnalyticsService:
    return _analytics_service


def journal_service() -> JournalService:
    return _journal_service


def research_service() -> ResearchService:
    return _research_service


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


@app.get("/api/snaptrade/status")
def snaptrade_status(service: SnapTradeSyncService = Depends(snaptrade_service)) -> dict:
    return service.status()


@app.post("/api/snaptrade/connection/check", dependencies=[Depends(require_local_write)])
def check_snaptrade_connection(
    service: SnapTradeSyncService = Depends(snaptrade_service),
) -> dict:
    try:
        return service.check_connection()
    except SnapTradeSyncError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/snaptrade/portal", dependencies=[Depends(require_local_write)])
def snaptrade_portal(service: SnapTradeSyncService = Depends(snaptrade_service)) -> dict[str, str]:
    try:
        return {"redirect_uri": service.create_portal()}
    except SnapTradeSyncError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/snaptrade/sync/preview", dependencies=[Depends(require_local_write)])
def preview_snaptrade_sync(service: SnapTradeSyncService = Depends(snaptrade_service)) -> dict:
    try:
        return service.preview_sync()
    except SnapTradeSyncRateLimited as exc:
        raise HTTPException(
            status_code=429,
            detail=str(exc),
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
    except SnapTradeSyncError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/snaptrade/sync/pending")
def pending_snaptrade_sync(service: SnapTradeSyncService = Depends(snaptrade_service)) -> dict:
    return {"preview": service.pending_preview()}


@app.post(
    "/api/snaptrade/sync/{preview_id}/apply",
    dependencies=[Depends(require_local_write)],
)
def apply_snaptrade_sync(
    preview_id: str,
    request: ApplySnapTradeSyncRequest,
    service: SnapTradeSyncService = Depends(snaptrade_service),
) -> dict[str, str]:
    try:
        return {"status": "ok", **service.apply_preview(preview_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, SnapTradeSyncError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.delete(
    "/api/snaptrade/sync/{preview_id}",
    dependencies=[Depends(require_local_write)],
)
def cancel_snaptrade_sync(
    preview_id: str,
    service: SnapTradeSyncService = Depends(snaptrade_service),
) -> dict[str, str]:
    try:
        service.cancel_preview(preview_id)
        return {"status": "deleted"}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/snaptrade/disconnect", dependencies=[Depends(require_local_write)])
def disconnect_snaptrade(
    request: DisconnectSnapTradeRequest,
    service: SnapTradeSyncService = Depends(snaptrade_service),
) -> dict[str, int | str]:
    try:
        return {"status": "disconnect_pending", "connections": service.disconnect()}
    except SnapTradeSyncError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.delete("/api/snaptrade/local-data", dependencies=[Depends(require_local_write)])
def delete_local_brokerage_data(
    request: DeleteLocalBrokerageDataRequest,
    service: SnapTradeSyncService = Depends(snaptrade_service),
) -> dict[str, int | str]:
    return {"status": "deleted", "snapshots": service.delete_local_data()}


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
def brokerage_activity(
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
