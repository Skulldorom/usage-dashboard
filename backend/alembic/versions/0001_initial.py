"""initial schema"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("provider_configs", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("provider", sa.String(length=32), nullable=False), sa.Column("label", sa.String(length=120), nullable=False), sa.Column("encrypted_api_key", sa.Text(), nullable=False), sa.Column("base_url", sa.String(length=255), nullable=True), sa.Column("extra", sa.JSON(), nullable=False, server_default=sa.text("'{}'")), sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.UniqueConstraint("provider", "label", name="uq_provider_label"))
    op.create_index("ix_provider_configs_provider", "provider_configs", ["provider"])
    op.create_table("usage_snapshots", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("provider_config_id", sa.Integer(), sa.ForeignKey("provider_configs.id", ondelete="CASCADE"), nullable=False), sa.Column("provider", sa.String(length=32), nullable=False), sa.Column("status", sa.String(length=32), nullable=False), sa.Column("summary", sa.String(length=255), nullable=False), sa.Column("metrics", sa.JSON(), nullable=False, server_default=sa.text("'[]'")), sa.Column("raw", sa.JSON(), nullable=False, server_default=sa.text("'{}'")), sa.Column("error", sa.Text(), nullable=True), sa.Column("checked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_usage_snapshots_provider", "usage_snapshots", ["provider"])

def downgrade() -> None:
    op.drop_table("usage_snapshots")
    op.drop_table("provider_configs")
