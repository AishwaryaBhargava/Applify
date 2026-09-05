"""Provider abstraction with automatic Groq <-> Azure fallback.

Every model call in the backend goes through one of two functions here:

* :func:`complete_json` -- a blocking JSON-mode completion.
* :func:`stream_text` -- a streamed text completion.

Both take a preferred provider, try it through
``utils.retry.retry_with_backoff``, and on a failure that is clearly the
provider's fault rather than ours -- a rate limit, a 5xx, a dropped connection
-- fall back **once** to the other provider with the same prompt, temperature,
and token budget. A 400/401/403/404/422 means our request is wrong; retrying it
elsewhere would only produce the same error twice, so those propagate
immediately.

Two rate limits are not the same thing:

* A **per-minute** limit clears on its own, so backoff is worth the seconds.
* A **daily** cap (Groq's free tier: "tokens per day (TPD)") does not clear
  today. Sleeping through the retries only makes the user wait for the same
  failure, so a daily cap skips the backoff entirely and falls back at once.

Streaming has one rule the blocking path does not need. Falling back is only
safe *before the first chunk reaches the user*: swapping models half way through
a reply would splice two different answers together, and the user would read the
seam. Once any text has been yielded, an error is surfaced as it is today --
the route persists the partial reply and sends an ``error`` event.

Which provider actually served a call is worth knowing without threading a
second return value through every caller, so the returned string and the
returned iterator both carry a ``provider`` attribute. Callers that may also be
handed a plain ``str`` (a test double, say) should read it with
:func:`provider_of`.
"""

import logging
from collections.abc import Iterator
from typing import Any

from app.core.config import settings
from app.services.azure_client import get_azure_client, get_deployment_name
from app.services.groq_client import get_groq_client, get_groq_model
from app.utils.retry import retry_with_backoff

logger = logging.getLogger(__name__)

GROQ = "groq"
AZURE = "azure"

PROVIDERS: tuple[str, ...] = (GROQ, AZURE)

# Substrings that mark a rate limit as a *daily* cap rather than a per-minute
# one. Groq's message reads "Rate limit reached ... Limit 200000, Used ...
# tokens per day (TPD)"; Azure phrases its daily quotas the same way.
DAILY_CAP_MARKERS: tuple[str, ...] = ("per day", "tpd", "per-day", "daily")

# HTTP statuses that mean *our request* is wrong. Sending the same request to
# the other provider would fail identically, so these never trigger a fallback
# and are never retried.
CLIENT_ERROR_STATUSES = frozenset({400, 401, 403, 404, 405, 409, 413, 422})

# Exception class names that mean the provider is unreachable or overloaded,
# matched by name so this module does not import the openai and groq SDKs.
AVAILABILITY_EXCEPTION_NAMES = frozenset(
    {
        "RateLimitError",
        "APIConnectionError",
        "APIConnectionTimeoutError",
        "APITimeoutError",
        "ConnectionError",
        "InternalServerError",
        "ServiceUnavailableError",
        "Timeout",
        "TimeoutError",
    }
)

# Matches the call sites this layer replaced: extraction and analysis retried
# four times, the chat stream three.
DEFAULT_MAX_ATTEMPTS = 4
DEFAULT_BASE_DELAY = 1.0


class _SkipRetries(Exception):
    """Internal marker: this failure must not be retried, only fallen back from.

    ``utils.retry.is_retryable`` matches on the exception's class name, and this
    name is in neither retryable set, so wrapping an exception in it makes the
    backoff loop give up without sleeping. The original is re-raised by
    :func:`_attempt` -- callers never see this class.
    """

    def __init__(self, original: BaseException) -> None:
        super().__init__(str(original))
        self.original = original


class ProviderText(str):
    """A completion string that remembers which provider produced it.

    A ``str`` subclass rather than a wrapper object so every existing caller --
    ``json.loads``, ``.strip()``, string comparison in tests -- keeps working
    untouched, and only the callers that care read ``.provider``.
    """

    provider: str

    def __new__(cls, text: str, provider: str) -> "ProviderText":
        instance = super().__new__(cls, text)
        instance.provider = provider
        return instance


