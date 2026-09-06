"""Tests for the health route and for the JWT verification guarding everything else.

The JWT tests sign their own tokens -- HS256 with a test secret, ES256 with a
freshly generated EC key whose JWKS lookup is monkeypatched -- so both
verification branches are covered without a live Supabase project.
"""

import datetime as dt

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from app.api.routes import health as health_route
from app.core.config import settings
from app.data.deps import get_db
from app.main import app
from app.tests.conftest import FakeSession
from app.utils import auth as auth_module
from app.utils.auth import AuthError, decode_jwt

TEST_SECRET = "test-jwt-secret-not-a-real-one-padded-to-32-bytes"
USER_ID = "11111111-2222-3333-4444-555555555555"


# --- /health ---------------------------------------------------------------


@pytest.fixture
def database_reachable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Report the database as reachable without opening a connection.

    The suite runs offline, and a health check that actually dialled Postgres
    would make these tests pass or fail on whether Docker happens to be up.
    """
    monkeypatch.setattr(health_route, "check_database", lambda: True)


def test_health_returns_ok(client: TestClient, database_reachable: None) -> None:
    """GET /health is unprotected and reports liveness, the database, and the build."""
    response = client.get("/health")
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert body["version"]


def test_health_reports_an_unreachable_database_without_failing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dead database is db: "error" with a 200, never a 5xx.

    The status code is what Render recycles an instance on, so a database blip
    must not read as "this process is broken".
    """
    monkeypatch.setattr(health_route, "check_database", lambda: False)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["db"] == "error"


def test_health_needs_no_auth(client: TestClient, database_reachable: None) -> None:
    """GET /health is the only route that works without an Authorization header."""
    assert client.get("/health").status_code == 200


# --- get_current_user rejection paths --------------------------------------


def test_protected_route_rejects_missing_token(client: TestClient) -> None:
    """get_current_user returns 401 when no Authorization header is sent."""
    response = client.get("/profile")
    assert response.status_code == 401
    assert response.json()["detail"] == "Missing Authorization header"


def test_protected_route_rejects_malformed_header(client: TestClient) -> None:
    """A non-Bearer Authorization header is rejected with 401."""
    response = client.get("/profile", headers={"Authorization": "Token abc123"})
    assert response.status_code == 401


def test_protected_route_rejects_garbage_token(client: TestClient) -> None:
    """A Bearer value that is not a JWT at all is rejected with 401."""
    response = client.get("/profile", headers={"Authorization": "Bearer not.a.jwt"})
    assert response.status_code == 401


# --- token helpers ---------------------------------------------------------


def _claims(**overrides: object) -> dict[str, object]:
    """Baseline Supabase-shaped claims: subject, audience, and a live expiry."""
    now = dt.datetime.now(dt.timezone.utc)
    claims: dict[str, object] = {
        "sub": USER_ID,
        "aud": "authenticated",
        "iat": now,
        "exp": now + dt.timedelta(hours=1),
    }
    claims.update(overrides)
    return claims


@pytest.fixture
def hs256_secret(monkeypatch: pytest.MonkeyPatch) -> str:
    """Point the HS256 fallback at a known test secret."""
    monkeypatch.setattr(settings, "supabase_jwt_secret", TEST_SECRET)
    return TEST_SECRET


@pytest.fixture
def es256_key(monkeypatch: pytest.MonkeyPatch) -> ec.EllipticCurvePrivateKey:
    """Generate an EC signing key and stub the JWKS lookup to return its public half."""
    private_key = ec.generate_private_key(ec.SECP256R1())

    class _StubSigningKey:
        key = private_key.public_key()

    class _StubJWKClient:
        def get_signing_key_from_jwt(self, token: str) -> _StubSigningKey:
            return _StubSigningKey()

    monkeypatch.setattr(auth_module, "get_jwks_client", lambda: _StubJWKClient())
    return private_key


# --- HS256 fallback branch (no kid) ----------------------------------------


def test_decode_jwt_accepts_hs256_token(hs256_secret: str) -> None:
    """A token with no kid falls back to the shared HS256 secret."""
    token = jwt.encode(_claims(), hs256_secret, algorithm="HS256")
    assert jwt.get_unverified_header(token).get("kid") is None

    claims = decode_jwt(token)
    assert claims["sub"] == USER_ID


