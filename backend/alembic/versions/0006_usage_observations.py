"""normalized analytics observations"""

from alembic import op
import sqlalchemy as sa

revision = "0006_usage_observations"
down_revision = "0005_alert_thresholds"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "usage_observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider_config_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("metric", sa.String(length=120), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reset_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["provider_config_id"], ["provider_configs.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_usage_observations_provider_config_id", "usage_observations", ["provider_config_id"])
    op.create_index("ix_usage_observations_provider", "usage_observations", ["provider"])
    op.create_index("ix_usage_observations_metric", "usage_observations", ["metric"])
    op.create_index("ix_usage_observations_observed_at", "usage_observations", ["observed_at"])


def downgrade() -> None:
    op.drop_index("ix_usage_observations_observed_at", table_name="usage_observations")
    op.drop_index("ix_usage_observations_metric", table_name="usage_observations")
    op.drop_index("ix_usage_observations_provider", table_name="usage_observations")
    op.drop_index("ix_usage_observations_provider_config_id", table_name="usage_observations")
    op.drop_table("usage_observations")
