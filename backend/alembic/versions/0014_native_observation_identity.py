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
_COLUMNS = "provider_config_id, coalesce(config_revision, 1), source, metric, observed_at, coalesce(model, ''), coalesce(provider_mapping, ''), coalesce(profile, '')"
_WHERE = "source IN ('native', 'native_grouped')"


def upgrade() -> None:
    # Native rows are daily provider facts.  Earlier releases could persist the
    # same fact repeatedly; retain the latest persisted row as the authoritative
    # correction when upstream provenance cannot distinguish duplicates.
    op.execute(
        """
        DELETE FROM usage_observations
        WHERE id IN (
            SELECT id FROM (
                SELECT id, row_number() OVER (
                    PARTITION BY provider_config_id, coalesce(config_revision, 1), source,
                        metric, observed_at, coalesce(model, ''),
                        coalesce(provider_mapping, ''), coalesce(profile, '')
                    ORDER BY id DESC
                ) AS duplicate_rank
                FROM usage_observations
                WHERE source IN ('native', 'native_grouped')
            ) duplicates
            WHERE duplicate_rank > 1
        )
        """
    )
    op.execute(f"CREATE UNIQUE INDEX {_INDEX} ON usage_observations ({_COLUMNS}) WHERE {_WHERE}")


def downgrade() -> None:
    op.drop_index(_INDEX, table_name="usage_observations")
