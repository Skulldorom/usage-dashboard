"""isolate snapshots across credential and monitoring revisions

Revision ID: 0012_snapshot_revisions
Revises: 0011_session_id_text
"""

from alembic import op
import sqlalchemy as sa

revision = "0012_snapshot_revisions"
down_revision = "0011_session_id_text"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("provider_configs") as batch_op:
        batch_op.add_column(sa.Column("usage_revision", sa.Integer(), nullable=False, server_default="1"))
    with op.batch_alter_table("usage_snapshots") as batch_op:
        batch_op.add_column(sa.Column("config_revision", sa.Integer(), nullable=True))
        batch_op.create_index("ix_usage_snapshots_config_revision", ["config_revision"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("usage_snapshots") as batch_op:
        batch_op.drop_index("ix_usage_snapshots_config_revision")
        batch_op.drop_column("config_revision")
    with op.batch_alter_table("provider_configs") as batch_op:
        batch_op.drop_column("usage_revision")
