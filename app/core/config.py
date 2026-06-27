"""Typed application settings, loaded from environment variables / .env.

Everything configurable lives here so there are no magic strings or secrets
scattered through the code. Add new settings as the app grows.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Runtime
    ENV: str = "development"  # development | production

    # Database — Supabase Postgres connection string.
    # Use the SQLAlchemy asyncpg scheme, e.g.
    #   postgresql+asyncpg://postgres:<pwd>@db.<ref>.supabase.co:5432/postgres
    DATABASE_URL: str

    # Auth — Supabase project. We verify access tokens two ways:
    #  * Asymmetric (ES256/RS256) via the project's JWKS endpoint, derived from
    #    SUPABASE_URL — the modern "JWT Signing Keys" path.
    #  * Symmetric (HS256) via SUPABASE_JWT_SECRET — the "Legacy JWT secret".
    # Set BOTH so verification works regardless of which key signs your tokens.
    SUPABASE_URL: str = ""  # e.g. https://<project-ref>.supabase.co
    SUPABASE_JWT_SECRET: str = ""  # Settings → JWT Keys → Legacy JWT Secret
    SUPABASE_JWT_AUDIENCE: str = "authenticated"

    @property
    def jwks_url(self) -> str:
        return self.SUPABASE_URL.rstrip("/") + "/auth/v1/.well-known/jwks.json"

    # AI Coach — Google Gemini (free tier). Server-side only.
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"
    COACH_CACHE_HOURS: int = 12  # how long a generated insight stays fresh

    # LLM provider (provider-agnostic) — powers the AI Coach, NL expense parsing,
    # and push-notification copy. The whole app calls app/services/llm.py; only
    # this config knows about providers. Most providers (Groq, OpenAI, OpenRouter,
    # Together, Fireworks, DeepInfra, local servers) share the OpenAI-compatible
    # chat-completions API, so switching to one of them is just these env vars —
    # no code change. An exotic provider needs only a new adapter in llm.py.
    LLM_PROVIDER: str = "groq"  # selector; known OpenAI-compatible bases live in llm.py
    LLM_BASE_URL: str = ""  # blank → derived from LLM_PROVIDER
    LLM_API_KEY: str = ""  # blank → falls back to GROQ_API_KEY
    LLM_MODEL: str = ""  # blank → falls back to GROQ_MODEL

    # Groq (the default provider). Free tier, no billing. Server-side only.
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # Push notifications (FCM) + the daily cron that triggers them.
    NOTIFICATIONS_ENABLED: bool = True  # global kill switch
    INTERNAL_CRON_SECRET: str = ""  # shared secret guarding /internal/run-notifications
    FCM_PROJECT_ID: str = ""  # Firebase project id
    FCM_SERVICE_ACCOUNT_JSON: str = ""  # full service-account JSON (string) — server-side only
    # Minutes east of UTC for "today" math (streak/log-date comparisons). IST = 330.
    APP_TZ_OFFSET_MINUTES: int = 330

    # CORS — comma-separated list of allowed frontend origins.
    # e.g. "http://localhost:3000,https://your-app.vercel.app"
    # Capacitor apps send Origin "capacitor://localhost" (iOS) and
    # "http://localhost" (Android) — include those when you ship the APK.
    ALLOWED_ORIGINS: str = "http://localhost:3000"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
