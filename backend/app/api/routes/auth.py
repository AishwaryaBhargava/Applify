"""Auth route.

The backend never talks to Supabase Auth -- the frontend owns sign-in, sign-up,
and session refresh through the Supabase JS client. All this backend does is
verify the JWT that arrives on each request, and that logic lives in
``app/utils/auth.py`` plus the ``get_current_user`` dependency in
``app/data/deps.py``.

The single endpoint here lets the frontend confirm that a token the backend
receives is one the backend accepts.
"""

from fastapi import APIRouter

from app.data.deps import CurrentUser

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/verify")
def verify(user_id: CurrentUser) -> dict[str, str]:
    """Verify the bearer token and echo back the user id it resolves to."""
    return {"user_id": user_id}
