"""tutor tool-call columns

Revision ID: 0018_tutor_tool_calls
Revises: 0017_activity_notes
Create Date: 2026-08-11
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401

revision = "0018_tutor_tool_calls"
down_revision = "0017_activity_notes"
branch_labels = None
depends_on = None

_COLS = {
    "tool_calls_json": sa.Column("tool_calls_json", sa.String(), nullable=True),
    "tool_name": sa.Column("tool_name", sa.String(), nullable=True),
}


def _have():
    insp = sa.inspect(op.get_bind())
    return {c["name"] for c in insp.get_columns("tutormessage")}


def upgrade() -> None:
    have = _have()
    for name, col in _COLS.items():
        if name not in have:
            op.add_column("tutormessage", col)


def downgrade() -> None:
    have = _have()
    for name in _COLS:
        if name in have:
            op.drop_column("tutormessage", name)
