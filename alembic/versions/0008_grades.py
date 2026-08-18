"""grade categories + items

Revision ID: 0008_grades
Revises: 0007_course_details
Create Date: 2026-06-16
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401

revision = "0008_grades"
down_revision = "0007_course_details"
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    tables = set(insp.get_table_names())
    if "gradecategory" not in tables:
        op.create_table(
            "gradecategory",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("course_id", sa.Integer(), sa.ForeignKey("course.id"), nullable=False, index=True),
            sa.Column("name", sa.String(), nullable=False, server_default=""),
            sa.Column("weight", sa.Float(), nullable=False, server_default="0"),
            sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        )
    if "gradeitem" not in tables:
        op.create_table(
            "gradeitem",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("category_id", sa.Integer(), sa.ForeignKey("gradecategory.id"), nullable=False, index=True),
            sa.Column("course_id", sa.Integer(), sa.ForeignKey("course.id"), nullable=False, index=True),
            sa.Column("title", sa.String(), nullable=False, server_default=""),
            sa.Column("earned", sa.Float(), nullable=False, server_default="0"),
            sa.Column("possible", sa.Float(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    tables = set(insp.get_table_names())
    if "gradeitem" in tables:
        op.drop_table("gradeitem")
    if "gradecategory" in tables:
        op.drop_table("gradecategory")
