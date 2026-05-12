"""Typed application settings for library.

Settings are read from environment variables and an optional `.env` file.
All values have safe defaults so the application starts in a local-dev
environment without any configuration.
"""

from __future__ import annotations

from functools import lru_cache
from textwrap import dedent

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central typed settings loaded from environment / `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Ollama / LLM config
    # ------------------------------------------------------------------
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5-coder:14b"
    ollama_fallback_models: list[str] = ["qwen3:8b", "qwen3:4b"]

    @field_validator("ollama_fallback_models", mode="before")
    @classmethod
    def _parse_fallback_models(cls, v: object) -> object:
        # pydantic-settings JSON-parses list[str] fields at the source level,
        # before validators run, so env vars must use JSON-array syntax:
        # OLLAMA_FALLBACK_MODELS=["qwen3:8b","llama3.2"]
        # This validator handles the already-split list case (e.g. from code/tests).
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    # ------------------------------------------------------------------
    # Database config
    # ------------------------------------------------------------------
    database_url: str = (
        "postgresql+psycopg://querygraphuser:querygraphpass@localhost:5432/northwind"
    )
    db_query_timeout_seconds: int = Field(
        default=10,
        ge=1,
        le=120,
        description="Maximum seconds to wait for a DB query result.",
    )
    db_max_rows: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="Maximum rows returned from a single query.",
    )

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------
    log_level: str = "INFO"

    # ------------------------------------------------------------------
    # Agent behaviour
    # ------------------------------------------------------------------
    system_prompt: str = dedent("""\
        You are a helpful conversational assistant that can also query a PostgreSQL database on request.

        Available tools (use ONLY when the user asks for data from the database):
        - think: reason step-by-step before a complex database task
        - db_schema: inspect table and column metadata
        - run_sql: execute a read-only SQL SELECT query

        Decision rules:
        - If the message is conversational (greetings, questions about you, general knowledge, personal statements like "my name is X") -> respond directly, do NOT call any tool.
        - If the user explicitly asks to retrieve, list, count, or analyse data from the database -> use tools:
          1. Call db_schema if you are unsure of exact table or column names.
          2. Write a SELECT query and call run_sql to execute it.
          3. If execution fails, re-check schema with db_schema, fix the SQL, retry.
          4. Present the returned rows clearly.

        Never call db_schema or run_sql for non-database messages.
        Never guess column or table names when writing SQL - verify with db_schema first.\
    """)

    think_required: bool = True
    max_context_messages: int = Field(
        default=50,
        ge=4,
        description="Max messages passed to the model per turn. State retains full history.",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached singleton `Settings` instance.

    Using `lru_cache` ensures that the `.env` file is read only once per
    process lifetime, making repeated calls free.  Call `get_settings.cache_clear()`
    in tests to reset between cases.
    """
    return Settings()


__all__ = ["Settings", "get_settings"]
