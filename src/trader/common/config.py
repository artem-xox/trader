"""Application configuration loaded from environment / .env.

All settings are read once into a cached `Settings` instance. LangSmith tracing is
driven by the standard `LANGSMITH_*` environment variables, which LangChain picks up
automatically — they are declared here only so the values live in one place and `.env`
stays the single source of truth.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- LLM ---
    openai_api_key: str = Field(default="", description="OpenAI API key")
    
    # Two tiers: a stronger model for planning (the reasoning step) and a lighter one for
    # the supporting components (skill selection, guard, verifier).
    openai_model_strong: str = Field(
        default="gpt-5.4-mini", description="Model for the planner / responder",
    )
    openai_model_weak: str = Field(
        default="gpt-5.4-nano", description="Model for selector / guard / verifier"
    )
    # LLM-as-judge model for evaluation. Should be at least as capable as the agent; empty
    # falls back to the strong tier (a judge must not be weaker than what it grades).
    openai_model_eval: str = Field(default="", description="Model for eval LLM judges")

    # --- Web search ---
    tavily_api_key: str = Field(default="", description="Tavily API key")

    # --- Telegram ---
    telegram_bot_token: str = Field(
        default="", alias="TELEGRAM_API_TOKEN", description="Telegram bot token"
    )
    # `NoDecode` is load-bearing: for a list field, pydantic-settings JSON-decodes the
    # raw environment value *inside the source*, before any validator runs. So the
    # comma-separated form this validator exists to parse never reached it, and an
    # empty string — what a DigitalOcean env var with no value becomes — crashed the
    # process at import with a bare JSONDecodeError. With NoDecode the string arrives
    # here untouched.
    telegram_allowed_chat_ids: Annotated[list[int], NoDecode] = Field(
        default_factory=list,
        description="Allowlist of chat IDs; empty means allow everyone (dev only)",
    )

    @field_validator("telegram_allowed_chat_ids", mode="before")
    @classmethod
    def _parse_telegram_allowed_chat_ids(cls, value: object) -> list[int]:
        if value is None or value == "":
            return []
        if isinstance(value, int):
            return [value]
        if isinstance(value, list):
            return [int(item) for item in value]
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            # A JSON list was the only form that worked before NoDecode, so one may
            # still be sitting in a dashboard or a .env somewhere.
            if stripped.startswith("["):
                return [int(item) for item in json.loads(stripped)]
            return [int(item.strip()) for item in stripped.split(",") if item.strip()]
        raise TypeError(f"Unsupported chat ID value: {value!r}")

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

    # --- Web UI ---
    # Where the built SPA lives, relative to the working directory. The app serves it
    # when the directory exists and runs API-only when it does not (see app/main.py).
    web_dist_dir: str = Field(default="web/dist", description="Directory of the built web client")

    # --- Observability (LangSmith) ---
    # Standard LangChain vars; declared so they are visible/validated in one spot.
    langsmith_tracing: bool = Field(default=False, alias="LANGSMITH_TRACING")
    langsmith_api_key: str = Field(default="", alias="LANGSMITH_API_KEY")
    langsmith_project: str = Field(default="trader", alias="LANGSMITH_PROJECT")


@lru_cache
def get_settings() -> Settings:
    return Settings()
