"""active_timer table (global persistent timer)

Revision ID: 0005_active_timer
Revises: 0004_subtasks
Create Date: 2026-06-13
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401

revision = "0005_active_timer"
down_revision = "0004_subtasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "activetimer" not in insp.get_table_names():
        op.create_table(
            "activetimer",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("task_id", sa.Integer(), sa.ForeignKey("task.id"), nullable=False),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("accumulated_sec", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("paused", sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "activetimer" in insp.get_table_names():
        op.drop_table("activetimer")