class ProviderStream:
    """An iterator of text chunks that records which provider served them.

    ``provider`` is None until a stream has actually been opened, which is why
    the SSE ``done`` event carries it and the ``start`` event cannot: at
    ``start`` time no request has been made yet.
    """

    def __init__(self, chunks: Iterator[str]) -> None:
        self._chunks = chunks
        self.provider: str | None = None

    def __iter__(self) -> "ProviderStream":
        return self

    def __next__(self) -> str:
        return next(self._chunks)


def provider_of(value: Any, default: str | None = None) -> str | None:
    """Return the provider recorded on a value, or ``default``.

    Written defensively because a test double substitutes a plain ``str`` or a
    plain generator for a :class:`ProviderText` / :class:`ProviderStream`.
    """
    return getattr(value, "provider", None) or default


# --------------------------------------------------------------------------
# Failure classification
# --------------------------------------------------------------------------


def _error_text(exc: BaseException) -> str:
    """Return everything the provider said about a failure, lowercased.

    The SDKs put the human-readable reason in ``str(exc)`` and, separately, in
    a parsed ``body`` dict. A daily cap is only distinguishable from a
    per-minute one by that text, so both are searched.
    """
    parts = [str(exc)]
    body = getattr(exc, "body", None)
    if body is not None:
        parts.append(str(body))
    return " ".join(parts).lower()


def _status_code(exc: BaseException) -> int | None:
    """Return an exception's HTTP status, from either attribute the SDKs use."""
    for attribute in ("status_code", "http_status"):
        value = getattr(exc, attribute, None)
        if isinstance(value, int):
            return value
    response = getattr(exc, "response", None)
    value = getattr(response, "status_code", None)
    return value if isinstance(value, int) else None


def is_daily_cap(exc: BaseException) -> bool:
    """Return True when a rate limit is a daily cap rather than a per-minute one.

    A daily cap will still be there in thirty seconds, so it is the one case
    where retrying is strictly wasted time.
    """
    if not is_quota_or_availability_error(exc):
        return False
    text = _error_text(exc)
    return any(marker in text for marker in DAILY_CAP_MARKERS)


def is_quota_or_availability_error(exc: BaseException) -> bool:
    """Return True when a failure is the provider's fault, not the request's.

    Rate limits (429), server errors (5xx), and connection or timeout failures
    all mean "this provider cannot serve this right now", which is exactly the
    case the other provider can. A 4xx that is not 429 means the request itself
    is malformed or unauthorised and would fail identically anywhere.
    """
    status = _status_code(exc)
    if status is not None:
        if status == 429 or status >= 500:
            return True
        if status in CLIENT_ERROR_STATUSES or 400 <= status < 500:
            return False
    return type(exc).__name__ in AVAILABILITY_EXCEPTION_NAMES


def _other(provider: str) -> str:
    """Return the provider that is not this one."""
    return AZURE if provider == GROQ else GROQ


def _normalise(prefer: str) -> str:
    """Return a validated provider name, defaulting to Groq."""
    return prefer if prefer in PROVIDERS else GROQ


def is_configured(provider: str) -> bool:
    """Return True when this provider has credentials to be called with.

    Falling back to a provider with no key would swap a rate limit for an
    authentication error, which is a worse message for the same outcome.
    """
    if provider == GROQ:
        return bool(settings.groq_api_key)
    return bool(settings.azure_openai_endpoint and settings.azure_openai_api_key)


def _fallback_allowed(exc: BaseException, fallback: str, purpose: str) -> bool:
    """Decide whether ``exc`` justifies retrying the call on ``fallback``."""
    if not settings.llm_fallback_enabled:
        return False
    if not is_quota_or_availability_error(exc):
        return False
    if not is_configured(fallback):
        logger.warning(
            "cannot fall back to %s for %s: it has no credentials configured",
            fallback,
            purpose,
        )
        return False
    return True


# --------------------------------------------------------------------------
# Raw provider calls
# --------------------------------------------------------------------------


