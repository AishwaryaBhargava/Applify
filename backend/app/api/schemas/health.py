"""Response schema for ``GET /health``."""

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """What the health endpoint reports.

    ``status`` stays ``"ok"`` for as long as the process answers at all: it is
    liveness, not readiness. A database that is unreachable shows up as
    ``db: "error"`` beside it rather than as a failed request, so a monitor can
    tell "the app is down" from "the app is up and Postgres is not".
    """

    status: str = Field(description='Always "ok" while the process is serving.')
    db: str = Field(description='"ok" when SELECT 1 succeeded, "error" otherwise.')
    version: str = Field(
        description="Short git sha of the running build, or 'dev' when unknown."
    )