def test_decode_jwt_rejects_hs256_token_with_wrong_secret(hs256_secret: str) -> None:
    """A bad signature is rejected."""
    token = jwt.encode(
        _claims(), "a-different-secret-also-padded-to-32-bytes", algorithm="HS256"
    )
    with pytest.raises(AuthError):
        decode_jwt(token)


def test_decode_jwt_rejects_expired_token(hs256_secret: str) -> None:
    """exp is enforced."""
    past = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)
    token = jwt.encode(
        _claims(exp=past, iat=past - dt.timedelta(hours=1)),
        hs256_secret,
        algorithm="HS256",
    )
    with pytest.raises(AuthError):
        decode_jwt(token)


def test_decode_jwt_rejects_wrong_audience(hs256_secret: str) -> None:
    """Only aud == "authenticated" is accepted."""
    token = jwt.encode(_claims(aud="anon"), hs256_secret, algorithm="HS256")
    with pytest.raises(AuthError):
        decode_jwt(token)


# --- JWKS branch (kid present) ---------------------------------------------


def test_decode_jwt_accepts_es256_token_via_jwks(
    es256_key: ec.EllipticCurvePrivateKey,
) -> None:
    """A token carrying a kid is verified against the JWKS signing key."""
    token = jwt.encode(
        _claims(), es256_key, algorithm="ES256", headers={"kid": "test-key-1"}
    )
    assert jwt.get_unverified_header(token)["kid"] == "test-key-1"

    claims = decode_jwt(token)
    assert claims["sub"] == USER_ID


def test_decode_jwt_rejects_es256_token_signed_by_another_key(
    es256_key: ec.EllipticCurvePrivateKey,
) -> None:
    """A kid token signed by a key the JWKS does not vouch for is rejected."""
    impostor = ec.generate_private_key(ec.SECP256R1())
    token = jwt.encode(
        _claims(), impostor, algorithm="ES256", headers={"kid": "test-key-1"}
    )
    with pytest.raises(AuthError):
        decode_jwt(token)


def test_decode_jwt_rejects_expired_es256_token(
    es256_key: ec.EllipticCurvePrivateKey,
) -> None:
    """exp is enforced on the JWKS branch too."""
    past = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=5)
    token = jwt.encode(
        _claims(exp=past, iat=past - dt.timedelta(hours=1)),
        es256_key,
        algorithm="ES256",
        headers={"kid": "test-key-1"},
    )
    with pytest.raises(AuthError):
        decode_jwt(token)


