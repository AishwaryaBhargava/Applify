"""Tests for the provider fallback layer.

Everything runs offline: the four raw provider calls in ``services.llm`` --
``_complete_groq_json``, ``_complete_azure_json``, ``_open_groq_stream``,
``_open_azure_stream`` -- are the seam, and every test replaces the ones it
needs. Patching there rather than at ``complete_json`` keeps the whole decision
under test: the classification, the backoff, the fallback, and the log line.

Timing is asserted rather than waited on. ``retry_with_backoff`` sleeps between
attempts, so the tests replace ``time.sleep`` with a recorder -- which is also
the assertion for the rule that matters most here: a *daily* cap must not sleep
at all, because those seconds buy nothing.

``test_live_quick_analysis`` is the one exception and is opt-in behind
``RUN_LIVE=1``. It makes a real call.
"""

import logging
import os
import time

import pytest

from app.core.config import settings
from app.services import analysis_service, llm

MESSAGES = [
    {"role": "system", "content": "Return JSON."},
    {"role": "user", "content": "Say something."},
]

GROQ_BODY = '{"served_by": "groq"}'
AZURE_BODY = '{"served_by": "azure"}'

# The exact wording Groq's free tier returns once the day's tokens are gone.
DAILY_CAP_MESSAGE = (
    "Error code: 429 - {'error': {'message': 'Rate limit reached for model "
    "`openai/gpt-oss-120b` in organization `org_x` service tier `on_demand` on "
    "tokens per day (TPD): Limit 200000, Used 199987, Requested 512. Please try "
    "again in 8m32s.', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}"
)

# A per-minute limit: the same class, a different window, and worth waiting for.
PER_MINUTE_MESSAGE = (
    "Error code: 429 - {'error': {'message': 'Rate limit reached for model "
    "`openai/gpt-oss-120b` on tokens per minute (TPM): Limit 6000, Used 5980. "
    "Please try again in 4.2s.', 'type': 'tokens'}}"
)


# ==========================================================================
# Doubles
# ==========================================================================


class RateLimitError(Exception):
    """Shaped like ``groq.RateLimitError`` / ``openai.RateLimitError``.

    Named to match the SDK class because ``utils.retry`` and ``services.llm``
    both classify by exception name as well as by status code.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.status_code = 429


class AuthenticationError(Exception):
    """A 401. Our key is wrong, and it would be just as wrong at the other
    provider."""

    def __init__(self, message: str = "Invalid API key") -> None:
        super().__init__(message)
        self.status_code = 401


class APIConnectionError(Exception):
    """A dropped connection: no status code, only the SDK's class name."""


class _Delta:
    def __init__(self, content: str | None) -> None:
        self.content = content


class _Choice:
    def __init__(self, content: str | None) -> None:
        self.delta = _Delta(content)


class _Chunk:
    """One streamed chunk, shaped like the SDKs'."""

    def __init__(self, content: str | None) -> None:
        self.choices = [_Choice(content)]


def emit(tokens: list[str], fail_after: int | None = None, error: Exception | None = None):
    """Build a stream opener that yields ``tokens``, optionally failing part way.

    Args:
        tokens: The chunk contents to emit, in order.
        fail_after: Raise once this many chunks have been emitted. ``0`` fails
            before the first chunk, which is the only point a fallback is safe.
        error: The exception to raise. Defaults to a per-minute rate limit.
    """

    def _open(messages, **kwargs):
        def chunks():
            for index, token in enumerate(tokens):
                if fail_after is not None and index == fail_after:
                    raise error or RateLimitError(PER_MINUTE_MESSAGE)
                yield _Chunk(token)

        return chunks()

    return _open


def raises(error: Exception):
    """Build a provider call that always fails with ``error``."""

    def _call(messages, **kwargs):
        raise error

    return _call


def returns(body: str, calls: list | None = None):
    """Build a provider call that always answers with ``body``."""

    def _call(messages, **kwargs):
        if calls is not None:
            calls.append(kwargs)
        return body

    return _call


