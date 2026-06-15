"""appearance settings columns (theme, accent, density, fontscale, default_view)

Revision ID: 0002_appearance
Revises: 0001_baseline
Create Date: 2026-06-12
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401

revision = "0002_appearance"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

_COLS = [
    ("theme", sa.String(), "dark"),
    ("accent", sa.String(), "#8A7F73"),
    ("density", sa.Float(), 1.0),
    ("fontscale", sa.Float(), 1.0),
    ("default_view", sa.String(), "week"),
]


def _has(col):
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return col in [c["name"] for c in insp.get_columns("settings")]


def upgrade() -> None:
    for name, typ, default in _COLS:
        if not _has(name):
            op.add_column("settings", sa.Column(name, typ, nullable=False,
                          server_default=str(default)))


def downgrade() -> None:
    for name, _, _ in _COLS:
        if _has(name):
            op.drop_column("settings", name)
