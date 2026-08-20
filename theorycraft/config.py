from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM
    model: str = Field(default="claude-sonnet-4-6", alias="THEORYCRAFT_MODEL")
    anthropic_api_key: Optional[str] = Field(default=None, alias="ANTHROPIC_API_KEY")
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")

    # Langfuse
    langfuse_public_key: Optional[str] = Field(default=None, alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: Optional[str] = Field(default=None, alias="LANGFUSE_SECRET_KEY")
    langfuse_host: str = Field(default="https://cloud.langfuse.com", alias="LANGFUSE_HOST")

    # GitHub
    github_token: Optional[str] = Field(default=None, alias="GITHUB_TOKEN")
    github_app_id: Optional[str] = Field(default=None, alias="GITHUB_APP_ID")
    github_app_private_key_path: Optional[str] = Field(default=None, alias="GITHUB_APP_PRIVATE_KEY_PATH")
    github_org: Optional[str] = Field(default=None, alias="GITHUB_ORG")

    # Notifications
    slack_webhook_url: Optional[str] = Field(default=None, alias="SLACK_WEBHOOK_URL")
    generic_webhook_url: Optional[str] = Field(default=None, alias="GENERIC_WEBHOOK_URL")

    # Sessions
    sessions_dir: Path = Field(default=Path.home() / ".theorycraft" / "sessions", alias="THEORYCRAFT_SESSIONS_DIR")
    output_dir: Path = Field(default=Path.cwd(), alias="THEORYCRAFT_OUTPUT_DIR")

    # Graph limits
    max_clarify_rounds: int = Field(default=2, alias="THEORYCRAFT_MAX_CLARIFY_ROUNDS")
    max_revisions: int = Field(default=3, alias="THEORYCRAFT_MAX_REVISIONS")

    @field_validator("sessions_dir", "output_dir", mode="before")
    @classmethod
    def expand_path(cls, v: str | Path) -> Path:
        return Path(v).expanduser().resolve()

    @property
    def langfuse_enabled(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)

    @property
    def github_enabled(self) -> bool:
        return bool(self.github_token or (self.github_app_id and self.github_app_private_key_path))

    @property
    def github_auth_mode(self) -> str:
        if self.github_app_id and self.github_app_private_key_path:
            return "app"
        return "pat"

    @property
    def slack_enabled(self) -> bool:
        return bool(self.slack_webhook_url)

    @property
    def webhook_enabled(self) -> bool:
        return bool(self.generic_webhook_url)

    def ensure_sessions_dir(self) -> None:
        self.sessions_dir.mkdir(parents=True, exist_ok=True)


class MCPConfig:
    def __init__(self, path: Path = Path(".theorycraft.json")):
        self._data: dict = {}
        if path.exists():
            with open(path) as f:
                self._data = json.load(f)

    @property
    def mcp_servers(self) -> dict:
        return self._data.get("mcp_servers", {})

    @property
    def defaults(self) -> dict:
        return self._data.get("defaults", {})


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
        _settings.ensure_sessions_dir()
    return _settings


def get_mcp_config() -> MCPConfig:
    return MCPConfig()
