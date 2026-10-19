"""persist data-source retry eligibility

Revision ID: 0012_data_source_retry_backoff
Revises: 0011_session_id_text
"""

from alembic import op
import sqlalchemy as sa

revision = "0012_data_source_retry_backoff"
down_revision = "0011_session_id_text"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("data_source_configs", sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("data_source_configs", "next_attempt_at")
