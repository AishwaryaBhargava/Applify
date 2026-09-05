"""add kind to chat_messages

Phase 6 gives every chat message a ``kind``: what produced it. A normal
conversational turn is ``chat``; the message that renders a completed analysis
is ``analysis``; a generated document is ``resume``, ``cover_letter``, or
``answer`` (Phase 7 fills those in). The frontend renders each differently, so
it needs the discriminator on the row rather than having to infer it.

The column is NOT NULL with a server default of ``'chat'``, so every row written
before this migration -- and any writer that does not know about the column --
lands as a plain chat turn.

Revision ID: c3a91f4b27d5
Revises: b7f2c9a41d38
Create Date: 2026-09-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3a91f4b27d5"
down_revision: str | None = "b7f2c9a41d38"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add ``chat_messages.kind``, defaulting existing rows to 'chat'."""
    op.add_column(
        "chat_messages",
        sa.Column(
            "kind",
            sa.String(length=32),
            server_default=sa.text("'chat'"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Drop ``chat_messages.kind``."""
    op.drop_column("chat_messages", "kind")
