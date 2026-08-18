"""drop unused settings.onboarded column

Revision ID: 0015_drop_onboarded
Revises: 0014_learning_source_chunks
Create Date: 2026-08-03
"""
from alembic import op
import sqlalchemy as sa

revision = "0015_drop_onboarded"
down_revision = "0014_learning_source_chunks"
branch_labels = None
depends_on = None


def _has(col):
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return col in [c["name"] for c in insp.get_columns("settings")]


def upgrade() -> None:
    if _has("onboarded"):
        op.drop_column("settings", "onboarded")


def downgrade() -> None:
    if not _has("onboarded"):
        op.add_column("settings", sa.Column("onboarded", sa.Boolean(), nullable=False,
                      server_default="false"))
