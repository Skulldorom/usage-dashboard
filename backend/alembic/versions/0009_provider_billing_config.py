"""add provider billing configuration

Revision ID: 0009_provider_billing_config
Revises: 0008_source_event_id_text
Create Date: 2026-09-03
"""

from alembic import op
import sqlalchemy as sa

revision = "0009_provider_billing_config"
down_revision = "0008_source_event_id_text"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("provider_configs") as batch_op:
        batch_op.add_column(sa.Column("pricing_model", sa.String(length=16), server_default="payg", nullable=False))
        batch_op.add_column(sa.Column("subscription_amount", sa.Numeric(12, 4), nullable=True))
        batch_op.add_column(sa.Column("subscription_currency", sa.String(length=3), server_default="USD", nullable=False))
        batch_op.add_column(sa.Column("billing_cadence", sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column("billing_anchor", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("provider_configs") as batch_op:
        batch_op.drop_column("billing_anchor")
        batch_op.drop_column("billing_cadence")
        batch_op.drop_column("subscription_currency")
        batch_op.drop_column("subscription_amount")
        batch_op.drop_column("pricing_model")
