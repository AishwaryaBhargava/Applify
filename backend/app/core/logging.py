"""Structured logging, and the request id every log line is stamped with.

One request that fails produces a handler log line, possibly a service warning,
and a line in uvicorn's access log. Correlating those in a Render log stream is
only possible if they share an identifier, so
:class:`app.core.middleware.RequestIDMiddleware` puts a uuid in
:data:`request_id_var` for the life of each request and every record formatted
here carries it.

The root logger is configured, not uvicorn's. ``uvicorn``, ``uvicorn.access``
and ``uvicorn.error`` are set up by uvicorn itself with ``propagate = False``,
so touching the root leaves the access log exactly as it was and only affects
this application's own loggers.
"""

import logging
import sys
from contextvars import ContextVar

# The current request's id, or "-" outside a request (startup, a worker thread
# with no context, a management command).
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

LOG_FORMAT = "%(asctime)s %(levelname)-8s [%(request_id)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%dT%H:%M:%S%z"

# Marks the handler this module installed, so repeated calls replace it instead
# of stacking a second copy (the test suite imports the app many times).
_HANDLER_NAME = "applify-console"


class RequestIDFilter(logging.Filter):
    """Attach the current request id to every record as ``request_id``.

    A filter rather than a custom formatter so the field exists on records
    emitted by third-party libraries too, which would otherwise raise a
    ``KeyError`` against :data:`LOG_FORMAT`.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Always keep the record; only add the missing attribute."""
        if not hasattr(record, "request_id"):
            record.request_id = request_id_var.get()
        return True


def resolve_level(name: str) -> int:
    """Return the logging level for a LOG_LEVEL value, defaulting to INFO."""
    level = logging.getLevelName(str(name).strip().upper())
    return level if isinstance(level, int) else logging.INFO


def configure_logging(level: str = "INFO") -> None:
    """Install the application's console handler on the root logger.

    Idempotent: calling it twice replaces the handler rather than doubling
    every line.

    Args:
        level: A level name from ``LOG_LEVEL``; anything unrecognised is INFO.
    """
    root = logging.getLogger()
    for existing in list(root.handlers):
        if getattr(existing, "name", None) == _HANDLER_NAME:
            root.removeHandler(existing)

    handler = logging.StreamHandler(sys.stdout)
    handler.name = _HANDLER_NAME
    handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
    handler.addFilter(RequestIDFilter())

    root.addHandler(handler)
    root.setLevel(resolve_level(level))

    # SQLAlchemy's engine logger is deliberately left at WARNING: at INFO it
    # echoes every statement, which on a chat turn is pages of SQL.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
