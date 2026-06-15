"""display_name on settings

Revision ID: 0003_display_name
Revises: 0002_appearance
Create Date: 2026-06-13
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401

revision = "0003_display_name"
down_revision = "0002_appearance"
branch_labels = None
depends_on = None


def _has(col):
    insp = sa.inspect(op.get_bind())
    return col in [c["name"] for c in insp.get_columns("settings")]


def upgrade() -> None:
    if not _has("display_name"):
        op.add_column("settings", sa.Column("display_name", sa.String(),
                      nullable=False, server_default=""))


def downgrade() -> None:
    if _has("display_name"):
        op.drop_column("settings", "display_name")
