"""allow long data source session ids

Revision ID: 0011_session_id_text
Revises: 0010_provider_error_details
"""

from alembic import op
import sqlalchemy as sa

revision = "0011_session_id_text"
down_revision = "0010_provider_error_details"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("usage_observations") as batch_op:
        batch_op.alter_column(
            "session_id",
            existing_type=sa.String(length=128),
            type_=sa.Text(),
            existing_nullable=True,
        )


def downgrade() -> None:
    # PostgreSQL rejects this downgrade if existing values exceed 128 characters.
    with op.batch_alter_table("usage_observations") as batch_op:
        batch_op.alter_column(
            "session_id",
            existing_type=sa.Text(),
            type_=sa.String(length=128),
            existing_nullable=True,
        )
