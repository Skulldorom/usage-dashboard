"""persist OpenRouter analytics query evidence separately from configuration

Revision ID: 0015_openrouter_analytics_state
Revises: 0014_native_observation_identity
"""

from alembic import op
import sqlalchemy as sa

revision = "0015_openrouter_analytics_state"
down_revision = "0014_native_observation_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "openrouter_analytics_states",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "provider_config_id", sa.Integer(), sa.ForeignKey("provider_configs.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("config_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("workspace_id", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("grouping", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("requested_start", sa.DateTime(timezone=True)),
        sa.Column("requested_end", sa.DateTime(timezone=True)),
        sa.Column("completed_start", sa.DateTime(timezone=True)),
        sa.Column("completed_end", sa.DateTime(timezone=True)),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("last_failure_at", sa.DateTime(timezone=True)),
        sa.Column("error_category", sa.String(length=64)),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("backfill_cursor", sa.DateTime(timezone=True)),
        sa.Column("backfill_complete", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint(
            "provider_config_id",
            "config_revision",
            "scope",
            "workspace_id",
            "grouping",
            name="uq_openrouter_analytics_state_scope",
        ),
    )
    op.create_index(
        "ix_openrouter_analytics_states_provider_config_id", "openrouter_analytics_states", ["provider_config_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_openrouter_analytics_states_provider_config_id", table_name="openrouter_analytics_states")
    op.drop_table("openrouter_analytics_states")
