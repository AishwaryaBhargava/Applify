"""SQLAlchemy engine, session factory, declarative Base, and the health probe.

The engine is tuned for a *hosted* Postgres rather than a local one, because
that is the deployment that can actually go wrong. Supabase's pooler closes
idle connections and Render's free instance sleeps, so a pooled connection is
routinely dead by the time it is handed out again -- hence ``pool_pre_ping``
and a recycle well under any upstream idle timeout. The pool is deliberately
small: Supabase's free tier allows few connections, and one Render instance
holding twenty of them would starve migrations and Studio.

TLS is decided from the URL's host rather than from an environment flag. The
local Supabase stack serves plain TCP and *refuses* an SSL handshake, while
every hosted Postgres requires one -- and a single flag that has to be flipped
by hand when the URL changes is a flag someone forgets.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import is_local_database, settings

logger = logging.getLogger(__name__)

# Kept small on purpose: Supabase's free tier caps total connections, and this
# service is one of several clients. 5 + 5 covers a burst without hoarding.
POOL_SIZE = 5
MAX_OVERFLOW = 5
# Under Supabase's pooler idle timeout, so a connection is retired by us before
# it is closed under us.
POOL_RECYCLE_SECONDS = 1800

# Seconds GET /health waits for the database before reporting "error". Short
# enough that the probe answers well inside Render's health-check timeout.
HEALTH_CHECK_TIMEOUT_SECONDS = 2.0


class Base(DeclarativeBase):
    """Declarative base shared by every ORM model (and by Alembic autogenerate)."""


def connect_args_for(url: str) -> dict[str, Any]:
    """Return the DBAPI connect arguments a database URL needs.

    Shared with ``alembic/env.py`` so migrations connect exactly the way the
    application does -- a migration that cannot negotiate TLS while the app can
    is a deploy that half-succeeds.

    Args:
        url: The Postgres URL from ``SUPABASE_DATABASE_URL``.

    Returns:
        ``{"sslmode": "require"}`` for a remote host, an empty dict for a
        loopback host or a non-Postgres URL.
    """
    if not url or not url.startswith(("postgresql", "postgres")):
        return {}
    if is_local_database(url):
        return {}
    return {"sslmode": "require"}


def engine_kwargs_for(url: str) -> dict[str, Any]:
    """Return the pool settings for a database URL.

    SQLite takes none of them -- its default pool rejects ``pool_size`` -- so
    the pool arguments are Postgres-only.
    """
    kwargs: dict[str, Any] = {
        "pool_pre_ping": True,  # Supabase drops idle connections; re-check first
        "future": True,
        "connect_args": connect_args_for(url),
    }
    if url.startswith("sqlite"):
        return kwargs
    kwargs.update(
        pool_size=POOL_SIZE,
        max_overflow=MAX_OVERFLOW,
        pool_recycle=POOL_RECYCLE_SECONDS,
    )
    return kwargs


engine = create_engine(
    settings.supabase_database_url,
    **engine_kwargs_for(settings.supabase_database_url),
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)

# One worker, because the probe is one query and concurrent health checks
# should queue rather than open extra connections. If a previous probe is still
# hanging on a dead socket the next one times out waiting for the worker --
# which is the right answer anyway.
_health_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="db-health")


def _select_one() -> None:
    """Run the cheapest statement Postgres has, on a pooled connection."""
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))


def check_database(timeout: float = HEALTH_CHECK_TIMEOUT_SECONDS) -> bool:
    """Return whether the database answered a trivial query in time.

    Never raises: this backs a liveness endpoint, and a health check that
    500s tells a load balancer to kill the instance over a database blip.

    Args:
        timeout: Seconds to wait before giving up and reporting failure.

    Returns:
        True when ``SELECT 1`` succeeded within ``timeout``, False otherwise.
    """
    try:
        _health_pool.submit(_select_one).result(timeout=timeout)
        return True
    except Exception as exc:  # noqa: BLE001 - a probe must not propagate
        logger.warning("database health check failed: %s", exc)
        return False