@pytest.fixture(autouse=True)
def credentials(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> None:
    """Give both providers credentials so ``is_configured`` is deterministic.

    Nothing reaches the network -- every raw call is patched -- but the fallback
    refuses to hand work to a provider with no key, and that rule must not make
    these tests depend on whoever's ``.env`` is on the machine.

    ``test_live_*`` is the one exception: it is the test that *is* the network,
    so it keeps the real configuration.
    """
    if request.node.name.startswith("test_live_"):
        return
    monkeypatch.setattr(settings, "groq_api_key", "test-groq-key")
    monkeypatch.setattr(settings, "azure_openai_endpoint", "https://test.openai.azure.com/")
    monkeypatch.setattr(settings, "azure_openai_api_key", "test-azure-key")
    monkeypatch.setattr(settings, "llm_fallback_enabled", True)


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Record every backoff sleep instead of serving it."""
    recorded: list[float] = []
    monkeypatch.setattr(time, "sleep", lambda seconds: recorded.append(seconds))
    return recorded


# ==========================================================================
# Failure classification
# ==========================================================================


def test_daily_cap_is_recognised_from_the_message() -> None:
    """"tokens per day (TPD)" is what separates a daily cap from a per-minute one."""
    assert llm.is_daily_cap(RateLimitError(DAILY_CAP_MESSAGE)) is True


def test_per_minute_limit_is_not_a_daily_cap() -> None:
    """A per-minute limit clears on its own, so it is worth the backoff."""
    assert llm.is_daily_cap(RateLimitError(PER_MINUTE_MESSAGE)) is False


def test_a_401_is_neither_retryable_nor_a_fallback_reason() -> None:
    """Our credentials being wrong is not the provider being unavailable."""
    assert llm.is_quota_or_availability_error(AuthenticationError()) is False
    assert llm.is_daily_cap(AuthenticationError("used tokens per day")) is False


def test_a_connection_error_is_a_fallback_reason() -> None:
    """No status code, but the provider is plainly unreachable."""
    assert llm.is_quota_or_availability_error(APIConnectionError("dropped")) is True


# ==========================================================================
# complete_json
# ==========================================================================


def test_groq_success_never_touches_azure(
    monkeypatch: pytest.MonkeyPatch, sleeps: list[float]
) -> None:
    """The happy path is one call to the preferred provider and nothing else."""
    calls: list = []
    monkeypatch.setattr(llm, "_complete_groq_json", returns(GROQ_BODY, calls))
    monkeypatch.setattr(
        llm, "_complete_azure_json", raises(AssertionError("azure must not be called"))
    )

    result = llm.complete_json(
        MESSAGES, max_tokens=512, temperature=0.2, purpose="quick analysis"
    )

    assert result == GROQ_BODY
    assert llm.provider_of(result) == "groq"
    assert calls == [{"max_tokens": 512, "temperature": 0.2}]
    assert sleeps == []


def test_daily_cap_falls_back_to_azure_without_sleeping(
    monkeypatch: pytest.MonkeyPatch,
    sleeps: list[float],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A daily cap skips the retries entirely: they cannot help before midnight."""
    attempts: list = []

    def groq(messages, **kwargs):
        attempts.append(kwargs)
        raise RateLimitError(DAILY_CAP_MESSAGE)

    monkeypatch.setattr(llm, "_complete_groq_json", groq)
    monkeypatch.setattr(llm, "_complete_azure_json", returns(AZURE_BODY))

    with caplog.at_level(logging.WARNING, logger="app.services.llm"):
        result = llm.complete_json(
            MESSAGES, max_tokens=512, temperature=0.2, purpose="quick analysis"
        )

    assert result == AZURE_BODY
    assert llm.provider_of(result) == "azure"
    assert len(attempts) == 1, "a daily cap must be attempted exactly once"
    assert sleeps == [], "retrying a daily cap only makes the user wait"
    assert (
        "groq rate-limited, falling back to azure for quick analysis" in caplog.text
    )


def test_per_minute_limit_retries_first_then_falls_back(
    monkeypatch: pytest.MonkeyPatch, sleeps: list[float]
) -> None:
    """A per-minute limit is worth waiting out before giving the work away."""
    attempts: list = []

    def groq(messages, **kwargs):
        attempts.append(kwargs)
        raise RateLimitError(PER_MINUTE_MESSAGE)

    monkeypatch.setattr(llm, "_complete_groq_json", groq)
    monkeypatch.setattr(llm, "_complete_azure_json", returns(AZURE_BODY))

    result = llm.complete_json(
        MESSAGES,
        max_tokens=512,
        temperature=0.2,
        purpose="quick analysis",
        max_attempts=3,
        base_delay=1.0,
    )

    assert result == AZURE_BODY
    assert len(attempts) == 3, "every attempt against Groq is used before Azure"
    assert len(sleeps) == 2, "one wait between each pair of attempts"


def test_azure_serves_the_same_prompt_and_settings(
    monkeypatch: pytest.MonkeyPatch, sleeps: list[float]
) -> None:
    """The fallback is the same request, not a cheaper one."""
    captured: list = []

    def azure(messages, **kwargs):
        captured.append((messages, kwargs))
        return AZURE_BODY

    monkeypatch.setattr(
        llm, "_complete_groq_json", raises(RateLimitError(DAILY_CAP_MESSAGE))
    )
    monkeypatch.setattr(llm, "_complete_azure_json", azure)

    llm.complete_json(MESSAGES, max_tokens=4096, temperature=0.1, purpose="extraction")

    assert captured == [(MESSAGES, {"max_tokens": 4096, "temperature": 0.1})]


def test_a_401_propagates_without_a_fallback(
    monkeypatch: pytest.MonkeyPatch, sleeps: list[float]
) -> None:
    """A bad request is ours to fix; sending it elsewhere only hides it."""
    monkeypatch.setattr(llm, "_complete_groq_json", raises(AuthenticationError()))
    monkeypatch.setattr(
        llm, "_complete_azure_json", raises(AssertionError("azure must not be called"))
    )

    with pytest.raises(AuthenticationError):
        llm.complete_json(MESSAGES, max_tokens=512, temperature=0.2, purpose="chat")

    assert sleeps == [], "a 401 is not retryable either"


def test_fallback_disabled_lets_the_rate_limit_through(
    monkeypatch: pytest.MonkeyPatch, sleeps: list[float]
) -> None:
    """LLM_FALLBACK_ENABLED=false makes a provider outage visible, not silent."""
    monkeypatch.setattr(settings, "llm_fallback_enabled", False)
    monkeypatch.setattr(
        llm, "_complete_groq_json", raises(RateLimitError(DAILY_CAP_MESSAGE))
    )
    monkeypatch.setattr(
        llm, "_complete_azure_json", raises(AssertionError("azure must not be called"))
    )

    with pytest.raises(RateLimitError):
        llm.complete_json(
            MESSAGES, max_tokens=512, temperature=0.2, purpose="quick analysis"
        )


def test_no_fallback_to_a_provider_without_credentials(
    monkeypatch: pytest.MonkeyPatch, sleeps: list[float]
) -> None:
    """Swapping a rate limit for an auth error helps nobody."""
    monkeypatch.setattr(settings, "azure_openai_api_key", "")
    monkeypatch.setattr(
        llm, "_complete_groq_json", raises(RateLimitError(DAILY_CAP_MESSAGE))
    )
    monkeypatch.setattr(
        llm, "_complete_azure_json", raises(AssertionError("azure must not be called"))
    )

    with pytest.raises(RateLimitError):
        llm.complete_json(MESSAGES, max_tokens=512, temperature=0.2, purpose="chat")


def test_prefer_azure_falls_back_to_groq(
    monkeypatch: pytest.MonkeyPatch, sleeps: list[float]
) -> None:
    """The rule is symmetric: the detailed analysis prefers Azure and can fail over."""
    monkeypatch.setattr(
        llm, "_complete_azure_json", raises(RateLimitError(DAILY_CAP_MESSAGE))
    )
    monkeypatch.setattr(llm, "_complete_groq_json", returns(GROQ_BODY))

    result = llm.complete_json(
        MESSAGES,
        max_tokens=512,
        temperature=0.2,
        prefer=llm.AZURE,
        purpose="detailed analysis",
    )

    assert llm.provider_of(result) == "groq"


def test_a_failing_fallback_raises_its_own_error(
    monkeypatch: pytest.MonkeyPatch, sleeps: list[float]
) -> None:
    """When both providers are down, the second failure is the one reported."""
    monkeypatch.setattr(
        llm, "_complete_groq_json", raises(RateLimitError(DAILY_CAP_MESSAGE))
    )
    monkeypatch.setattr(llm, "_complete_azure_json", raises(APIConnectionError("down")))

    with pytest.raises(APIConnectionError):
        llm.complete_json(MESSAGES, max_tokens=512, temperature=0.2, purpose="chat")


# ==========================================================================
# stream_text
# ==========================================================================


def test_stream_falls_back_before_the_first_chunk(
    monkeypatch: pytest.MonkeyPatch,
    sleeps: list[float],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Nothing has been shown yet, so the whole reply can come from Azure."""
    monkeypatch.setattr(
        llm,
        "_open_groq_stream",
        emit(["never "], fail_after=0, error=RateLimitError(DAILY_CAP_MESSAGE)),
    )
    monkeypatch.setattr(llm, "_open_azure_stream", emit(["Your ", "reply."]))

    stream = llm.stream_text(MESSAGES, max_tokens=2048, temperature=0.6, purpose="chat")

    with caplog.at_level(logging.WARNING, logger="app.services.llm"):
        chunks = list(stream)

    assert chunks == ["Your ", "reply."]
    assert stream.provider == "azure"
    assert "groq rate-limited, falling back to azure for chat" in caplog.text
    assert sleeps == []


def test_stream_error_after_the_first_chunk_does_not_fall_back(
    monkeypatch: pytest.MonkeyPatch, sleeps: list[float]
) -> None:
    """Half a reply from each model would read as one incoherent answer.

    The user has already seen the opening words; the route's job from here is to
    persist what streamed and report the failure, not to start a second reply.
    """
    monkeypatch.setattr(
        llm,
        "_open_groq_stream",
        emit(["Your ", "Python ", "never"], fail_after=2),
    )
    monkeypatch.setattr(
        llm, "_open_azure_stream", raises(AssertionError("azure must not be called"))
    )

    stream = llm.stream_text(MESSAGES, max_tokens=2048, temperature=0.6, purpose="chat")

    seen: list[str] = []
    with pytest.raises(RateLimitError):
        for chunk in stream:
            seen.append(chunk)

    assert seen == ["Your ", "Python "]
    assert stream.provider == "groq"


def test_stream_daily_cap_falls_back_without_sleeping(
    monkeypatch: pytest.MonkeyPatch, sleeps: list[float]
) -> None:
    """A capped Groq hands the whole reply to Azure at once, not after four waits."""
    attempts: list = []

    def groq(messages, **kwargs):
        attempts.append(kwargs)
        raise RateLimitError(DAILY_CAP_MESSAGE)

    monkeypatch.setattr(llm, "_open_groq_stream", groq)
    monkeypatch.setattr(llm, "_open_azure_stream", emit(["Azure ", "reply."]))

    stream = llm.stream_text(MESSAGES, max_tokens=2048, temperature=0.6, purpose="chat")

    assert list(stream) == ["Azure ", "reply."]
    assert stream.provider == "azure"
    assert len(attempts) == 1
    assert sleeps == []


def test_stream_per_minute_limit_retries_before_falling_back(
    monkeypatch: pytest.MonkeyPatch, sleeps: list[float]
) -> None:
    """A per-minute limit gets the backoff first; Azure only covers what is left."""
    attempts: list = []

    def groq(messages, **kwargs):
        attempts.append(kwargs)
        raise RateLimitError(PER_MINUTE_MESSAGE)

    monkeypatch.setattr(llm, "_open_groq_stream", groq)
    monkeypatch.setattr(llm, "_open_azure_stream", emit(["ok"]))

    stream = llm.stream_text(
        MESSAGES, max_tokens=2048, temperature=0.6, purpose="chat", max_attempts=3
    )

    assert list(stream) == ["ok"]
    assert len(attempts) == 3
    assert len(sleeps) == 2


def test_stream_records_the_provider_that_served_it(
    monkeypatch: pytest.MonkeyPatch, sleeps: list[float]
) -> None:
    """The happy path names Groq, which is what the SSE done event reports."""
    monkeypatch.setattr(llm, "_open_groq_stream", emit(["ok"]))
    monkeypatch.setattr(
        llm, "_open_azure_stream", raises(AssertionError("azure must not be called"))
    )

    stream = llm.stream_text(MESSAGES, max_tokens=2048, temperature=0.6, purpose="chat")

    assert list(stream) == ["ok"]
    assert stream.provider == "groq"


def test_stream_skips_chunks_with_no_content(
    monkeypatch: pytest.MonkeyPatch, sleeps: list[float]
) -> None:
    """Azure's content filter leads with an empty chunk; it is not a token."""

    def _open(messages, **kwargs):
        empty = _Chunk(None)
        empty.choices = []
        return iter([empty, _Chunk(None), _Chunk("real")])

    monkeypatch.setattr(llm, "_open_groq_stream", _open)

    stream = llm.stream_text(MESSAGES, max_tokens=2048, temperature=0.6, purpose="chat")

    assert list(stream) == ["real"]


def test_stream_fallback_disabled_propagates(
    monkeypatch: pytest.MonkeyPatch, sleeps: list[float]
) -> None:
    """With fallback off, a capped Groq is an error the route reports."""
    monkeypatch.setattr(settings, "llm_fallback_enabled", False)
    monkeypatch.setattr(
        llm, "_open_groq_stream", raises(RateLimitError(DAILY_CAP_MESSAGE))
    )
    monkeypatch.setattr(
        llm, "_open_azure_stream", raises(AssertionError("azure must not be called"))
    )

    stream = llm.stream_text(MESSAGES, max_tokens=2048, temperature=0.6, purpose="chat")

    with pytest.raises(RateLimitError):
        list(stream)


# ==========================================================================
# The call sites
# ==========================================================================


def test_quick_analysis_records_the_serving_provider(
    monkeypatch: pytest.MonkeyPatch, sleeps: list[float]
) -> None:
    """A snapshot Azure rescued says so, and the row records it."""
    body = (
        '{"fit_score": 71, "strengths": ["a", "b", "c"], '
        '"gaps": ["d", "e", "f"], "verdict": "Worth applying."}'
    )
    monkeypatch.setattr(
        llm, "_complete_groq_json", raises(RateLimitError(DAILY_CAP_MESSAGE))
    )
    monkeypatch.setattr(llm, "_complete_azure_json", returns(body))

    snapshot = analysis_service.run_quick_analysis({"skills": ["Python"]}, "Needs Python")

    assert snapshot.fit_score == 71
    assert snapshot._provider == "azure"


def test_chat_prefers_azure_when_configured_to(monkeypatch: pytest.MonkeyPatch) -> None:
    """LLM_PREFER_AZURE_FOR_CHAT flips the order with no code change."""
    from app.services import chat_service

    monkeypatch.setattr(settings, "llm_prefer_azure_for_chat", True)
    assert chat_service.chat_provider() == llm.AZURE

    monkeypatch.setattr(settings, "llm_prefer_azure_for_chat", False)
    assert chat_service.chat_provider() == llm.GROQ


# ==========================================================================
# Live check (opt-in)
# ==========================================================================


@pytest.mark.skipif(
    os.environ.get("RUN_LIVE") != "1",
    reason="Set RUN_LIVE=1 to run a real quick analysis against the live providers.",
)
def test_live_quick_analysis() -> None:
    """Run one real quick analysis and report which provider served it.

    The assertion is deliberately provider-agnostic: the point of the fallback
    is that a valid snapshot comes back whether Groq answered or Azure covered
    for it. Run with ``-s`` to see the provider and the latency.
    """
    profile = {
        "summary": "Backend engineer with six years on Python payment systems.",
        "skills": ["Python", "PostgreSQL", "FastAPI", "Docker"],
        "work_experience": [
            {
                "title": "Senior Backend Engineer",
                "company": "Kestrel Payments",
                "start_date": "March 2022",
                "current": True,
                "highlights": ["Cut reconciliation from 40 minutes to 6."],
            }
        ],
    }
    jd = (
        "Senior Backend Engineer. Python and PostgreSQL in production, "
        "Kubernetes for deployment, and experience owning payment integrations."
    )

    started = time.monotonic()
    snapshot = analysis_service.run_quick_analysis(profile, jd)
    elapsed = time.monotonic() - started

    print(
        "\nlive quick analysis: provider={} fit_score={} latency={:.2f}s".format(
            snapshot._provider, snapshot.fit_score, elapsed
        )
    )

    assert snapshot._provider in (llm.GROQ, llm.AZURE)
    assert 0 <= snapshot.fit_score <= 100
    assert snapshot.verdict, "a snapshot without a verdict is not usable"
    assert len(snapshot.strengths) == 3
    assert len(snapshot.gaps) == 3
