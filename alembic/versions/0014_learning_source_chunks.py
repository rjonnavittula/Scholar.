"""learning source chunks

Revision ID: 0014_learning_source_chunks
Revises: 0013_learning_source_sections
Create Date: 2026-06-30
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401

revision = "0014_learning_source_chunks"
down_revision = "0013_learning_source_sections"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    have = _tables()
    if "learningsourcechunk" not in have:
        op.create_table(
            "learningsourcechunk",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("source_id", sa.Integer(), sa.ForeignKey("learningsource.id"), nullable=False),
            sa.Column("section_id", sa.Integer(), sa.ForeignKey("learningsourcesection.id"), nullable=True),
            sa.Column("position", sa.Integer(), nullable=False),
            sa.Column("section_position", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("heading", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""),
            sa.Column("heading_path_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="[]"),
            sa.Column("body_text", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""),
            sa.Column("char_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("token_estimate", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("chunk_hash", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""),
            sa.Column("metadata_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_learningsourcechunk_source_id", "learningsourcechunk", ["source_id"])
        op.create_index("ix_learningsourcechunk_section_id", "learningsourcechunk", ["section_id"])
        op.create_index("ix_learningsourcechunk_position", "learningsourcechunk", ["position"])
        op.create_index("ix_learningsourcechunk_chunk_hash", "learningsourcechunk", ["chunk_hash"])


def downgrade() -> None:
    have = _tables()
    if "learningsourcechunk" in have:
        op.drop_index("ix_learningsourcechunk_chunk_hash", table_name="learningsourcechunk")
        op.drop_index("ix_learningsourcechunk_position", table_name="learningsourcechunk")
        op.drop_index("ix_learningsourcechunk_section_id", table_name="learningsourcechunk")
        op.drop_index("ix_learningsourcechunk_source_id", table_name="learningsourcechunk")
        op.drop_table("learningsourcechunk")