def _complete_groq_json(
    messages: list[dict[str, str]],
    *,
    max_tokens: int,
    temperature: float,
) -> str:
    """One blocking Groq completion in JSON mode."""
    completion = get_groq_client().chat.completions.create(
        model=get_groq_model(),
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )
    return completion.choices[0].message.content or ""


def _complete_azure_json(
    messages: list[dict[str, str]],
    *,
    max_tokens: int,
    temperature: float,
) -> str:
    """One blocking Azure GPT-4o completion in JSON mode.

    GPT-4o supports the same ``response_format`` as Groq, so a prompt written
    for one needs no rewriting to run on the other.
    """
    completion = get_azure_client().chat.completions.create(
        model=get_deployment_name(),
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )
    return completion.choices[0].message.content or ""


def _open_groq_stream(
    messages: list[dict[str, str]],
    *,
    max_tokens: int,
    temperature: float,
) -> Any:
    """Open a Groq streaming completion and return the SDK's chunk iterator."""
    return get_groq_client().chat.completions.create(
        model=get_groq_model(),
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
    )


def _open_azure_stream(
    messages: list[dict[str, str]],
    *,
    max_tokens: int,
    temperature: float,
) -> Any:
    """Open an Azure GPT-4o streaming completion."""
    return get_azure_client().chat.completions.create(
        model=get_deployment_name(),
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
    )


def _complete(
    provider: str,
    messages: list[dict[str, str]],
    *,
    max_tokens: int,
    temperature: float,
) -> str:
    """Dispatch a blocking JSON completion to one provider.

    Deliberately an if/else over module-level names rather than a lookup table
    built at import: a dict would capture the functions as they were when this
    module loaded, and a test that patches ``_complete_groq_json`` would find
    its double silently ignored -- and the real provider called instead.
    """
    if provider == GROQ:
        return _complete_groq_json(
            messages, max_tokens=max_tokens, temperature=temperature
        )
    return _complete_azure_json(
        messages, max_tokens=max_tokens, temperature=temperature
    )


def _open_stream(
    provider: str,
    messages: list[dict[str, str]],
    *,
    max_tokens: int,
    temperature: float,
) -> Any:
    """Dispatch a streaming completion to one provider, late-bound as above."""
    if provider == GROQ:
        return _open_groq_stream(
            messages, max_tokens=max_tokens, temperature=temperature
        )
    return _open_azure_stream(
        messages, max_tokens=max_tokens, temperature=temperature
    )


def chunk_text(chunk: Any) -> str:
    """Return the text a streamed chunk carries, or an empty string.

    Azure's content filter emits a leading chunk with no choices at all, and
    both SDKs emit chunks whose delta has no content, so every access is
    defensive.
    """
    choices = getattr(chunk, "choices", None) or []
    if not choices:
        return ""
    delta = getattr(choices[0], "delta", None)
    content = getattr(delta, "content", None) if delta is not None else None
    return content or ""


# --------------------------------------------------------------------------
# The attempt / fallback machinery
# --------------------------------------------------------------------------


def _attempt(
    call: Any,
    *,
    max_attempts: int,
    base_delay: float,
) -> Any:
    """Run one provider call with backoff, but never sleep through a daily cap.

    ``retry_with_backoff`` decides what to retry from the exception's class
    name and status, and it cannot know that one 429 clears in seconds while
    another lasts until midnight. Wrapping a daily cap in :class:`_SkipRetries`
    is how that distinction reaches the retry loop; the original exception is
    unwrapped again here so callers only ever see the provider's own error.
    """

    def guarded() -> Any:
        try:
            return call()
        except Exception as exc:
            if is_daily_cap(exc):
                raise _SkipRetries(exc) from exc
            raise

    runner = retry_with_backoff(max_attempts=max_attempts, base_delay=base_delay)(
        guarded
    )
    try:
        return runner()
    except _SkipRetries as skipped:
        raise skipped.original from None


def _log_fallback(primary: str, fallback: str, purpose: str) -> None:
    """Emit the single warning line that records a provider swap."""
    logger.warning(
        "%s rate-limited, falling back to %s for %s", primary, fallback, purpose
    )


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------


