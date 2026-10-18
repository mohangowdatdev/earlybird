"""Settings: every value comes from `EARLYBIRD_*` environment variables or `.env` (ADR 0014)."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EARLYBIRD_", env_file=".env", extra="ignore")

    data_dir: Path = Path("var")
    database_url: str | None = None
    profile_path: Path = Path("profile.yaml")
    registry_path: Path = Path("registry/companies.yaml")

    dataset_repo: str = "mohangowdatdev/earlybird"
    dataset_tag: str = "data-latest"

    portal_host: str = "127.0.0.1"
    portal_port: int = 8765
    sync_interval_minutes: int = 60
    dawn_window_days: int = 3

    # AI (ADR 0017). No key = rules only. Budgets are hard monthly caps in USD.
    anthropic_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("ANTHROPIC_API_KEY", "EARLYBIRD_ANTHROPIC_API_KEY"),
    )
    ai_model: str = "claude-haiku-5-5"
    ai_monthly_budget_usd: float = 5.0
    ai_fit_monthly_budget_usd: float = 2.0
    ai_batch_threshold: int = 150
    ai_max_batch_size: int = 10_000
    ai_concurrency: int = 5

    http_timeout_seconds: float = 20.0
    http_concurrency: int = 16
    log_format: Literal["auto", "console", "json"] = "auto"
    log_level: str = "INFO"

    @property
    def db_url(self) -> str:
        return self.database_url or f"sqlite:///{self.data_dir / 'earlybird.db'}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
