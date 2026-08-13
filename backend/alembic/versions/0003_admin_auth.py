"""admin password authentication"""
from alembic import op
import sqlalchemy as sa

revision = "0003_admin_auth"
down_revision = "0002_provider_visibility_order"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_credentials",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("session_tokens", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("setup_code_hash", sa.Text(), nullable=True),
        sa.Column("setup_code_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reset_code_hash", sa.Text(), nullable=True),
        sa.Column("reset_code_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("admin_credentials")
