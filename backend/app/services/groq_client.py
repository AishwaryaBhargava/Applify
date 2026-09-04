"""Shared Groq client.

Groq handles fast conversational responses and quick snapshot analysis. One
client instance is shared by the chat and analysis services.

The model is never hardcoded -- always read :func:`get_groq_model`, which
resolves ``GROQ_MODEL`` from settings. The tech stack doc names
``llama-3.3-70b-versatile``, but that model is decommissioned on this account;
the default is now ``openai/gpt-oss-120b``.
"""

from functools import lru_cache

from groq import Groq

from app.core.config import settings

# gpt-oss models spend tokens on reasoning before emitting any answer, so a low
# max_tokens truncates the reply to nothing. Never go below this.
MIN_MAX_TOKENS = 256


@lru_cache
def get_groq_client() -> Groq:
    """Return the process-wide Groq client.

    Built lazily so importing this module never requires a Groq API key.
    """
    return Groq(api_key=settings.groq_api_key)


def get_groq_model() -> str:
    """Return the configured Groq chat model id."""
    return settings.groq_model
