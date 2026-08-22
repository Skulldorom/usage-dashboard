"""data sources + usage observation provenance"""

from alembic import op
import sqlalchemy as sa

revision = "0007_data_sources"
down_revision = "0006_usage_observations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "data_source_configs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("base_url", sa.String(length=255), nullable=True),
        sa.Column("encrypted_token", sa.Text(), nullable=True),
        sa.Column("extra", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("poll_interval_minutes", sa.Integer(), nullable=False, server_default=sa.text("60")),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("latest_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("kind", "name", name="uq_data_source_kind_name"),
    )
    op.create_index("ix_data_source_configs_kind", "data_source_configs", ["kind"])

    # UsageObservation gains telemetry provenance columns; provider_config_id
    # becomes nullable so data-source observations (source="hermes") can live
    # alongside provider observations without a provider config.
    with op.batch_alter_table("usage_observations") as batch_op:
        batch_op.alter_column("provider_config_id", existing_type=sa.Integer(), nullable=True)
        batch_op.add_column(sa.Column("data_source_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("model", sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column("profile", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("session_id", sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column("cost_type", sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column("provider_mapping", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("source_event_id", sa.String(length=64), nullable=True))
        batch_op.create_foreign_key(
            "fk_usage_observations_data_source_id",
            "data_source_configs",
            ["data_source_id"],
            ["id"],
            ondelete="CASCADE",
        )
    op.create_index("ix_usage_observations_data_source_id", "usage_observations", ["data_source_id"])
    # DB-level idempotency for data-source telemetry: unique per (data_source,
    # source_event_id). Partial so provider observations (both columns NULL) are
    # unaffected and two data sources may reuse the same event ID.
    op.create_index(
        "ux_usage_observations_source_event",
        "usage_observations",
        ["data_source_id", "source_event_id"],
        unique=True,
        sqlite_where=sa.text("data_source_id IS NOT NULL AND source_event_id IS NOT NULL"),
        postgresql_where=sa.text("data_source_id IS NOT NULL AND source_event_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ux_usage_observations_source_event", table_name="usage_observations")
    op.drop_index("ix_usage_observations_data_source_id", table_name="usage_observations")
    with op.batch_alter_table("usage_observations") as batch_op:
        batch_op.drop_constraint("fk_usage_observations_data_source_id", type_="foreignkey")
        batch_op.drop_column("source_event_id")
        batch_op.drop_column("provider_mapping")
        batch_op.drop_column("cost_type")
        batch_op.drop_column("session_id")
        batch_op.drop_column("profile")
        batch_op.drop_column("model")
        batch_op.drop_column("data_source_id")
        batch_op.alter_column("provider_config_id", existing_type=sa.Integer(), nullable=False)
    op.drop_index("ix_data_source_configs_kind", table_name="data_source_configs")
    op.drop_table("data_source_configs")
