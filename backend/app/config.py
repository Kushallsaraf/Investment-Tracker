"""Local-only runtime configuration and private directory creation."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _secure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        path.chmod(0o700)
    except OSError:
        pass
    return path


@dataclass(frozen=True)
class Settings:
    runtime_root: Path
    database_path: Path
    temporary_uploads: Path
    secret_path: Path
    host: str
    port: int
    snaptrade_enabled: bool
    snaptrade_ui_redirect: str
    snaptrade_min_sync_seconds: int

    @classmethod
    def from_environment(cls) -> Settings:
        configured = os.getenv("PORTFOLIO_MANAGER_HOME", "").strip()
        runtime_root = (
            Path(configured).expanduser() if configured else Path.home() / ".canadian-portfolio-manager"
        )
        runtime_root = _secure_directory(runtime_root.resolve())
        return cls(
            runtime_root=runtime_root,
            database_path=runtime_root / "portfolio.sqlite3",
            temporary_uploads=_secure_directory(runtime_root / "tmp" / "imports"),
            secret_path=runtime_root / "local-secret.key",
            host=os.getenv("PORTFOLIO_MANAGER_HOST", "127.0.0.1").strip() or "127.0.0.1",
            port=int(os.getenv("PORTFOLIO_MANAGER_PORT", "8742")),
            snaptrade_enabled=os.getenv("PORTFOLIO_MANAGER_SNAPTRADE_ENABLED", "0").strip()
            in {"1", "true", "TRUE", "yes", "YES"},
            snaptrade_ui_redirect=(
                os.getenv(
                    "PORTFOLIO_MANAGER_SNAPTRADE_REDIRECT",
                    "http://127.0.0.1:5173/?snaptrade=connected",
                ).strip()
                or "http://127.0.0.1:5173/?snaptrade=connected"
            ),
            snaptrade_min_sync_seconds=600,
        )


settings = Settings.from_environment()
