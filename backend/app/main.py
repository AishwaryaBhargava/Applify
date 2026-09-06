"""FastAPI application entry point: logging, middleware, error handling, routes.

The middleware stack is assembled bottom-up here because Starlette applies
``add_middleware`` in reverse order -- the last one added is the outermost. The
resulting order, and why each layer sits where it does, is documented in
:mod:`app.core.middleware`.

Nothing in this module reads ``$PORT``. Uvicorn takes it on the command line
(``--port $PORT``), which is how Render and the Dockerfile both start the app,
so the port is a deployment concern rather than a code one.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    account,
    analysis,
    auth,
    chats,
    health,
    messages,
    outputs,
    profile,
    tracker,
)
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import (
    REQUEST_ID_HEADER,
    BodySizeLimitMiddleware,
    ExceptionResponseMiddleware,
    RequestIDMiddleware,
    SecurityHeadersMiddleware,
)
from app.core.version import app_version

configure_logging(settings.log_level)
logger = logging.getLogger(__name__)

# The verbs and headers this API actually uses. Spelled out rather than "*"
# because a wildcard plus credentials is the combination browsers refuse, and
# because an explicit list is the one place to look when a preflight fails.
CORS_METHODS = ["GET", "POST", "PATCH", "DELETE", "OPTIONS"]
CORS_HEADERS = ["Authorization", "Content-Type", "Accept", REQUEST_ID_HEADER]


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Record what this process actually decided, once, at boot.

    Three things are worth a line each, because all three are invisible
    otherwise and each has its own way of silently breaking a deploy: a
    corrected CORS origin (the dashboard says one thing, the server compares
    another), whether the database is being connected to over TLS, and which
    build is running.
    """
    for configured, used in settings.origin_corrections:
        logger.warning("ALLOWED_ORIGINS entry %r normalised to %r", configured, used)
    logger.info(
        "Applify API %s starting: origins=%s, database=%s",
        app_version(),
        settings.allowed_origins or "none",
        "local (no TLS)" if settings.database_is_local else "remote (sslmode=require)",
    )
    yield


app = FastAPI(
    title="Applify API",
    description="Backend for Applify, a job application co-pilot.",
    version="1.0.0",
    lifespan=lifespan,
)

# Innermost first: see the module docstring in app.core.middleware.
app.add_middleware(BodySizeLimitMiddleware)
app.add_middleware(ExceptionResponseMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=CORS_METHODS,
    allow_headers=CORS_HEADERS,
    # Without this the browser hides the header from the frontend, and the id
    # in a user's bug report would not match anything in the logs.
    expose_headers=[REQUEST_ID_HEADER],
    max_age=600,
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestIDMiddleware)

register_exception_handlers(app)


# GET /health is the only unprotected route; everything below it depends on
# get_current_user.
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(chats.router)
app.include_router(messages.router)
app.include_router(analysis.router)
app.include_router(outputs.router)
app.include_router(tracker.router)
app.include_router(account.router)
