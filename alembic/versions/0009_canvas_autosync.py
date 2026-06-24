"""canvas auto-sync settings

Revision ID: 0009_canvas_autosync
Revises: 0008_grades
Create Date: 2026-06-16
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401

revision = "0009_canvas_autosync"
down_revision = "0008_grades"
branch_labels = None
depends_on = None

_COLS = {
    "canvas_autosync": sa.Column("canvas_autosync", sa.Boolean(), nullable=False, server_default=sa.false()),
    "canvas_sync_hours": sa.Column("canvas_sync_hours", sa.Integer(), nullable=False, server_default="12"),
    "canvas_last_sync": sa.Column("canvas_last_sync", sa.DateTime(), nullable=True),
}


def _have():
    insp = sa.inspect(op.get_bind())
    return {c["name"] for c in insp.get_columns("settings")}


def upgrade() -> None:
    have = _have()
    for name, col in _COLS.items():
        if name not in have:
            op.add_column("settings", col)


def downgrade() -> None:
    have = _have()
    for name in _COLS:
        if name in have:
            op.drop_column("settings", name)
