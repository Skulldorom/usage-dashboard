"""guard native observation upserts across grouped dimensions

Revision ID: 0014_native_observation_identity
Revises: 0013_observation_revisions
"""

from alembic import op

revision = "0014_native_observation_identity"
down_revision = "0013_observation_revisions"
branch_labels = None
depends_on = None

_INDEX = "ux_usage_observations_native_identity"
_COLUMNS = "provider_config_id, config_revision, source, metric, observed_at, coalesce(model, ''), coalesce(provider_mapping, ''), coalesce(profile, '')"
_WHERE = "source IN ('native', 'native_grouped')"


def upgrade() -> None:
    op.execute(f"CREATE UNIQUE INDEX {_INDEX} ON usage_observations ({_COLUMNS}) WHERE {_WHERE}")


def downgrade() -> None:
    op.drop_index(_INDEX, table_name="usage_observations")
