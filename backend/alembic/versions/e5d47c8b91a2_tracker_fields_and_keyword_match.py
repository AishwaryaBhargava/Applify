"""tracker application fields and job_chats.keyword_match

Two independent additions, in one revision because they ship together.

**tracker_entries** grows the facts an application actually has: where the
posting is, where the job is, what it pays, where it was found, when it was
sent, what the user has to do next and by when, free-form notes, and a
priority. All nullable -- every one of them is optional, and a tracker row
created before this migration is still a valid row afterwards.

``applied_at`` is deliberately not derived from ``status``: the status is a
current state that can be corrected in both directions, while "when did I send
this" is a fact that happened once. The API stamps it on the first transition
into ``applied`` and never clears it.

**job_chats.keyword_match** holds the ATS keyword-match result for the chat: the
keywords extracted from the JD plus the deterministic match against the user's
profile. JSONB rather than its own table because there is exactly one live
result per chat and nothing queries across chats.

Revision ID: e5d47c8b91a2
Revises: c3a91f4b27d5
Create Date: 2026-09-05

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e5d47c8b91a2"
down_revision: str | None = "c3a91f4b27d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# (name, type) for every column added to tracker_entries. Kept as data so
# upgrade and downgrade cannot drift apart.
TRACKER_COLUMNS: tuple[tuple[str, sa.types.TypeEngine], ...] = (
    ("job_url", sa.Text()),
    ("location", sa.Text()),
    ("salary", sa.Text()),
    ("source", sa.Text()),
    ("applied_at", sa.DateTime(timezone=True)),
    ("next_action", sa.Text()),
    ("next_action_date", sa.Date()),
    ("notes", sa.Text()),
    ("priority", sa.String(length=16)),
)


def upgrade() -> None:
    """Add the tracker's application fields and the chat's keyword match."""
    for name, column_type in TRACKER_COLUMNS:
        op.add_column(
            "tracker_entries", sa.Column(name, column_type, nullable=True)
        )

    op.add_column(
        "job_chats",
        sa.Column("keyword_match", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    """Drop everything this revision added."""
    op.drop_column("job_chats", "keyword_match")

    for name, _ in reversed(TRACKER_COLUMNS):
        op.drop_column("tracker_entries", name)
