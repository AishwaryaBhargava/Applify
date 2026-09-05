"""Alembic migration environment.

The database URL is read from ``app.core.config.settings`` (i.e. from
``backend/.env`` or the deployment environment), never from ``alembic.ini``, so
there is exactly one place credentials live.

Connection arguments come from ``app.data.database.connect_args_for``, the same
function the application engine uses, so a migration negotiates TLS exactly the
way the running app does. That matters on Render, where the release step is
``alembic upgrade head``: a migration that cannot connect while the app can is a
deploy that half-succeeds.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings

# Importing app.models registers every table on Base.metadata.
import app.models  # noqa: F401  (side-effect import)
from app.data.database import Base, connect_args_for

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Feed the real URL to Alembic at runtime. escape '%' so ConfigParser
# interpolation does not choke on percent-encoded passwords.
if settings.supabase_database_url:
    config.set_main_option(
        "sqlalchemy.url", settings.supabase_database_url.replace("%", "%%")
    )

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations without a DBAPI connection, emitting SQL to stdout."""
    context.configure(
        url=settings.supabase_database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=connect_args_for(settings.supabase_database_url),
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
