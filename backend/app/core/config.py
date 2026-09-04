"""Application settings.

Single source of truth for every environment variable the backend reads.
Values are loaded from ``backend/.env`` locally and from the platform
environment (Render dashboard) in deployment.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> backend/
BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """All backend environment variables, validated at import time."""

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    # --- Azure AI Foundry (GPT-4o: detailed analysis + document generation) ---
    azure_openai_endpoint: str = Field(default="", alias="AZURE_OPENAI_ENDPOINT")
    azure_openai_api_key: str = Field(default="", alias="AZURE_OPENAI_API_KEY")
    azure_openai_api_version: str = Field(
        default="2024-12-01-preview", alias="AZURE_OPENAI_API_VERSION"
    )
    azure_gpt4o_deployment: str = Field(default="gpt-4o", alias="AZURE_GPT4O_DEPLOYMENT")

    # --- Groq (chat + quick analysis) ---
    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")
    # llama-3.3-70b-versatile named in the tech stack doc is decommissioned on
    # this account; gpt-oss-120b is the verified replacement. Overridable so a
    # model swap never needs a code change.
    groq_model: str = Field(default="openai/gpt-oss-120b", alias="GROQ_MODEL")

    # --- Supabase (Postgres + Auth) ---
    supabase_database_url: str = Field(default="", alias="SUPABASE_DATABASE_URL")
    supabase_jwt_secret: str = Field(default="", alias="SUPABASE_JWT_SECRET")
    # Project base URL, e.g. https://abcdefgh.supabase.co -- used to locate the
    # JWKS endpoint for asymmetric (ES256/RS256) token verification.
    supabase_url: str = Field(default="", alias="SUPABASE_URL")

    # --- CORS ---
    # Comma-separated in the environment, exposed as a list via allowed_origins.
    allowed_origins_raw: str = Field(
        default="http://localhost:5173", alias="ALLOWED_ORIGINS"
    )

    # --- JWT verification ---
    # utils/auth.py picks its strategy per token: a token carrying a `kid` is
    # verified against the project's JWKS (ES256/RS256 signing keys), one
    # without falls back to the shared HS256 secret. No mode switch needed.
    jwt_audience: str = Field(default="authenticated", alias="SUPABASE_JWT_AUDIENCE")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def allowed_origins(self) -> list[str]:
        """ALLOWED_ORIGINS parsed into a list of origins."""
        return [
            origin.strip()
            for origin in self.allowed_origins_raw.split(",")
            if origin.strip()
        ]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def supabase_jwks_url(self) -> str:
        """The project's JWKS endpoint, derived from SUPABASE_URL."""
        if not self.supabase_url:
            return ""
        return self.supabase_url.rstrip("/") + "/auth/v1/.well-known/jwks.json"


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide Settings singleton."""
    return Settings()


settings = get_settings()
