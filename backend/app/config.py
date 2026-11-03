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
    host: str
    port: int
    sec_user_agent: str | None

    @classmethod
    def from_environment(cls) -> Settings:
        configured = os.getenv("PORTFOLIO_MANAGER_HOME", "").strip()
        runtime_root = Path(configured).expanduser() if configured else Path.home() / ".portfolio-manager"
        runtime_root = _secure_directory(runtime_root.resolve())
        return cls(
            runtime_root=runtime_root,
            database_path=runtime_root / "portfolio.sqlite3",
            host=os.getenv("PORTFOLIO_MANAGER_HOST", "127.0.0.1").strip() or "127.0.0.1",
            port=int(os.getenv("PORTFOLIO_MANAGER_PORT", "8742")),
            # SEC asks automated clients to identify themselves with a name and contact email.
            sec_user_agent=os.getenv("PORTFOLIO_MANAGER_SEC_USER_AGENT", "").strip() or None,
        )


settings = Settings.from_environment()
