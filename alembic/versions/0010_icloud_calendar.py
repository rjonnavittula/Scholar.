"""icloud calendar sync fields on settings

Revision ID: 0010_icloud_calendar
Revises: 0009_canvas_autosync
Create Date: 2026-08-16
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401

revision = "0010_icloud_calendar"
down_revision = "0009_canvas_autosync"
branch_labels = None
depends_on = None


def _has(col):
    insp = sa.inspect(op.get_bind())
    return col in [c["name"] for c in insp.get_columns("settings")]


def upgrade() -> None:
    if not _has("icloud_username"):
        op.add_column("settings", sa.Column("icloud_username", sa.String(),
                      nullable=False, server_default=""))
    if not _has("icloud_password"):
        op.add_column("settings", sa.Column("icloud_password", sa.String(),
                      nullable=False, server_default=""))
    if not _has("icloud_calendar_url"):
        op.add_column("settings", sa.Column("icloud_calendar_url", sa.String(),
                      nullable=False, server_default=""))
    if not _has("icloud_autosync"):
        op.add_column("settings", sa.Column("icloud_autosync", sa.Boolean(),
                      nullable=False, server_default=sa.false()))
    if not _has("icloud_sync_hours"):
        op.add_column("settings", sa.Column("icloud_sync_hours", sa.Integer(),
                      nullable=False, server_default="12"))
    if not _has("icloud_last_sync"):
        op.add_column("settings", sa.Column("icloud_last_sync", sa.DateTime(),
                      nullable=True))


def downgrade() -> None:
    for col in ("icloud_username", "icloud_password", "icloud_calendar_url",
                "icloud_autosync", "icloud_sync_hours", "icloud_last_sync"):
        if _has(col):
            op.drop_column("settings", col)
