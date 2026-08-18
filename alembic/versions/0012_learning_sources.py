"""learning source registry

Revision ID: 0012_learning_sources
Revises: 0011_learning_lessons_blocks
Create Date: 2026-06-28
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401

revision = "0012_learning_sources"
down_revision = "0011_learning_lessons_blocks"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    have = _tables()
    if "learningsource" not in have:
        op.create_table(
            "learningsource",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("title", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column("source_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="text"),
            sa.Column("trust_level", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="user"),
            sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="registered"),
            sa.Column("content_hash", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""),
            sa.Column("mime_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="text/plain"),
            sa.Column("original_name", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""),
            sa.Column("body_text", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""),
            sa.Column("metadata_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_learningsource_title", "learningsource", ["title"])
        op.create_index("ix_learningsource_content_hash", "learningsource", ["content_hash"])

    have = _tables()
    if "learningtracksource" not in have:
        op.create_table(
            "learningtracksource",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("track_id", sa.Integer(), sa.ForeignKey("learningtrack.id"), nullable=False),
            sa.Column("source_id", sa.Integer(), sa.ForeignKey("learningsource.id"), nullable=False),
            sa.Column("role", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="primary"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_learningtracksource_track_id", "learningtracksource", ["track_id"])
        op.create_index("ix_learningtracksource_source_id", "learningtracksource", ["source_id"])


def downgrade() -> None:
    have = _tables()
    if "learningtracksource" in have:
        op.drop_index("ix_learningtracksource_source_id", table_name="learningtracksource")
        op.drop_index("ix_learningtracksource_track_id", table_name="learningtracksource")
        op.drop_table("learningtracksource")
    have = _tables()
    if "learningsource" in have:
        op.drop_index("ix_learningsource_content_hash", table_name="learningsource")
        op.drop_index("ix_learningsource_title", table_name="learningsource")
        op.drop_table("learningsource")
