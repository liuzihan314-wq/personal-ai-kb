"""Application settings loaded from environment variables and ``.env``."""

from functools import lru_cache
import os
from pathlib import Path
from typing import Literal
from tempfile import NamedTemporaryFile

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
    embedding_model: str | None = None
    embedding_base_url: str | None = None
    embedding_api_key: SecretStr | None = Field(default=None, repr=False)

    # V2 authentication is opt-in.  Empty values keep the V1 local, single-
    # user mode unchanged and do not cause the UI to inspect request headers.
    auth_enabled: bool = False
    auth_issuer: str | None = None
    auth_audience: str | None = None
    auth_jwks_url: str | None = None
    auth_role_mapping: str | None = None
    auth_mode: Literal["cloudflare", "local"] = "cloudflare"
    auth_local_users_file: Path = Path("config/local_users.json")

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


def save_local_settings(values: dict[str, str], env_path: Path = Path(".env")) -> None:
    """Persist approved local settings without exposing their values in logs.

    Existing comments and unrelated settings are preserved. This file is local
    only: ``.gitignore`` excludes it from version control.
    """

    if not values:
        return
    for key, value in values.items():
        if not key.startswith("PKB_") or "\n" in value or "\r" in value:
            raise ValueError("配置项格式无效")

    existing = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    pending = dict(values)
    lines: list[str] = []
    for line in existing.splitlines():
        key, separator, _value = line.partition("=")
        normalized_key = key.removeprefix("export ").strip()
        if separator and normalized_key in pending:
            lines.append(f"{normalized_key}={pending.pop(normalized_key)}")
        else:
            lines.append(line)
    lines.extend(f"{key}={value}" for key, value in pending.items())
    content = "\n".join(lines) + "\n"

    env_path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=env_path.parent,
        prefix=".env.",
        delete=False,
    ) as temporary:
        temporary.write(content)
        temporary_path = Path(temporary.name)
    os.chmod(temporary_path, 0o600)
    temporary_path.replace(env_path)
    get_settings.cache_clear()
