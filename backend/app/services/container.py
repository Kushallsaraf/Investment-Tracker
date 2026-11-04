"""One place that wires repositories and services, shared by the web API and the MCP server."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import settings
from app.database import Database
from app.journal_repository import JournalRepository
from app.market_repository import MarketRepository
from app.providers.sec import SecClient
from app.repository import PortfolioRepository
from app.sec_repository import SecRepository
from app.services.activities import ActivityService
from app.services.analytics import AnalyticsService
from app.services.exit_plans import ExitPlanService
from app.services.fundamentals import FundamentalsService
from app.services.insiders import InsiderService
from app.services.journal import JournalService
from app.services.market import MarketService
from app.services.peers import PeerService
from app.services.portfolio import PortfolioService
from app.services.research import ResearchService
from app.services.sec_data import SecDataService
from app.services.sectors import SectorService


@dataclass(frozen=True)
class Services:
    database: Database
    portfolio_repository: PortfolioRepository
    journal_repository: JournalRepository
    portfolio: PortfolioService
    sectors: SectorService
    activities: ActivityService
    analytics: AnalyticsService
    research: ResearchService
    market: MarketService
    journal: JournalService
    exit_plans: ExitPlanService
    fundamentals: FundamentalsService
    insiders: InsiderService
    peers: PeerService


def build_services(
    database: Database | None = None,
    *,
    history: Any = None,
    prices: Any = None,
    sec_client: Any = None,
) -> Services:
    """Build every service on one database. Tests pass fake providers; the app uses the real ones."""
    database = database or Database()
    portfolio_repository = PortfolioRepository(database)
    journal_repository = JournalRepository(database)
    sectors = SectorService(portfolio_repository)
    market = MarketService(MarketRepository(database), provider=history)
    journal = JournalService(journal_repository, portfolio_repository, market=market)
    sec_repository = SecRepository(database)
    sec = SecDataService(sec_repository, sec_client or SecClient(settings.sec_user_agent))
    fundamentals = FundamentalsService(sec, market)
    return Services(
        database=database,
        portfolio_repository=portfolio_repository,
        journal_repository=journal_repository,
        portfolio=PortfolioService(portfolio_repository, price_provider=prices),
        sectors=sectors,
        activities=ActivityService(portfolio_repository),
        analytics=AnalyticsService(portfolio_repository, sectors),
        research=ResearchService(journal_repository, portfolio_repository, sectors),
        market=market,
        journal=journal,
        exit_plans=ExitPlanService(journal_repository, journal),
        fundamentals=fundamentals,
        insiders=InsiderService(sec, market),
        peers=PeerService(sec, market, fundamentals, sec_repository),
    )
