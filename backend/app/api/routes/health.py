"""Health check route. The only unprotected endpoint in the API."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness probe used by Render and by the frontend connection check."""
    return {"status": "ok"}
