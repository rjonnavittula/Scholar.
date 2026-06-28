"""learning source sections

Revision ID: 0013_learning_source_sections
Revises: 0012_learning_sources
Create Date: 2026-06-28
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401

revision = "0013_learning_source_sections"
down_revision = "0012_learning_sources"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    have = _tables()
    if "learningsourcesection" not in have:
        op.create_table(
            "learningsourcesection",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("source_id", sa.Integer(), sa.ForeignKey("learningsource.id"), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False),
            sa.Column("heading", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column("level", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("body_text", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""),
            sa.Column("char_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("section_hash", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""),
            sa.Column("metadata_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_learningsourcesection_source_id", "learningsourcesection", ["source_id"])
        op.create_index("ix_learningsourcesection_position", "learningsourcesection", ["position"])
        op.create_index("ix_learningsourcesection_section_hash", "learningsourcesection", ["section_hash"])


def downgrade() -> None:
    have = _tables()
    if "learningsourcesection" in have:
        op.drop_index("ix_learningsourcesection_section_hash", table_name="learningsourcesection")
        op.drop_index("ix_learningsourcesection_position", table_name="learningsourcesection")
        op.drop_index("ix_learningsourcesection_source_id", table_name="learningsourcesection")
        op.drop_table("learningsourcesection")
