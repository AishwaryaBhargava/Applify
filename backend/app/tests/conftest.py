"""Shared pytest fixtures."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client() -> TestClient:
    """A TestClient bound to the real FastAPI app.

    No database connection is opened: SQLAlchemy's engine is lazy, and no test
    in this module exercises a route that reaches the database.
    """
    return TestClient(app)
