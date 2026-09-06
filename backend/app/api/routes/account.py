"""Account route: permanent deletion of a user's data and their login.

Thin, like every other route here: :mod:`app.services.account_service` owns the
order of operations and the Supabase Admin call, and this module only maps its
two failure modes onto status codes.
"""

import logging

from fastapi import APIRouter, HTTPException, Response, status

from app.data.deps import CurrentUser, DbSession
from app.services import account_service
from app.services.account_service import (
    AUTH_DELETE_FAILED,
    NOT_CONFIGURED,
    AccountDeletionNotConfigured,
    AuthUserDeletionFailed,
)

router = APIRouter(prefix="/account", tags=["account"])

logger = logging.getLogger(__name__)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(user_id: CurrentUser, db: DbSession) -> Response:
    """Delete the authenticated user's data and their Supabase login.

    Irreversible and unconfirmed by the API: the confirmation belongs in the UI,
    which is where the user can be told what they are about to lose. There is no
    body and no undo.

    What goes: the profile, every job chat, and -- by the ``ON DELETE CASCADE``
    on their chat foreign key -- every message, analysis, generated document,
    and tracker row. Then the Supabase Auth user, so the address can sign up
    again from scratch.

    Raises:
        HTTPException: 501 when the server has no ``SUPABASE_SERVICE_ROLE_KEY``,
            in which case **nothing is deleted** rather than half of it; 502
            when the rows were removed but Supabase Auth would not delete the
            login, with the request id in the message so support can find the
            log line.
    """
    try:
        account_service.delete_account(db, user_id)
    except AccountDeletionNotConfigured as exc:
        # Not a 500: the server is working exactly as configured, and the fix is
        # a deployment setting rather than a retry.
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, NOT_CONFIGURED) from exc
    except AuthUserDeletionFailed as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, AUTH_DELETE_FAILED) from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)
