"""Runtime configuration from environment (no hardcoded secrets)."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _load_env_files() -> None:
    """Populate os.environ before Settings() — supports CWD-independent paths and `env.local ` typos."""
    root = _project_root()
    load_dotenv(root / ".env", encoding="utf-8")
    load_dotenv(root / "env.local", encoding="utf-8", override=True)
    stray = root / "env.local "
    if stray.is_file():
        load_dotenv(stray, encoding="utf-8", override=True)


_load_env_files()


class Settings(BaseSettings):
    # Absolute paths so keys load when CWD is `ui/` or elsewhere (e.g. Streamlit).
    # case_sensitive=False matches `open_api` in env.local and `OPEN_API` in the shell.
    model_config = SettingsConfigDict(
        env_file=(
            _project_root() / ".env",
            _project_root() / "env.local",
        ),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Env names: OPENAI_API_KEY, OPEN_API, plus lowercase from `env.local` (dotenv) when case_sensitive=False.
    openai_api_key: str | None = None
    open_api: str | None = None

    underwriting_config_dir: Path = Field(
        default_factory=lambda: _project_root() / "config",
        alias="UNDERWRITING_CONFIG_DIR",
    )
    ml_model_path: str | None = Field(default=None, alias="ML_MODEL_PATH")
    extraction_model: str | None = Field(default=None, alias="EXTRACTION_MODEL")

    credit_use_mock: bool = Field(default=True, alias="CREDIT_USE_MOCK")
    transunion_base_url: str | None = Field(default=None, alias="TRANSUNION_BASE_URL")
    transunion_api_key: str | None = Field(default=None, alias="TRANSUNION_API_KEY")
    experian_base_url: str | None = Field(default=None, alias="EXPERIAN_BASE_URL")
    experian_api_key: str | None = Field(default=None, alias="EXPERIAN_API_KEY")

    langchain_tracing_v2: bool = Field(default=False, alias="LANGCHAIN_TRACING_V2")
    langchain_api_key: str | None = Field(default=None, alias="LANGCHAIN_API_KEY")
    langchain_project: str | None = Field(default=None, alias="LANGCHAIN_PROJECT")

    kafka_bootstrap_servers: str | None = Field(default=None, alias="KAFKA_BOOTSTRAP_SERVERS")

    def resolved_openai_key(self) -> str:
        key = (
            self.openai_api_key
            or self.open_api
            or os.environ.get("OPENAI_API_KEY")
            or os.environ.get("OPEN_API")
            or os.environ.get("open_api")
            or ""
        )
        key = key.strip()
        if not key:
            msg = "Set OPENAI_API_KEY or OPEN_API for LLM extraction."
            raise RuntimeError(msg)
        return key


settings = Settings()
