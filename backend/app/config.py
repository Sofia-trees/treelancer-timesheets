"""Runtime settings. Local dev defaults to a SQLite file so the app runs with
zero external services; prod sets DATABASE_URL to Postgres (Render)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TT_", env_file=".env", extra="ignore")

    # SQLite for local dev; override with a Postgres URL in prod.
    database_url: str = f"sqlite:///{(_BACKEND_DIR / 'timesheets.db').as_posix()}"

    # Session-token signing. MUST be overridden in prod.
    jwt_secret: str = "dev-insecure-change-me"
    jwt_ttl_hours: int = 24 * 14

    magic_link_ttl_minutes: int = 20
    frontend_url: str = "http://localhost:5173"

    # When true (local/dev), the login endpoint returns the magic link in the
    # response instead of emailing it, so you can log in without SMTP wired up.
    expose_magic_link: bool = True

    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Idempotent (skips if data already exists) — keeps a demo deploy usable
    # even after a fresh/reset disk, without a manual seed step.
    seed_on_startup: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
