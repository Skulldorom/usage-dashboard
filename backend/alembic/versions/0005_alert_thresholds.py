"""alert thresholds per provider"""
from alembic import op
import sqlalchemy as sa

revision = "0005_alert_thresholds"
down_revision = "0004_api_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "provider_configs",
        sa.Column("alert_thresholds", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )


def downgrade() -> None:
    op.drop_column("provider_configs", "alert_thresholds")