def test_jwks_branch_errors_clearly_without_supabase_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A kid token with SUPABASE_URL unset gives an actionable error, not a crash."""
    auth_module.get_jwks_client.cache_clear()
    monkeypatch.setattr(settings, "supabase_url", "")
    key = ec.generate_private_key(ec.SECP256R1())
    token = jwt.encode(_claims(), key, algorithm="ES256", headers={"kid": "k"})

    with pytest.raises(AuthError, match="SUPABASE_URL"):
        decode_jwt(token)
    auth_module.get_jwks_client.cache_clear()


# --- end-to-end through the dependency -------------------------------------


def test_protected_route_accepts_valid_hs256_token(
    client: TestClient, hs256_secret: str, db: FakeSession
) -> None:
    """A valid token passes get_current_user and the route body actually runs.

    The 404 is the point: the request got past authentication and reached
    GET /profile, which found no profile for this user. get_db is overridden so
    the assertion is about the token, not about a database being reachable.
    """
    app.dependency_overrides[get_db] = lambda: db
    try:
        token = jwt.encode(_claims(), hs256_secret, algorithm="HS256")
        response = client.get("/profile", headers={"Authorization": "Bearer " + token})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Profile not found"}


def test_auth_verify_returns_user_id(client: TestClient, hs256_secret: str) -> None:
    """POST /auth/verify echoes the user id resolved from the token."""
    token = jwt.encode(_claims(), hs256_secret, algorithm="HS256")
    response = client.post("/auth/verify", headers={"Authorization": "Bearer " + token})
    assert response.status_code == 200
    assert response.json() == {"user_id": USER_ID}


# --- the private-instance allowlist ----------------------------------------

# ALLOWED_USER_EMAILS turns a shared Supabase project into a personal
# deployment: the token is genuine, the signature verifies, and the user is
# still refused. That is a 403 rather than a 401 on purpose -- re-authenticating
# cannot help, and a 401 would send the frontend round a login loop.


@pytest.fixture
def allowlist(monkeypatch: pytest.MonkeyPatch):
    """Set ALLOWED_USER_EMAILS for one test."""

    def apply(raw: str) -> None:
        monkeypatch.setattr(settings, "allowed_user_emails_raw", raw)

    apply("")
    return apply


def _token(secret: str, **overrides: object) -> str:
    """Sign an HS256 token with the given extra claims."""
    return jwt.encode(_claims(**overrides), secret, algorithm="HS256")


def test_open_instance_accepts_any_verified_email(
    client: TestClient, hs256_secret: str, db: FakeSession, allowlist
) -> None:
    """An empty allowlist is the default and lets everyone through."""
    allowlist("")
    app.dependency_overrides[get_db] = lambda: db
    try:
        response = client.get(
            "/profile",
            headers={
                "Authorization": "Bearer "
                + _token(hs256_secret, email="anyone@example.com")
            },
        )
    finally:
        app.dependency_overrides.clear()

    # 404 rather than 200: the request reached the route, which found no
    # profile. Getting that far is the assertion.
    assert response.status_code == 404


def test_private_instance_accepts_a_listed_email(
    client: TestClient, hs256_secret: str, db: FakeSession, allowlist
) -> None:
    """A listed address is served exactly as before, case-insensitively."""
    allowlist("Owner@Example.com, teammate@example.com")
    app.dependency_overrides[get_db] = lambda: db
    try:
        response = client.get(
            "/profile",
            headers={
                "Authorization": "Bearer "
                + _token(hs256_secret, email="OWNER@example.com")
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


def test_private_instance_rejects_an_unlisted_email(
    client: TestClient, hs256_secret: str, allowlist
) -> None:
    """A valid token from someone else is a 403 that says why."""
    allowlist("owner@example.com")

    response = client.get(
        "/profile",
        headers={
            "Authorization": "Bearer "
            + _token(hs256_secret, email="stranger@example.com")
        },
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "This Applify instance is private."}


def test_private_instance_rejects_a_token_with_no_email(
    client: TestClient, hs256_secret: str, allowlist
) -> None:
    """No email claim means not on the list -- the safe direction."""
    allowlist("owner@example.com")

    response = client.get(
        "/profile", headers={"Authorization": "Bearer " + _token(hs256_secret)}
    )

    assert response.status_code == 403


def test_private_instance_reads_the_email_from_user_metadata(
    client: TestClient, hs256_secret: str, db: FakeSession, allowlist
) -> None:
    """Some providers put the address only in user_metadata."""
    allowlist("owner@example.com")
    app.dependency_overrides[get_db] = lambda: db
    try:
        response = client.get(
            "/profile",
            headers={
                "Authorization": "Bearer "
                + _token(hs256_secret, user_metadata={"email": "owner@example.com"})
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


def test_an_invalid_token_is_still_a_401_on_a_private_instance(
    client: TestClient, hs256_secret: str, allowlist
) -> None:
    """The allowlist is checked after verification, never instead of it."""
    allowlist("owner@example.com")

    response = client.get("/profile", headers={"Authorization": "Bearer nonsense"})

    assert response.status_code == 401


def test_allowed_user_emails_parses_and_folds_case() -> None:
    """Entries are trimmed, lower-cased, and de-duplicated."""
    from app.core.config import Settings

    parsed = Settings(ALLOWED_USER_EMAILS=" A@b.com , a@B.com ,, c@d.com ")
    assert parsed.allowed_user_emails == frozenset({"a@b.com", "c@d.com"})
    assert Settings(ALLOWED_USER_EMAILS="").allowed_user_emails == frozenset()
