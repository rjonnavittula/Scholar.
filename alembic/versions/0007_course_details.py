"""course detail fields (instructor, url, notes, credits)

Revision ID: 0007_course_details
Revises: 0006_canvas_ics_url
Create Date: 2026-06-16
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401

revision = "0007_course_details"
down_revision = "0006_canvas_ics_url"
branch_labels = None
depends_on = None

_COLS = {
    "instructor": sa.Column("instructor", sa.String(), nullable=False, server_default=""),
    "url": sa.Column("url", sa.String(), nullable=False, server_default=""),
    "notes": sa.Column("notes", sa.String(), nullable=False, server_default=""),
    "credits": sa.Column("credits", sa.Float(), nullable=True),
}


def _have():
    insp = sa.inspect(op.get_bind())
    return {c["name"] for c in insp.get_columns("course")}


def upgrade() -> None:
    have = _have()
    for name, col in _COLS.items():
        if name not in have:
            op.add_column("course", col)


def downgrade() -> None:
    have = _have()
    for name in _COLS:
        if name in have:
            op.drop_column("course", name)
