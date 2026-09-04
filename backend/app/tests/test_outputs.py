"""Tests for the generated output routes and the retry helper.

Phase 1 covers the auth guard and utils.retry. Behavioural tests arrive with
Phase 7.
"""

from fastapi.testclient import TestClient

from app.utils.retry import is_retryable, retry_with_backoff

CHAT_ID = "00000000-0000-0000-0000-000000000001"


def test_create_output_requires_auth(client: TestClient) -> None:
    """POST /chats/{id}/outputs is protected by get_current_user."""
    response = client.post(
        "/chats/{}/outputs".format(CHAT_ID), json={"output_type": "resume"}
    )
    assert response.status_code == 401


def test_list_outputs_requires_auth(client: TestClient) -> None:
    """GET /chats/{id}/outputs is protected by get_current_user."""
    assert client.get("/chats/{}/outputs".format(CHAT_ID)).status_code == 401


class _RateLimitError(Exception):
    """Stands in for the SDK rate limit classes, matched by name."""

    status_code = 429


def test_is_retryable_matches_rate_limits() -> None:
    """429s and 5xxs are retryable; a plain ValueError is not."""
    assert is_retryable(_RateLimitError())
    assert not is_retryable(ValueError("bad input"))


def test_retry_with_backoff_retries_then_succeeds() -> None:
    """The decorator retries a 429 and returns the eventual success."""
    calls = {"n": 0}

    @retry_with_backoff(max_attempts=3, base_delay=0.01, jitter=False)
    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise _RateLimitError("rate limited")
        return "ok"

    assert flaky() == "ok"
    assert calls["n"] == 3


def test_retry_with_backoff_does_not_retry_other_errors() -> None:
    """Non-retryable exceptions propagate on the first attempt."""
    calls = {"n": 0}

    @retry_with_backoff(max_attempts=3, base_delay=0.01, jitter=False)
    def broken() -> None:
        calls["n"] += 1
        raise ValueError("bad input")

    try:
        broken()
    except ValueError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")
    assert calls["n"] == 1
