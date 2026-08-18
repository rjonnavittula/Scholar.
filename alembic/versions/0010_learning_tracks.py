"""learning tracks/modules/nodes

Revision ID: 0010_learning_tracks
Revises: 0009_canvas_autosync
Create Date: 2026-06-27
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401

revision = "0010_learning_tracks"
down_revision = "0009_canvas_autosync"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    have = _tables()
    if "learningtrack" not in have:
        op.create_table(
            "learningtrack",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("title", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column("input_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="source_text"),
            sa.Column("role", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""),
            sa.Column("source_hash", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""),
            sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="draft"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_learningtrack_title", "learningtrack", ["title"])
        op.create_index("ix_learningtrack_source_hash", "learningtrack", ["source_hash"])

    have = _tables()
    if "learningmodule" not in have:
        op.create_table(
            "learningmodule",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("track_id", sa.Integer(), sa.ForeignKey("learningtrack.id"), nullable=False),
            sa.Column("title", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False),
            sa.Column("exp", sa.Integer(), nullable=False, server_default="100"),
            sa.Column("locked", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("completed", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("mastery", sa.Float(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_learningmodule_track_id", "learningmodule", ["track_id"])
        op.create_index("ix_learningmodule_position", "learningmodule", ["position"])

    have = _tables()
    if "learningnode" not in have:
        op.create_table(
            "learningnode",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("module_id", sa.Integer(), sa.ForeignKey("learningmodule.id"), nullable=False),
            sa.Column("title", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False),
            sa.Column("node_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="lesson"),
            sa.Column("exp", sa.Integer(), nullable=False, server_default="50"),
            sa.Column("locked", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("completed", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("mastery", sa.Float(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_learningnode_module_id", "learningnode", ["module_id"])
        op.create_index("ix_learningnode_position", "learningnode", ["position"])


def downgrade() -> None:
    have = _tables()
    if "learningnode" in have:
        op.drop_index("ix_learningnode_position", table_name="learningnode")
        op.drop_index("ix_learningnode_module_id", table_name="learningnode")
        op.drop_table("learningnode")
    have = _tables()
    if "learningmodule" in have:
        op.drop_index("ix_learningmodule_position", table_name="learningmodule")
        op.drop_index("ix_learningmodule_track_id", table_name="learningmodule")
        op.drop_table("learningmodule")
    have = _tables()
    if "learningtrack" in have:
        op.drop_index("ix_learningtrack_source_hash", table_name="learningtrack")
        op.drop_index("ix_learningtrack_title", table_name="learningtrack")
        op.drop_table("learningtrack")
