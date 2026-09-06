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

# Hosts that are never reachable over TLS, so a Postgres URL pointing at one is
# connected to without SSL. Everything else -- a Supabase cloud project above
# all -- gets ``sslmode=require``.
LOCAL_DB_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "[::1]", "0.0.0.0"})

# Origins whose scheme, when ALLOWED_ORIGINS omits it, is http rather than https.
LOCAL_ORIGIN_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "[::1]"})


def normalise_origin(value: str) -> str:
    """Return one ALLOWED_ORIGINS entry in the exact form CORS compares against.

    Starlette matches ``Origin`` headers against this list by string equality,
    so ``https://applify.vercel.app/`` with its trailing slash silently matches
    nothing, and a bare ``applify.vercel.app`` matches nothing either. Both are
    easy to type into a dashboard and impossible to debug from the browser
    error, so they are corrected here rather than trusted.

    Args:
        value: One comma-separated entry from ``ALLOWED_ORIGINS``.

    Returns:
        The origin as ``scheme://host[:port]``: lower-cased, trailing slashes
        and any path removed, and a scheme added when one is missing (``http``
        for a loopback host, ``https`` for anything else). ``*`` is returned
        unchanged.
    """
    origin = value.strip()
    if not origin or origin == "*":
        return origin

    origin = origin.rstrip("/")
    if "://" in origin:
        scheme, _, remainder = origin.partition("://")
        origin = "{}://{}".format(scheme.lower(), remainder)
    else:
        host = origin.split(":", 1)[0].split("/", 1)[0].lower()
        scheme = "http" if host in LOCAL_ORIGIN_HOSTS else "https"
        origin = "{}://{}".format(scheme, origin)

    # Drop any path that was pasted along with the origin: CORS compares the
    # scheme, host, and port only.
    scheme, _, remainder = origin.partition("://")
    remainder = remainder.split("/", 1)[0]
    return "{}://{}".format(scheme.lower(), remainder.lower())


def is_local_database(url: str) -> bool:
    """Return True when a Postgres URL points at a host on this machine.

    Used to decide whether ``sslmode=require`` applies: the local Supabase
    stack serves plain TCP and refuses an SSL handshake, while every hosted
    Postgres expects one.
    """
    if not url:
        return True
    remainder = url.partition("://")[2]
    authority = remainder.split("/", 1)[0].split("?", 1)[0]
    host_port = authority.rpartition("@")[2]
    if host_port.startswith("["):
        host = host_port.partition("]")[0] + "]"
    else:
        host = host_port.split(":", 1)[0]
    return host.lower() in LOCAL_DB_HOSTS


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

    # --- Provider fallback (services/llm.py) ---
    # Groq's free tier has a daily token cap. When it is reached, the affected
    # call is re-sent to Azure GPT-4o rather than failing. Set false to make a
    # provider outage visible instead of quietly doubling Azure spend.
    llm_fallback_enabled: bool = Field(default=True, alias="LLM_FALLBACK_ENABLED")
    # Send chat to Azure first instead of Groq. The escape hatch for a day when
    # Groq is capped from the first request: no code change, no redeploy.
    llm_prefer_azure_for_chat: bool = Field(
        default=False, alias="LLM_PREFER_AZURE_FOR_CHAT"
    )

    # --- Supabase (Postgres + Auth) ---
    supabase_database_url: str = Field(default="", alias="SUPABASE_DATABASE_URL")
    supabase_jwt_secret: str = Field(default="", alias="SUPABASE_JWT_SECRET")
    # Project base URL, e.g. https://abcdefgh.supabase.co -- used to locate the
    # JWKS endpoint for asymmetric (ES256/RS256) token verification.
    supabase_url: str = Field(default="", alias="SUPABASE_URL")
    # Admin key for the Supabase Auth API. Only DELETE /account uses it, to
    # remove the login after the user's rows are gone. Secret: it bypasses row
    # level security entirely, so it is never logged and never sent to a
    # browser. Unset means account deletion answers 501 rather than half
    # deleting an account.
    supabase_service_role_key: str = Field(
        default="", alias="SUPABASE_SERVICE_ROLE_KEY"
    )

    # --- Private instance ---
    # Comma-separated email allowlist. Empty (the default) means the instance is
    # open to anyone the Supabase project will issue a token to. Non-empty turns
    # it private: a valid token whose `email` claim is not listed is a 403.
    allowed_user_emails_raw: str = Field(default="", alias="ALLOWED_USER_EMAILS")

    # --- CORS ---
    # Comma-separated in the environment, exposed as a list via allowed_origins.
    allowed_origins_raw: str = Field(
        default="http://localhost:5173", alias="ALLOWED_ORIGINS"
    )

    # --- Runtime / observability ---
    # Root log level. DEBUG locally when something needs tracing; INFO on
    # Render, where every line costs log retention.
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    # Reported by GET /health so a deployed build can be identified. Render
    # sets RENDER_GIT_COMMIT itself; APP_VERSION overrides it anywhere else.
    app_version_override: str = Field(default="", alias="APP_VERSION")
    render_git_commit: str = Field(default="", alias="RENDER_GIT_COMMIT")

    # --- JWT verification ---
    # utils/auth.py picks its strategy per token: a token carrying a `kid` is
    # verified against the project's JWKS (ES256/RS256 signing keys), one
    # without falls back to the shared HS256 secret. No mode switch needed.
    jwt_audience: str = Field(default="authenticated", alias="SUPABASE_JWT_AUDIENCE")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def allowed_origins(self) -> list[str]:
        """ALLOWED_ORIGINS parsed, normalised, and de-duplicated.

        Normalisation is not cosmetic: Starlette compares the browser's
        ``Origin`` header against these strings exactly, so a stray trailing
        slash or a missing scheme in the Render dashboard would block the
        frontend with no server-side error to read.
        """
        seen: dict[str, None] = {}
        for raw in self.allowed_origins_raw.split(","):
            origin = normalise_origin(raw)
            if origin:
                seen.setdefault(origin, None)
        return list(seen)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def origin_corrections(self) -> list[tuple[str, str]]:
        """``(as configured, as used)`` for every entry normalisation changed.

        Logged once at startup so a corrected origin is visible rather than
        silently different from what the dashboard says.
        """
        corrections: list[tuple[str, str]] = []
        for raw in self.allowed_origins_raw.split(","):
            entry = raw.strip()
            if not entry:
                continue
            normalised = normalise_origin(entry)
            if normalised != entry:
                corrections.append((entry, normalised))
        return corrections

    @computed_field  # type: ignore[prop-decorator]
    @property
    def allowed_user_emails(self) -> frozenset[str]:
        """ALLOWED_USER_EMAILS parsed, lower-cased, and de-duplicated.

        Empty means the instance is open. Comparison is case-folded because an
        email address is case-insensitive in practice and a capitalised entry in
        a dashboard would otherwise lock its owner out with a 403 they could not
        explain.
        """
        return frozenset(
            entry.strip().lower()
            for entry in self.allowed_user_emails_raw.split(",")
            if entry.strip()
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_is_local(self) -> bool:
        """True when SUPABASE_DATABASE_URL points at this machine.

        The local Supabase stack speaks plain TCP; every hosted Postgres wants
        TLS. This is the switch between the two.
        """
        return is_local_database(self.supabase_database_url)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def version(self) -> str:
        """The build identifier reported by ``GET /health``."""
        return self.app_version_override or self.render_git_commit or ""

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
