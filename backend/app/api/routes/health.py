"""Health check route. The only unprotected endpoint in the API.

Two consumers, one payload. Render polls it to decide whether a deploy is live
and whether an instance should stay in rotation; the frontend polls it for the
connection pill in the header. Both want a fast, honest answer, and neither is
helped by a 500 -- Render would recycle a healthy instance over a database blip,
and the pill would go red for a backend that is actually up.

So the status code is always 200 while the process is answering at all, and the
detail lives in the body: ``db`` says whether Postgres answered, ``version``
says which build answered.
"""

from fastapi import APIRouter

from app.api.schemas.health import HealthResponse
from app.core.version import app_version
from app.data.database import check_database

router = APIRouter(tags=["health"])

DB_OK = "ok"
DB_ERROR = "error"


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Report liveness, database reachability, and the running build.

    The database probe is a ``SELECT 1`` on a pooled connection with a two
    second ceiling, and it never raises -- see
    :func:`app.data.database.check_database`.
    """
    return HealthResponse(
        status="ok",
        db=DB_OK if check_database() else DB_ERROR,
        version=app_version(),
    )
