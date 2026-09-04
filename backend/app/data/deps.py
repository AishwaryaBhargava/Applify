"""FastAPI dependencies: database session and authenticated user injection."""

from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.data.database import SessionLocal
from app.utils.auth import AuthError, decode_jwt, extract_bearer_token, get_user_id


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

    Applied to every protected route.

    Raises:
        HTTPException: 401 when the Authorization header is missing or the token
            is invalid or expired.
    """
    try:
        token = extract_bearer_token(authorization)
        claims = decode_jwt(token)
        return get_user_id(claims)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


# Convenience aliases for route signatures.
DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[str, Depends(get_current_user)]
