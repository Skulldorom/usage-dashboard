"""persist independently verifiable OpenRouter analytics coverage windows

Revision ID: 0016_openrouter_analytics_windows
Revises: 0015_openrouter_analytics_state
"""
from alembic import op
import sqlalchemy as sa

revision = "0016_openrouter_analytics_windows"
down_revision = "0015_openrouter_analytics_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "openrouter_analytics_windows",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider_config_id", sa.Integer(), sa.ForeignKey("provider_configs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("config_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("workspace_id", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("grouping", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_empty", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("provider_config_id", "config_revision", "scope", "workspace_id", "grouping", "window_start", "window_end", name="uq_openrouter_analytics_window_identity"),
    )
    op.create_index("ix_openrouter_analytics_windows_lookup", "openrouter_analytics_windows", ["provider_config_id", "config_revision", "scope", "workspace_id", "grouping", "window_start"])


def downgrade() -> None:
    op.drop_index("ix_openrouter_analytics_windows_lookup", table_name="openrouter_analytics_windows")
    op.drop_table("openrouter_analytics_windows")
