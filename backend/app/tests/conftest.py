"""Shared pytest fixtures.

There is no database in the test environment, and the models use Postgres-only
column types (``UUID``, ``JSONB``) that SQLite cannot host, so route tests run
against a :class:`FakeSession` injected through FastAPI's dependency overrides
rather than a real engine. The fake implements only the session surface the
services actually use, which is also a useful constraint: if a service starts
reaching for raw SQL, these tests break loudly.

``FakeSession.query`` is a real, if small, query engine: it evaluates the
SQLAlchemy filter and order_by expressions the services build against the rows
in memory. That matters for the rules this phase depends on -- "only your own
chats", "not the soft-deleted ones", "oldest message first" are all expressed as
filters, and a fake that ignored them would pass every test while leaking one
user's chats to another.
"""

import uuid
from typing import Any, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.sql import operators
from sqlalchemy.sql.elements import BinaryExpression, BooleanClauseList, Null

from app.data.deps import get_current_user, get_db
from app.main import app

# A fixed, valid UUID so tests can assert on the stored row's key.
TEST_USER_ID = "11111111-2222-3333-4444-555555555555"

# Another user, for the "never leak existence across users" tests.
OTHER_USER_ID = "99999999-8888-7777-6666-555555555555"


# --------------------------------------------------------------------------
# Expression evaluation
# --------------------------------------------------------------------------


def _bound_value(element: Any) -> Any:
    """Return the Python value on the right-hand side of a comparison."""
    if element is None or isinstance(element, Null):
        return None
    return getattr(element, "value", element)


def _evaluate(clause: Any, row: Any) -> bool:
    """Evaluate one SQLAlchemy filter expression against an in-memory row."""
    if isinstance(clause, BooleanClauseList):
        results = [_evaluate(part, row) for part in clause.clauses]
        if clause.operator is operators.or_:
            return any(results)
        return all(results)

    if not isinstance(clause, BinaryExpression):
        raise NotImplementedError(
            "FakeSession cannot evaluate {!r}".format(clause)
        )

    left = getattr(row, clause.left.key, None)
    right = _bound_value(clause.right)
    op = clause.operator

    if op is operators.eq:
        return left == right
    if op is operators.ne:
        return left != right
    if op is operators.is_:
        return left is right if right is None else left == right
    if op is operators.is_not:
        return left is not right if right is None else left != right
    if op is operators.in_op:
        return left in list(right or [])
    if op is operators.not_in_op:
        return left not in list(right or [])
    if op is operators.lt:
        return left < right
    if op is operators.le:
        return left <= right
    if op is operators.gt:
        return left > right
    if op is operators.ge:
        return left >= right

    raise NotImplementedError("FakeSession does not support {}".format(op))


class FakeQuery:
    """The slice of ``Query`` the services use, evaluated in Python."""

    def __init__(self, rows: list[Any]) -> None:
        self._rows = list(rows)

    def filter(self, *criteria: Any) -> "FakeQuery":
        """Keep the rows every criterion matches."""
        return FakeQuery(
            [row for row in self._rows if all(_evaluate(c, row) for c in criteria)]
        )

    def order_by(self, *expressions: Any) -> "FakeQuery":
        """Sort by one or more columns, honouring ``.asc()`` / ``.desc()``."""
        rows = list(self._rows)
        # Applied right to left so the first expression is the primary sort.
        for expression in reversed(expressions):
            element = getattr(expression, "element", expression)
            descending = getattr(expression, "modifier", None) is operators.desc_op
            rows.sort(
                key=lambda row, key=element.key: getattr(row, key),
                reverse=descending,
            )
        return FakeQuery(rows)

    def all(self) -> list[Any]:
        """Return every matching row."""
        return list(self._rows)

    def first(self) -> Any:
        """Return the first matching row, or None."""
        return self._rows[0] if self._rows else None

    def one_or_none(self) -> Any:
        """Return the single matching row, None, or raise if there are several."""
        if len(self._rows) > 1:
            raise AssertionError("one_or_none() matched {} rows".format(len(self._rows)))
        return self.first()

    def count(self) -> int:
        """Return how many rows match."""
        return len(self._rows)


class FakeSession:
    """An in-memory stand-in for a SQLAlchemy ``Session``.

    Rows live in ``store``, keyed by ``(model, primary key)``. ``commit`` only
    records that it happened -- the objects are already the live ones, exactly
    as they are with ``expire_on_commit=False``.
    """

    def __init__(self) -> None:
        self.store: dict[tuple[type, Any], Any] = {}
        self.commits = 0
        self.closed = False
        self._sequence = 0

    # -- session surface ---------------------------------------------------

    def _key(self, instance: Any) -> tuple[type, Any]:
        """Key a row by its model and primary key value."""
        pk_column = sa_inspect(type(instance)).primary_key[0]
        value = getattr(instance, pk_column.key, None)
        if value is None:
            # The services assign ids explicitly; anything that does not gets a
            # synthetic key so it is still stored exactly once.
            self._sequence += 1
            value = "unkeyed-{}".format(self._sequence)
        return (type(instance), value)

    def get(self, model: type, primary_key: Any) -> Any:
        """Return the stored row for a primary key, or None."""
        return self.store.get((model, primary_key))

    def add(self, instance: Any) -> None:
        """Stage a new row, keyed by its primary key."""
        self.store[self._key(instance)] = instance

    def delete(self, instance: Any) -> None:
        """Remove a staged row."""
        self.store.pop(self._key(instance), None)

    def query(self, model: type) -> FakeQuery:
        """Return a query over every stored row of one model.

        Rows are handed out in insertion order, which is what makes the
        ``order_by`` results deterministic when timestamps tie.
        """
        return FakeQuery(
            [row for (kind, _), row in self.store.items() if kind is model]
        )

    def commit(self) -> None:
        """Record a commit. Nothing to flush -- the objects are already live."""
        self.commits += 1

    def rollback(self) -> None:
        """Accepted and ignored: nothing here is transactional."""

    def flush(self) -> None:
        """Accepted and ignored: ``add`` is already visible to ``query``."""

    def close(self) -> None:
        """Mark the session closed, as ``get_db`` does in its finally block."""
        self.closed = True

    # -- test conveniences -------------------------------------------------

    def seed(self, instance: Any) -> Any:
        """Pre-load a row as though it were already in the database."""
        self.add(instance)
        return instance

    def rows(self, model: type) -> list[Any]:
        """Every stored row of one model, in insertion order."""
        return [row for (kind, _), row in self.store.items() if kind is model]


@pytest.fixture(scope="session")
def client() -> TestClient:
    """A TestClient bound to the real FastAPI app, with no overrides applied.

    Used by the auth-guard tests, which must see the real ``get_current_user``.
    No database connection is opened: SQLAlchemy's engine is lazy, and an
    unauthenticated request is rejected before any route body runs.
    """
    return TestClient(app)


@pytest.fixture
def db() -> FakeSession:
    """A fresh in-memory session for one test."""
    return FakeSession()


@pytest.fixture
def auth_client(db: FakeSession) -> Iterator[TestClient]:
    """A TestClient with ``get_db`` and ``get_current_user`` overridden.

    Requests arrive already authenticated as ``TEST_USER_ID`` and every route
    shares the ``db`` fixture's session, so a test can assert on what a request
    actually wrote.
    """
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: TEST_USER_ID
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def test_user_uuid() -> uuid.UUID:
    """``TEST_USER_ID`` as the UUID the profiles table is keyed by."""
    return uuid.UUID(TEST_USER_ID)
