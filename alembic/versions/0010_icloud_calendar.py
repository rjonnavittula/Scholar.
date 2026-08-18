"""icloud calendar sync fields on settings

Revision ID: 0010_icloud_calendar
Revises: 0019_tutor_dynamic_tools
Create Date: 2026-08-16

Re-chained after merging origin/hive-courses: this and 0010_learning_tracks
both originally pointed to 0009_canvas_autosync (two branches never meant to
coexist -- they were built in separate, unmerged checkouts). Re-pointed to
come after the full learning/tutor chain rather than renumber 0011-0019,
which already reference each other by revision id, not filename order.
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401

revision = "0010_icloud_calendar"
down_revision = "0019_tutor_dynamic_tools"
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
