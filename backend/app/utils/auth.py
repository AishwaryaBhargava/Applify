"""JWT decode and user-extraction helpers for Supabase-issued tokens.

Supabase signs access tokens two different ways depending on the project's age
and settings:

* **Asymmetric signing keys** (ES256, sometimes RS256) -- the default for
  projects created today. Tokens carry a ``kid`` in their header and are
  verified against the project's JWKS endpoint.
* **The legacy shared secret** (HS256, ``SUPABASE_JWT_SECRET``). Tokens carry no
  ``kid``.

:func:`decode_jwt` reads the *unverified* header to decide which applies --
JWKS first, HS256 as the fallback -- so the same code works before and after a
project migrates its signing keys, and no configuration flag has to be flipped.
Reading the unverified header is safe: it selects a verification strategy, and
the signature check that follows is what actually establishes trust.

Both paths enforce ``exp`` and require ``aud == "authenticated"``.
"""

from functools import lru_cache
from typing import Any

import jwt
from jwt import PyJWKClient, PyJWTError

from app.core.config import settings

# Asymmetric algorithms a Supabase project may use for its signing keys.
JWKS_ALGORITHMS = ("ES256", "RS256", "EdDSA")


class AuthError(Exception):
    """Raised when a token is missing, malformed, expired, or fails verification."""


@lru_cache
def get_jwks_client() -> PyJWKClient:
    """Return the cached JWKS client for this Supabase project.

    ``PyJWKClient`` caches fetched keys internally, and ``lru_cache`` keeps a
    single client for the process, so a normal request does not hit the network.

    Raises:
        AuthError: If ``SUPABASE_URL`` is not configured.
    """
    if not settings.supabase_jwks_url:
        raise AuthError(
            "SUPABASE_URL is not set, so JWKS-signed tokens cannot be verified"
        )
    return PyJWKClient(settings.supabase_jwks_url, cache_keys=True)


def _decode_options() -> dict[str, Any]:
    """Verification options shared by both strategies."""
    return {"require": ["exp", "sub"], "verify_exp": True, "verify_aud": True}


def _verify_token_jwks(token: str, algorithm: str | None) -> dict[str, Any]:
    """Verify a token signed with an asymmetric key, resolved through JWKS."""
    try:
        signing_key = get_jwks_client().get_signing_key_from_jwt(token)
    except AuthError:
        raise
    except Exception as exc:  # PyJWKClientError and network failures
        raise AuthError("Could not resolve signing key: {}".format(exc)) from exc

    algorithms = [algorithm] if algorithm in JWKS_ALGORITHMS else list(JWKS_ALGORITHMS)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=algorithms,
        audience=settings.jwt_audience,
        options=_decode_options(),
    )


def _verify_token_hs256(token: str) -> dict[str, Any]:
    """Verify a token signed with the legacy shared HS256 JWT secret."""
    if not settings.supabase_jwt_secret:
        raise AuthError("SUPABASE_JWT_SECRET is not set")
    return jwt.decode(
        token,
        settings.supabase_jwt_secret,
        algorithms=["HS256"],
        audience=settings.jwt_audience,
        options=_decode_options(),
    )


def _verify_token(token: str) -> dict[str, Any]:
    """Pick a verification strategy from the token's unverified header.

    A ``kid`` means the token was signed with a project signing key, so it is
    verified through JWKS. No ``kid`` means the legacy shared secret.
    """
    try:
        header = jwt.get_unverified_header(token)
    except PyJWTError as exc:
        raise AuthError("Malformed token header: {}".format(exc)) from exc

    if header.get("kid"):
        return _verify_token_jwks(token, header.get("alg"))
    return _verify_token_hs256(token)


def decode_jwt(token: str) -> dict[str, Any]:
    """Decode and verify a Supabase access token.

    Args:
        token: The raw JWT, without the ``Bearer`` prefix.

    Returns:
        The verified token claims.

    Raises:
        AuthError: If the token is empty, malformed, expired, has the wrong
            audience, or fails signature verification.
    """
    if not token:
        raise AuthError("Missing token")
    try:
        return _verify_token(token)
    except AuthError:
        raise
    except PyJWTError as exc:
        raise AuthError("Invalid token: {}".format(exc)) from exc


def extract_bearer_token(authorization: str | None) -> str:
    """Pull the raw token out of an ``Authorization: Bearer <token>`` header.

    Raises:
        AuthError: If the header is absent or not a well-formed Bearer header.
    """
    if not authorization:
        raise AuthError("Missing Authorization header")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AuthError("Authorization header must be in the form: Bearer <token>")
    return token.strip()


def get_user_id(claims: dict[str, Any]) -> str:
    """Return the Supabase user id (the ``sub`` claim) from verified claims.

    Raises:
        AuthError: If the token carries no subject.
    """
    user_id = claims.get("sub")
    if not user_id:
        raise AuthError("Token has no subject claim")
    return str(user_id)
