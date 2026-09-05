"""Tests for the cross-cutting layer: error shape, request ids, headers, CORS.

Nothing here exercises a feature. It exercises the promises every route makes
without stating them -- that a failure is JSON and not HTML, that a 500 says
nothing about the code that produced it, that a response can be traced back to
a log line, and that a browser is allowed to read the answer.

Every test is offline. The failures are injected by overriding ``get_db`` with
a dependency that raises, which is the same place a real database failure would
first surface.
"""

import logging
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.core import errors
from app.core.config import (
    is_local_database,
    normalise_origin,
    settings,
)
from app.core.logging import RequestIDFilter, request_id_var
from app.core.middleware import BODY_TOO_LARGE, MAX_BODY_BYTES, SECURITY_HEADERS
from app.data.database import connect_args_for
from app.data.deps import get_current_user, get_db
from app.main import app
from app.tests.conftest import TEST_USER_ID

# A protected route with a database dependency: the shortest path from a
# failing session to a rendered error response.
PROBE_ROUTE = "/profile"

# Text planted in an exception message. It must never reach the client.
SECRET = "postgresql://postgres:hunter2@db.internal:5432/applify"


def _operational_error() -> OperationalError:
    """Build the exception psycopg2 raises when Postgres is unreachable."""
    return OperationalError(
        "SELECT 1", {}, Exception("could not connect to server: {}".format(SECRET))
    )


class _FakeRateLimitError(Exception):
    """Stands in for the SDKs' RateLimitError, matched by name and status.

    ``services.llm`` deliberately classifies provider failures by class name
    and status code rather than by importing the openai and groq SDKs, so a
    local class named this way is exactly what the real thing looks like to it.
    """

    status_code = 429


@pytest.fixture
def failing_client() -> Iterator[TestClient]:
    """A client whose ``get_db`` can be pointed at any exception.

    Yields a helper that installs a raising dependency and returns the client,
    so each test names the failure it is about in one line.
    """
    clients: list[TestClient] = []

    def raise_from_get_db(exc: BaseException) -> TestClient:
        def broken_db() -> None:
            raise exc

        app.dependency_overrides[get_db] = broken_db
        app.dependency_overrides[get_current_user] = lambda: TEST_USER_ID
        client = TestClient(app)
        clients.append(client)
        return client

    try:
        yield raise_from_get_db  # type: ignore[misc]
    finally:
        app.dependency_overrides.clear()


# --- the exception handlers ------------------------------------------------


def test_database_failure_is_a_503_json_body(failing_client) -> None:
    """An OperationalError is 503 with the retry message, not a 500 or HTML."""
    response = failing_client(_operational_error()).get(PROBE_ROUTE)

    assert response.status_code == 503
    assert response.json() == {"detail": errors.DB_UNAVAILABLE}
    assert response.headers["content-type"].startswith("application/json")


def test_database_failure_does_not_leak_the_connection_string(failing_client) -> None:
    """The 503 says to retry and nothing about where the database lives."""
    response = failing_client(_operational_error()).get(PROBE_ROUTE)

    assert SECRET not in response.text
    assert "psycopg2" not in response.text


def test_unexpected_exception_is_a_500_json_body(failing_client) -> None:
    """Anything unclassified is 500 with a fixed message."""
    response = failing_client(RuntimeError("kaboom in {}".format(SECRET))).get(
        PROBE_ROUTE
    )

    assert response.status_code == 500
    assert response.json() == {"detail": errors.UNEXPECTED}


def test_unexpected_exception_leaks_neither_traceback_nor_message(
    failing_client,
) -> None:
    """The body carries no stack trace, no exception class, and no detail text."""
    response = failing_client(RuntimeError("kaboom in {}".format(SECRET))).get(
        PROBE_ROUTE
    )

    body = response.text
    assert "Traceback" not in body
    assert "RuntimeError" not in body
    assert "kaboom" not in body
    assert SECRET not in body


