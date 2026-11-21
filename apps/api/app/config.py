from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    database_url: str = os.getenv(
        "DATABASE_URL", f"sqlite:///{(PROJECT_ROOT / 'data' / 'service_desk.db').as_posix()}"
    )
    llm_provider: str = os.getenv("LLM_PROVIDER", "mock")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    llm_model: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    itsm_provider: str = os.getenv("ITSM_PROVIDER", "mock")
    auth_secret: str = os.getenv("AUTH_SECRET", "local-demo-secret-change-in-production")
    reopen_window_hours: int = _int("REOPEN_WINDOW_HOURS", 72)
    max_agent_steps: int = _int("MAX_AGENT_STEPS", 12)
    rate_limit_per_minute: int = _int("RATE_LIMIT_PER_MINUTE", 120)
    cors_origins: tuple[str, ...] = tuple(
        x.strip()
        for x in os.getenv("CORS_ORIGINS", "http://localhost:3001,http://localhost:5173").split(",")
        if x.strip()
    )

    @property
    def sqlite_path(self) -> Path:
        if not self.database_url.startswith("sqlite:///"):
            raise RuntimeError("The deterministic POC currently requires a sqlite:/// DATABASE_URL")
        raw = self.database_url.removeprefix("sqlite:///")
        return Path(raw) if Path(raw).is_absolute() else PROJECT_ROOT / raw


@lru_cache
def get_settings() -> Settings:
    return Settings()
