"""add normalized provider error details to usage snapshots

Revision ID: 0010_provider_error_details
Revises: 0009_provider_billing_config
Create Date: 2026-09-04
"""

from alembic import op
import sqlalchemy as sa

revision = "0010_provider_error_details"
down_revision = "0009_provider_billing_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("usage_snapshots") as batch_op:
        batch_op.add_column(sa.Column("error_details", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("usage_snapshots") as batch_op:
        batch_op.drop_column("error_details")
