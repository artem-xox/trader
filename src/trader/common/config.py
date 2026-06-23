"""Application configuration loaded from environment / .env.

All settings are read once into a cached `Settings` instance. LangSmith tracing is
driven by the standard `LANGSMITH_*` environment variables, which LangChain picks up
automatically — they are declared here only so the values live in one place and `.env`
stays the single source of truth.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- LLM ---
    openai_api_key: str = Field(default="", description="OpenAI API key")
    openai_model: str = Field(default="gpt-4.1-mini", description="Chat model name")

    # --- Web search ---
    tavily_api_key: str = Field(default="", description="Tavily API key")

    # --- Telegram ---
    telegram_bot_token: str = Field(
        default="", alias="TELEGRAM_API_TOKEN", description="Telegram bot token"
    )
    telegram_allowed_chat_ids: list[int] = Field(
        default_factory=list,
        description="Allowlist of chat IDs; empty means allow everyone (dev only)",
    )

    # --- Agent ---
    agent_max_iterations: int = Field(default=8, description="ReAct loop hard cap")
    agent_app_url: str = Field(
        default="http://127.0.0.1:8000",
        description="Base URL the bot uses to reach the agent HTTP app",
    )
    agent_api_key: str = Field(
        default="",
        description="Shared secret for X-API-Key header; empty = no auth (dev only)",
    )

    # --- Observability (LangSmith) ---
    # Standard LangChain vars; declared so they are visible/validated in one spot.
    langsmith_tracing: bool = Field(default=False, alias="LANGSMITH_TRACING")
    langsmith_api_key: str = Field(default="", alias="LANGSMITH_API_KEY")
    langsmith_project: str = Field(default="trader", alias="LANGSMITH_PROJECT")


@lru_cache
def get_settings() -> Settings:
    return Settings()
