"""tutor dynamic tools (Phase 4: tool authoring)

Revision ID: 0019_tutor_dynamic_tools
Revises: 0018_tutor_tool_calls
Create Date: 2026-08-11
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401

revision = "0019_tutor_dynamic_tools"
down_revision = "0018_tutor_tool_calls"
branch_labels = None
depends_on = None


def _tables():
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if "tutordynamictool" not in _tables():
        op.create_table(
            "tutordynamictool",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("track_id", sa.Integer(), sa.ForeignKey("learningtrack.id"), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("description", sa.String(), nullable=False, server_default=""),
            sa.Column("parameters_schema", sa.String(), nullable=False, server_default="{}"),
            sa.Column("code", sa.String(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_tutordynamictool_track_id", "tutordynamictool", ["track_id"])


def downgrade() -> None:
    if "tutordynamictool" in _tables():
        op.drop_index("ix_tutordynamictool_track_id", table_name="tutordynamictool")
        op.drop_table("tutordynamictool")
