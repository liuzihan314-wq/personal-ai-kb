"""Application settings loaded from environment variables and ``.env``."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings that are safe to use across supported platforms."""

    model_config = SettingsConfigDict(
        env_prefix="PKB_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Personal AI Knowledge Base"
    environment: str = "development"
    log_level: str = "INFO"
    data_dir: Path = Path("data")

    # Provider settings are deliberately generic. Concrete adapters decide how
    # to use them; the core never selects a vendor, model, or endpoint.
    ai_provider: str | None = None
    ai_model: str | None = None
    ai_base_url: str | None = None
    ai_api_key: SecretStr | None = Field(default=None, repr=False)

    @property
    def raw_dir(self) -> Path:
        """Return the directory reserved for immutable source material."""

        return self.data_dir / "raw"

    @property
    def notes_dir(self) -> Path:
        """Return the directory reserved for single-document notes."""

        return self.data_dir / "notes"

    @property
    def knowledge_dir(self) -> Path:
        """Return the directory reserved for compiled topic knowledge."""

        return self.data_dir / "knowledge"

    @property
    def index_dir(self) -> Path:
        """Return the directory reserved for local indexes."""

        return self.data_dir / "index"

    @property
    def cache_dir(self) -> Path:
        """Return the directory reserved for local caches."""

        return self.data_dir / "cache"

    @property
    def logs_dir(self) -> Path:
        """Return the directory reserved for local logs."""

        return self.data_dir / "logs"

    @property
    def data_directories(self) -> tuple[Path, ...]:
        """Return the data layout without creating directories or files."""

        return (
            self.raw_dir,
            self.notes_dir,
            self.knowledge_dir,
            self.index_dir,
            self.cache_dir,
            self.logs_dir,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-level settings instance."""

    return Settings()
