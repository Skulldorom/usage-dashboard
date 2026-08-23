"""allow long data source event ids"""

from alembic import op
import sqlalchemy as sa

revision = "0008_source_event_id_text"
down_revision = "0007_data_sources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("usage_observations") as batch_op:
        batch_op.alter_column(
            "source_event_id",
            existing_type=sa.String(length=64),
            type_=sa.Text(),
            existing_nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("usage_observations") as batch_op:
        batch_op.alter_column(
            "source_event_id",
            existing_type=sa.Text(),
            type_=sa.String(length=64),
            existing_nullable=True,
        )
