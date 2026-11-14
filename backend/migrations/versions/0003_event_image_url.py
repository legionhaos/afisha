"""Add the optional event poster URL.

Revision ID: 0003_event_image_url
Revises: 0002_raw_replay_index
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_event_image_url"
down_revision = "0002_raw_replay_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    columns = [c["name"] for c in insp.get_columns("events")]
    if "image_url" not in columns:
        op.add_column("events", sa.Column("image_url", sa.Text(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    columns = [c["name"] for c in insp.get_columns("events")]
    if "image_url" in columns:
        op.drop_column("events", "image_url")
