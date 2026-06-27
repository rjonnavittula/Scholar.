"""learning lessons and blocks

Revision ID: 0011_learning_lessons_blocks
Revises: 0010_learning_tracks
Create Date: 2026-06-27
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401

revision = "0011_learning_lessons_blocks"
down_revision = "0010_learning_tracks"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    have = _tables()
    if "learninglesson" not in have:
        op.create_table(
            "learninglesson",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("node_id", sa.Integer(), sa.ForeignKey("learningnode.id"), nullable=False),
            sa.Column("title", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="draft"),
            sa.Column("estimated_min", sa.Integer(), nullable=False, server_default="10"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_learninglesson_node_id", "learninglesson", ["node_id"])

    have = _tables()
    if "learningblock" not in have:
        op.create_table(
            "learningblock",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("lesson_id", sa.Integer(), sa.ForeignKey("learninglesson.id"), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False),
            sa.Column("block_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="text"),
            sa.Column("title", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""),
            sa.Column("payload_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="{}"),
            sa.Column("source_refs_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="[]"),
            sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_learningblock_lesson_id", "learningblock", ["lesson_id"])
        op.create_index("ix_learningblock_position", "learningblock", ["position"])


def downgrade() -> None:
    have = _tables()
    if "learningblock" in have:
        op.drop_index("ix_learningblock_position", table_name="learningblock")
        op.drop_index("ix_learningblock_lesson_id", table_name="learningblock")
        op.drop_table("learningblock")
    have = _tables()
    if "learninglesson" in have:
        op.drop_index("ix_learninglesson_node_id", table_name="learninglesson")
        op.drop_table("learninglesson")
