"""canvas_ics_url on settings

Revision ID: 0006_canvas_ics_url
Revises: 0005_active_timer
Create Date: 2026-06-14
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401

revision = "0006_canvas_ics_url"
down_revision = "0005_active_timer"
branch_labels = None
depends_on = None


def _has(col):
    insp = sa.inspect(op.get_bind())
    return col in [c["name"] for c in insp.get_columns("settings")]


def upgrade() -> None:
    if not _has("canvas_ics_url"):
        op.add_column("settings", sa.Column("canvas_ics_url", sa.String(),
                      nullable=False, server_default=""))


def downgrade() -> None:
    if _has("canvas_ics_url"):
        op.drop_column("settings", "canvas_ics_url")
