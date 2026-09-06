"""FastAPI dependencies: database session and authenticated user injection."""

from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.data.database import SessionLocal
from app.utils.auth import (
    AuthError,
    decode_jwt,
    extract_bearer_token,
    get_user_email,
    get_user_id,
    is_allowed_email,
)

# What a caller with a perfectly valid token sees when this instance is private
# and they are not on the list. Deliberately says nothing about who *is* on it.
PRIVATE_INSTANCE = "This Applify instance is private."


def get_db() -> Generator[Session, None, None]:
    """Yield a database session and always close it afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    """Verify the Supabase JWT on the request and return the user id.

    Applied to every protected route. When ``ALLOWED_USER_EMAILS`` is set, the
    token's verified ``email`` claim must appear on it -- the deployment switch
    that turns a shared Supabase project into a private instance without
    disabling sign-up in the dashboard.

    A rejected email is a **403**, not a 401: the token is genuine and retrying
    with a fresh one will not help, so telling the client to re-authenticate
    would send it round a login loop.

    Raises:
        HTTPException: 401 when the Authorization header is missing or the token
            is invalid or expired; 403 when the instance is private and the
            caller is not on the allowlist.
    """
    try:
        token = extract_bearer_token(authorization)
        claims = decode_jwt(token)
        user_id = get_user_id(claims)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    if not is_allowed_email(get_user_email(claims), settings.allowed_user_emails):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=PRIVATE_INSTANCE
        )
    return user_id


# Convenience aliases for route signatures.
DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[str, Depends(get_current_user)]
