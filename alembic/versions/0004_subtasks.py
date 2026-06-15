"""parent_id on task (subtasks)

Revision ID: 0004_subtasks
Revises: 0003_display_name
Create Date: 2026-06-13
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401

revision = "0004_subtasks"
down_revision = "0003_display_name"
branch_labels = None
depends_on = None


def _has(col):
    insp = sa.inspect(op.get_bind())
    return col in [c["name"] for c in insp.get_columns("task")]


def upgrade() -> None:
    if not _has("parent_id"):
        op.add_column("task", sa.Column("parent_id", sa.Integer(), nullable=True))
        op.create_index("ix_task_parent_id", "task", ["parent_id"])


def downgrade() -> None:
    if _has("parent_id"):
        op.drop_index("ix_task_parent_id", "task")
        op.drop_column("task", "parent_id")
