"""tutor mode: track columns + tutor message log

Revision ID: 0016_tutor_mode
Revises: 0015_drop_onboarded
Create Date: 2026-08-04
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401

revision = "0016_tutor_mode"
down_revision = "0015_drop_onboarded"
branch_labels = None
depends_on = None

_COLS = [
    ("tutor_enabled", sa.Boolean(), "false"),
    ("tutor_system_prompt", sqlmodel.sql.sqltypes.AutoString(), ""),
]


def _has_col(table, col):
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return col in [c["name"] for c in insp.get_columns(table)]


def _tables():
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    for name, typ, default in _COLS:
        if not _has_col("learningtrack", name):
            op.add_column("learningtrack", sa.Column(name, typ, nullable=False, server_default=default))

    if "tutormessage" not in _tables():
        op.create_table(
            "tutormessage",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("track_id", sa.Integer(), sa.ForeignKey("learningtrack.id"), nullable=False),
            sa.Column("role", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="user"),
            sa.Column("content", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_tutormessage_track_id", "tutormessage", ["track_id"])


def downgrade() -> None:
    if "tutormessage" in _tables():
        op.drop_index("ix_tutormessage_track_id", table_name="tutormessage")
        op.drop_table("tutormessage")
    for name, _, _ in _COLS:
        if _has_col("learningtrack", name):
            op.drop_column("learningtrack", name)