def complete_json(
    messages: list[dict[str, str]],
    *,
    max_tokens: int,
    temperature: float,
    prefer: str = GROQ,
    purpose: str = "completion",
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_delay: float = DEFAULT_BASE_DELAY,
) -> str:
    """Return a JSON-mode completion, falling back to the other provider once.

    Args:
        messages: An OpenAI-style messages list. Both providers take the same
            shape, so nothing is rewritten between them.
        max_tokens: Token ceiling, applied identically to both providers.
        temperature: Sampling temperature, applied identically to both.
        prefer: ``"groq"`` or ``"azure"``; the provider tried first.
        purpose: What this call is for, e.g. ``"resume extraction"``. Appears in
            the fallback log line and nowhere else.
        max_attempts: Attempts against the preferred provider before falling
            back. A daily cap collapses this to one.
        base_delay: Seconds before the second attempt; doubles from there.

    Returns:
        A :class:`ProviderText` -- a ``str`` carrying ``.provider``.

    Raises:
        Whatever the provider raised, once fallback is impossible or the
        fallback provider failed too.
    """
    primary = _normalise(prefer)
    fallback = _other(primary)

    def run(provider: str) -> str:
        return _attempt(
            lambda: _complete(
                provider, messages, max_tokens=max_tokens, temperature=temperature
            ),
            max_attempts=max_attempts,
            base_delay=base_delay,
        )

    try:
        return ProviderText(run(primary), primary)
    except Exception as exc:
        if not _fallback_allowed(exc, fallback, purpose):
            raise
        _log_fallback(primary, fallback, purpose)

    return ProviderText(run(fallback), fallback)


def stream_text(
    messages: list[dict[str, str]],
    *,
    max_tokens: int,
    temperature: float,
    prefer: str = GROQ,
    purpose: str = "chat",
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_delay: float = DEFAULT_BASE_DELAY,
) -> ProviderStream:
    """Stream a text completion, falling back only before the first chunk.

    The fallback window closes as soon as the user has seen a token. A reply
    whose first half came from one model and second half from another would
    contradict itself mid-sentence, so once anything has been yielded the
    failure is raised for the route to report as a partial reply -- exactly the
    behaviour there was before this layer existed.

    Args:
        messages: An OpenAI-style messages list.
        max_tokens: Token ceiling, applied identically to both providers.
        temperature: Sampling temperature, applied identically to both.
        prefer: ``"groq"`` or ``"azure"``; the provider tried first.
        purpose: What this call is for; appears in the fallback log line.
        max_attempts: Attempts against the preferred provider before falling
            back. A daily cap collapses this to one.
        base_delay: Seconds before the second attempt; doubles from there.

    Returns:
        A :class:`ProviderStream` of non-empty text chunks, whose ``provider``
        names the provider that served them once the first chunk has arrived.
    """
    primary = _normalise(prefer)
    fallback = _other(primary)
    handle: ProviderStream

    def open_stream(provider: str) -> Any:
        return _attempt(
            lambda: _open_stream(
                provider, messages, max_tokens=max_tokens, temperature=temperature
            ),
            max_attempts=max_attempts,
            base_delay=base_delay,
        )

    def serve(provider: str) -> Iterator[str]:
        """Yield the text chunks of one provider's stream."""
        for chunk in open_stream(provider):
            text = chunk_text(chunk)
            if text:
                handle.provider = provider
                yield text

    def generate() -> Iterator[str]:
        started = False
        try:
            for text in serve(primary):
                started = True
                yield text
            handle.provider = handle.provider or primary
            return
        except Exception as exc:
            # Mid-stream is past the point of no return: half a reply from each
            # model reads as a self-contradiction, so the error stands.
            if started or not _fallback_allowed(exc, fallback, purpose):
                raise
            _log_fallback(primary, fallback, purpose)

        yield from serve(fallback)
        handle.provider = handle.provider or fallback

    handle = ProviderStream(generate())
    return handle
