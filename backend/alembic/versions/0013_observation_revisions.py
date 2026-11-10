"""isolate native analytics observations across credential revisions

Revision ID: 0013_observation_revisions
Revises: 0012_snapshot_revisions
"""

from alembic import op
import sqlalchemy as sa

revision = "0013_observation_revisions"
down_revision = "0012_snapshot_revisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("usage_observations") as batch_op:
        batch_op.add_column(sa.Column("config_revision", sa.Integer(), nullable=True))
        batch_op.create_index("ix_usage_observations_config_revision", ["config_revision"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("usage_observations") as batch_op:
        batch_op.drop_index("ix_usage_observations_config_revision")
        batch_op.drop_column("config_revision")
