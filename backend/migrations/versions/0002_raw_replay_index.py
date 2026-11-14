"""Index the raw-record replay cursor.

Revision ID: 0002_raw_replay_index
Revises: 0001_initial_schema
"""

from alembic import op

revision = "0002_raw_replay_index"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_raw_event_records_replay_cursor", "raw_event_records", ["created_at", "id"])


def downgrade() -> None:
    op.drop_index("ix_raw_event_records_replay_cursor", table_name="raw_event_records")
