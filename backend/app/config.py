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
    fred_api_key: str | None
    ai_provider: str
    ai_model: str
    ollama_url: str
    ai_base_url: str | None
    ai_api_key: str | None

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
            # A free key from fredaccount.stlouisfed.org; macro data stays unavailable without one.
            fred_api_key=os.getenv("FRED_API_KEY", "").strip() or None,
            # The AI analyst runs on Ollama by default; "openai" means any OpenAI-compatible API.
            ai_provider=os.getenv("AI_PROVIDER", "ollama").strip().lower() or "ollama",
            ai_model=os.getenv("AI_MODEL", "").strip() or "qwen2.5:7b",
            ollama_url=os.getenv("OLLAMA_URL", "").strip() or "http://127.0.0.1:11434",
            ai_base_url=os.getenv("AI_BASE_URL", "").strip() or None,
            ai_api_key=os.getenv("AI_API_KEY", "").strip() or None,
        )


settings = Settings.from_environment()
