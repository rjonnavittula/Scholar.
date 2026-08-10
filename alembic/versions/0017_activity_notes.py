"""activity notes field

Revision ID: 0017_activity_notes
Revises: 0016_tutor_mode
Create Date: 2026-08-09
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401

revision = "0017_activity_notes"
down_revision = "0016_tutor_mode"
branch_labels = None
depends_on = None


def _has(col):
    insp = sa.inspect(op.get_bind())
    return col in {c["name"] for c in insp.get_columns("activity")}


def upgrade() -> None:
    if not _has("notes"):
        op.add_column("activity", sa.Column("notes", sa.String(), nullable=False, server_default=""))


def downgrade() -> None:
    if _has("notes"):
        op.drop_column("activity", "notes")
