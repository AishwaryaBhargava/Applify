"""Account deletion: remove a user's data, then remove their login.

Two systems hold something about a user. Postgres holds their profile and their
job chats, and every other table hangs off one of those two. Supabase Auth holds
the login itself, which this backend never otherwise touches -- the frontend
owns sign-in and this service verifies the tokens.

Deleting an account has to clear both, and the order is deliberate:

1. **Database first.** Rows are what a user asked to be forgotten.
2. **Auth second**, through the Supabase Admin API with the service role key.

Getting that order wrong is unrecoverable in a way this order is not. Deleting
the login first and then failing on the database leaves rows nobody can reach,
sign in as, or delete -- the user has no token any more. Failing the other way
round leaves a login with no data behind it, which the user can retry, and which
this service reports as a **502** naming exactly that state rather than
pretending the deletion worked.

The service role key bypasses row level security entirely. It lives in
``SUPABASE_SERVICE_ROLE_KEY``, it is never logged, and when it is unset the
route answers **501 and deletes nothing** -- a half-deleted account is worse
than a refused one.
"""

import logging
import uuid
from typing import Any

import httpx

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.job_chat import JobChat
from app.models.profile import Profile
from app.models.tracker_entry import TrackerEntry

logger = logging.getLogger(__name__)

# The admin call is a single small DELETE. Ten seconds is generous for it and
# short enough that a hung Supabase does not hold the request open.
AUTH_REQUEST_TIMEOUT = 10.0

# 404 counts as success: the login is already gone, which is the state the
# caller asked for. Retrying a partly finished deletion has to be able to
# finish rather than fail on the half that already worked.
AUTH_SUCCESS_STATUSES = frozenset({200, 202, 204, 404})

NOT_CONFIGURED = "Account deletion is not configured on this server."
AUTH_DELETE_FAILED = (
    "Your data was removed, but your login could not be deleted. "
    "Please contact support with the request id from this response."
)


class AccountDeletionNotConfigured(Exception):
    """Raised when SUPABASE_SERVICE_ROLE_KEY is unset, before anything is deleted."""


class AuthUserDeletionFailed(Exception):
    """Raised when the rows are gone but Supabase Auth would not delete the login."""


def deletion_is_configured() -> bool:
    """True when this deployment can complete an account deletion end to end."""
    return bool(settings.supabase_service_role_key and settings.supabase_url)


def _as_uuid(user_id: uuid.UUID | str) -> uuid.UUID:
    """Coerce a Supabase ``sub`` claim into the UUID the tables are keyed by."""
    if isinstance(user_id, uuid.UUID):
        return user_id
    return uuid.UUID(str(user_id))


def delete_user_rows(db: Session, user_id: uuid.UUID | str) -> dict[str, int]:
    """Delete everything this user owns and commit.

    Only two tables are addressed directly, because everything else hangs off
    ``job_chats`` by a foreign key declared ``ON DELETE CASCADE`` in the initial
    migration: ``chat_messages``, ``analyses``, ``generated_outputs``, and
    ``tracker_entries`` all go with the chat that owns them.

    ``tracker_entries`` is *also* swept by ``user_id``, and swept **first**, so
    the sweep and the cascade cannot both try to remove the same row. The
    cascade is real and would cover every tracker row that still has a chat;
    the sweep additionally catches one whose chat was already hard deleted by a
    partial earlier run. Deleting nothing is cheap; leaving a row behind in a
    "delete my account" flow is not.

    Soft-deleted chats are included: ``deleted_at`` hides a chat from the user,
    and this is not a read.

    Args:
        db: The active session.
        user_id: The Supabase user id.

    Returns:
        ``{"profiles": n, "chats": n, "tracker_entries": n}`` -- what was
        removed, for the log line.
    """
    key = _as_uuid(user_id)
    counts = {"profiles": 0, "chats": 0, "tracker_entries": 0}

    for entry in db.query(TrackerEntry).filter(TrackerEntry.user_id == key).all():
        db.delete(entry)
        counts["tracker_entries"] += 1
    # Flushed before the chats go, so the tracker deletes are already on the
    # wire when Postgres runs the cascade rather than racing it.
    db.flush()

    for chat in db.query(JobChat).filter(JobChat.user_id == key).all():
        db.delete(chat)
        counts["chats"] += 1

    profile = db.get(Profile, key)
    if profile is not None:
        db.delete(profile)
        counts["profiles"] = 1

    db.commit()
    return counts


def delete_auth_user(user_id: uuid.UUID | str) -> None:
    """Delete the Supabase Auth user through the Admin API.

    Raises:
        AccountDeletionNotConfigured: If the service role key or the project URL
            is unset. Checked again here so the function is safe to call on its
            own, not only after the route's check.
        AuthUserDeletionFailed: If Supabase is unreachable or refuses.
    """
    if not deletion_is_configured():
        raise AccountDeletionNotConfigured(NOT_CONFIGURED)

    url = "{}/auth/v1/admin/users/{}".format(
        settings.supabase_url.rstrip("/"), user_id
    )
    key = settings.supabase_service_role_key
    headers = {
        "apikey": key,
        "Authorization": "Bearer {}".format(key),
    }

    try:
        response = httpx.delete(url, headers=headers, timeout=AUTH_REQUEST_TIMEOUT)
    except Exception as exc:
        raise AuthUserDeletionFailed(
            "Supabase Auth was unreachable: {}".format(exc)
        ) from exc

    if response.status_code not in AUTH_SUCCESS_STATUSES:
        # The body can echo the request, and the request carried the service
        # role key in a header. Only the status code is quoted.
        raise AuthUserDeletionFailed(
            "Supabase Auth returned {}".format(response.status_code)
        )


def delete_account(db: Session, user_id: uuid.UUID | str) -> dict[str, Any]:
    """Delete a user's rows, then their login.

    Args:
        db: The active session.
        user_id: The Supabase user id.

    Returns:
        The row counts from :func:`delete_user_rows`.

    Raises:
        AccountDeletionNotConfigured: If the server has no service role key. In
            that case **nothing is deleted** -- the check runs first.
        AuthUserDeletionFailed: If the rows are gone but the login is not. The
            route answers 502; the counts are logged either way.
    """
    if not deletion_is_configured():
        raise AccountDeletionNotConfigured(NOT_CONFIGURED)

    counts = delete_user_rows(db, user_id)
    logger.info(
        "deleted account rows for %s: %s profile(s), %s chat(s), %s tracker row(s)",
        user_id,
        counts["profiles"],
        counts["chats"],
        counts["tracker_entries"],
    )

    try:
        delete_auth_user(user_id)
    except AuthUserDeletionFailed:
        logger.error(
            "account rows for %s were deleted but the Supabase Auth user was not",
            user_id,
        )
        raise

    logger.info("deleted Supabase Auth user %s", user_id)
    return counts