def test_provider_rate_limit_is_a_503_naming_rate_limits(failing_client) -> None:
    """A 429 that survived the provider fallback is 503, worded for the frontend.

    ``frontend/src/services/api.ts`` matches "rate limit" in the detail of a
    502 or 503 to show "Taking a moment, retrying..." instead of a hard error,
    so the wording is a contract rather than copy.
    """
    response = failing_client(_FakeRateLimitError("Rate limit reached")).get(
        PROBE_ROUTE
    )

    assert response.status_code == 503
    assert "rate limit" in response.json()["detail"].lower()


def test_unhandled_failures_are_logged_with_their_traceback(
    failing_client, caplog: pytest.LogCaptureFixture
) -> None:
    """What the client is not told, the log is."""
    with caplog.at_level(logging.ERROR, logger="app.core.errors"):
        failing_client(RuntimeError("kaboom")).get(PROBE_ROUTE)

    record = next(r for r in caplog.records if r.name == "app.core.errors")
    assert record.exc_info is not None
    assert PROBE_ROUTE in record.getMessage()


def test_validation_errors_are_a_readable_sentence(auth_client: TestClient) -> None:
    """422 keeps its status but loses pydantic's nested list of error objects.

    The frontend renders ``detail`` straight into a toast, and a JSON array of
    ``{"loc": [...], "type": ...}`` renders as noise.
    """
    response = auth_client.post("/chats", json={"title": ""})

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert isinstance(detail, str)
    assert "title" in detail


# --- request ids -----------------------------------------------------------


def test_every_response_carries_a_request_id(client: TestClient) -> None:
    """The header is on a plain 401 as much as on a 200."""
    response = client.get(PROBE_ROUTE)

    assert response.status_code == 401
    assert response.headers["X-Request-ID"]


def test_error_responses_carry_a_request_id(failing_client) -> None:
    """A 500 is exactly the response whose id someone will quote in a bug report."""
    response = failing_client(RuntimeError("kaboom")).get(PROBE_ROUTE)

    assert response.status_code == 500
    assert response.headers["X-Request-ID"]


def test_an_inbound_request_id_is_kept(client: TestClient) -> None:
    """A caller's own correlation id survives instead of being replaced."""
    response = client.get(PROBE_ROUTE, headers={"X-Request-ID": "trace-abc-123"})

    assert response.headers["X-Request-ID"] == "trace-abc-123"


def test_request_ids_differ_between_requests(client: TestClient) -> None:
    """Two requests are two ids, or the id would correlate nothing."""
    first = client.get("/auth/verify").headers["X-Request-ID"]
    second = client.get("/auth/verify").headers["X-Request-ID"]

    assert first != second


def test_log_records_are_stamped_with_the_current_request_id() -> None:
    """The filter is what puts the id into every formatted line."""
    token = request_id_var.set("req-42")
    try:
        record = logging.LogRecord("t", logging.INFO, __file__, 1, "hi", None, None)
        assert RequestIDFilter().filter(record) is True
        assert record.request_id == "req-42"
    finally:
        request_id_var.reset(token)


# --- security headers ------------------------------------------------------


@pytest.mark.parametrize("name,value", SECURITY_HEADERS)
def test_security_headers_are_set(client: TestClient, name: str, value: str) -> None:
    """Every response carries the four headers that cost nothing."""
    response = client.get(PROBE_ROUTE)

    assert response.headers[name] == value


def test_no_hsts_header_is_sent(client: TestClient) -> None:
    """Render terminates TLS; this process does not get to pin a domain policy."""
    assert "strict-transport-security" not in client.get(PROBE_ROUTE).headers


# --- CORS ------------------------------------------------------------------


