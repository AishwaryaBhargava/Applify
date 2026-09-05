"""Every failure this API can produce, rendered as one JSON shape.

FastAPI already answers an ``HTTPException`` with ``{"detail": "..."}``. What
it does *not* do is give the same treatment to the three failures that are not
raised deliberately by a route:

* the database being unreachable, which SQLAlchemy raises as an
  ``OperationalError`` from wherever the session was first touched;
* a provider rate limit that survived the Groq/Azure fallback in
  ``services.llm``;
* anything genuinely unexpected, which Starlette would otherwise return as a
  bare ``text/plain`` "Internal Server Error" -- a body the frontend's error
  reader cannot get a message out of.

All three are mapped here, so the frontend has exactly one error shape to
parse. Two details matter beyond the shape:

* **Status choice.** A dead database and a rate-limited provider are both
  ``503``: they are temporary, and the browser and the user should be told to
  retry rather than told the request was wrong. The rate-limit message names
  "rate limit" deliberately -- ``frontend/src/services/api.ts`` matches on that
  wording to show "Taking a moment, retrying..." instead of a hard error.
* **What is not said.** The 500 body is a fixed string. Exception text can
  carry a connection string, a prompt, or a row of user data, and none of that
  belongs in a browser. The traceback is logged, with the request id, and only
  logged.

Validation failures keep their ``422`` but lose FastAPI's nested list of error
objects in favour of one readable sentence, because the frontend renders
``detail`` directly into a toast.
"""

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, OperationalError

from app.services.llm import is_rate_limit_error

logger = logging.getLogger(__name__)

DB_UNAVAILABLE = "Database unavailable, please retry"
# "rate limit" is load-bearing: the frontend matches it to soften the message.
RATE_LIMITED = (
    "The AI provider is rate limited right now. Please retry in a moment."
)
UNEXPECTED = "Something went wrong"


def error_response(status_code: int, detail: str) -> JSONResponse:
    """Return the one error body this API emits."""
    return JSONResponse(status_code=status_code, content={"detail": detail})


def flatten_validation_errors(errors: list[dict[str, Any]]) -> str:
    """Render pydantic's error list as one sentence.

    ``body -> title`` becomes ``title``, and several failures are joined with
    semicolons, so the whole thing fits in a toast.
    """
    parts: list[str] = []
    for error in errors:
        location = ".".join(
            str(item)
            for item in error.get("loc", ())
            if item not in ("body", "query", "path", "header")
        )
        message = str(error.get("msg", "Invalid value"))
        parts.append("{}: {}".format(location, message) if location else message)
    return "; ".join(parts) or "Request validation failed."


async def validation_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """422 with a readable message instead of pydantic's nested error list."""
    errors = exc.errors() if isinstance(exc, RequestValidationError) else []
    detail = flatten_validation_errors(list(errors))
    logger.info("%s %s failed validation: %s", request.method, request.url.path, detail)
    return error_response(status.HTTP_422_UNPROCESSABLE_CONTENT, detail)


async def database_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """503 when Postgres is unreachable, refusing connections, or timing out."""
    logger.error(
        "database error on %s %s", request.method, request.url.path, exc_info=exc
    )
    return error_response(status.HTTP_503_SERVICE_UNAVAILABLE, DB_UNAVAILABLE)


def response_for_unhandled(request: Request, exc: BaseException) -> JSONResponse:
    """Classify an exception no route handled and log it with its traceback.

    Args:
        request: The request that failed, named in the log line.
        exc: The exception that escaped the route.

    Returns:
        503 for a provider rate limit or a database failure that reached this
        far, 500 with a fixed message for anything else.
    """
    if isinstance(exc, (OperationalError, DBAPIError)):
        logger.error(
            "database error on %s %s", request.method, request.url.path, exc_info=exc
        )
        return error_response(status.HTTP_503_SERVICE_UNAVAILABLE, DB_UNAVAILABLE)

    if is_rate_limit_error(exc):
        logger.warning(
            "provider rate limit survived fallback on %s %s: %s",
            request.method,
            request.url.path,
            exc,
        )
        return error_response(status.HTTP_503_SERVICE_UNAVAILABLE, RATE_LIMITED)

    logger.error(
        "unhandled error on %s %s", request.method, request.url.path, exc_info=exc
    )
    return error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, UNEXPECTED)


def register_exception_handlers(app: FastAPI) -> None:
    """Attach the handlers for the failures a route does not raise itself.

    ``OperationalError`` is registered as well as its ``DBAPIError`` base:
    Starlette resolves handlers along the exception's MRO, so the base alone
    would do, but naming both keeps the intent readable from ``main.py``.
    """
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(OperationalError, database_exception_handler)
    app.add_exception_handler(DBAPIError, database_exception_handler)
