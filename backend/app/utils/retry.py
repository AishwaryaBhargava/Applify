"""Exponential backoff for Azure and Groq rate limits.

Azure GPT-4o enforces per-minute token limits and detailed analysis / document
generation are long calls, so every Azure call is wrapped. Groq calls use the
same decorator for symmetry.
"""

import functools
import logging
import random
import time
from collections.abc import Callable
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Exception *names* treated as retryable. Matching on the name rather than the
# class avoids importing the openai and groq SDKs into this module.
RETRYABLE_EXCEPTION_NAMES = frozenset(
    {
        "RateLimitError",
        "APIConnectionError",
        "APITimeoutError",
        "InternalServerError",
        "ServiceUnavailableError",
    }
)


def is_retryable(exc: BaseException) -> bool:
    """Return True when an exception is a rate limit or a transient server error.

    Recognises SDK rate-limit classes by name and any exception exposing a
    ``status_code`` of 429 or 5xx.
    """
    if type(exc).__name__ in RETRYABLE_EXCEPTION_NAMES:
        return True
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int) and (status_code == 429 or status_code >= 500):
        return True
    return False


def retry_with_backoff(
    max_attempts: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    jitter: bool = True,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator retrying a callable with exponential backoff on 429 / 5xx.

    Args:
        max_attempts: Total attempts including the first call.
        base_delay: Seconds to wait before the second attempt; doubles each time.
        max_delay: Upper bound on any single wait.
        jitter: Add random jitter so concurrent callers do not retry in lockstep.

    Returns:
        A decorator preserving the wrapped function's signature.

    Raises:
        The last exception raised by the wrapped call once attempts are exhausted,
        and immediately for any exception that is not retryable.
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            delay = base_delay
            last_exc: BaseException | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:  # noqa: BLE001 - re-raised below
                    if not is_retryable(exc) or attempt == max_attempts:
                        raise
                    last_exc = exc
                    wait = min(delay, max_delay)
                    if jitter:
                        wait += random.uniform(0, wait * 0.25)
                    logger.warning(
                        "%s attempt %d/%d failed (%s); retrying in %.2fs",
                        func.__name__,
                        attempt,
                        max_attempts,
                        exc,
                        wait,
                    )
                    time.sleep(wait)
                    delay *= 2
            # Unreachable: the loop either returns or raises.
            raise RuntimeError("retry_with_backoff exhausted") from last_exc

        return wrapper

    return decorator