def test_preflight_from_an_allowed_origin_is_permitted(client: TestClient) -> None:
    """The configured frontend origin gets its preflight approved."""
    origin = settings.allowed_origins[0]

    response = client.options(
        PROBE_ROUTE,
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["access-control-allow-credentials"] == "true"


def test_preflight_from_an_unknown_origin_gets_no_allow_header(
    client: TestClient,
) -> None:
    """An origin that is not configured is refused, not silently allowed."""
    response = client.options(
        PROBE_ROUTE,
        headers={
            "Origin": "http://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert "access-control-allow-origin" not in response.headers


def test_the_request_id_header_is_exposed_to_the_browser(client: TestClient) -> None:
    """Without expose_headers the frontend cannot read the id it would report."""
    response = client.get(
        PROBE_ROUTE, headers={"Origin": settings.allowed_origins[0]}
    )

    assert "X-Request-ID" in response.headers["access-control-expose-headers"]


# --- the body size cap -----------------------------------------------------


def test_an_oversized_body_is_refused_before_the_route_reads_it(
    client: TestClient,
) -> None:
    """A body over the ASGI cap is 413 before authentication even runs.

    ``client`` sends no token, so a 401 here would mean the request reached the
    routing layer with a 12MB body already in memory -- exactly what the cap
    exists to prevent.
    """
    oversized = b"0" * (MAX_BODY_BYTES + 1024)

    response = client.post(
        "/profile/upload",
        files={"file": ("huge.pdf", oversized, "application/pdf")},
    )

    assert response.status_code == 413
    assert response.json() == {"detail": BODY_TOO_LARGE}


# --- configuration normalisation -------------------------------------------


@pytest.mark.parametrize(
    "configured,expected",
    [
        ("https://applify.vercel.app/", "https://applify.vercel.app"),
        ("applify.vercel.app", "https://applify.vercel.app"),
        ("localhost:5173", "http://localhost:5173"),
        ("127.0.0.1:5173", "http://127.0.0.1:5173"),
        ("HTTPS://Applify.Vercel.App", "https://applify.vercel.app"),
        ("https://applify.vercel.app/app/", "https://applify.vercel.app"),
        ("  http://localhost:5173  ", "http://localhost:5173"),
        ("*", "*"),
    ],
)
def test_origins_are_normalised_to_what_cors_compares(
    configured: str, expected: str
) -> None:
    """CORS matches by string equality, so a typed-in origin is corrected first."""
    assert normalise_origin(configured) == expected


def test_origin_corrections_are_reported_for_logging() -> None:
    """A corrected origin is surfaced so startup can say so out loud."""
    raw = settings.allowed_origins_raw
    try:
        settings.allowed_origins_raw = "https://applify.vercel.app/, localhost:5173"
        assert settings.origin_corrections == [
            ("https://applify.vercel.app/", "https://applify.vercel.app"),
            ("localhost:5173", "http://localhost:5173"),
        ]
    finally:
        settings.allowed_origins_raw = raw


@pytest.mark.parametrize(
    "url,local",
    [
        ("postgresql://postgres:postgres@127.0.0.1:54322/postgres", True),
        ("postgresql://postgres:postgres@localhost:5432/postgres", True),
        ("postgresql://postgres:pw@db.abcdefgh.supabase.co:5432/postgres", False),
        ("postgresql://postgres.ref:pw@aws-0-eu-west-2.pooler.supabase.com:5432/x", False),
        ("", True),
    ],
)
def test_local_databases_are_told_from_hosted_ones(url: str, local: bool) -> None:
    """The TLS decision is read off the URL rather than off a separate flag."""
    assert is_local_database(url) is local


def test_only_a_hosted_database_gets_sslmode_require() -> None:
    """The local Supabase stack refuses an SSL handshake; Supabase cloud demands one."""
    assert connect_args_for("postgresql://postgres:postgres@127.0.0.1:54322/x") == {}
    assert connect_args_for("postgresql://u:p@db.ref.supabase.co:5432/postgres") == {
        "sslmode": "require"
    }
