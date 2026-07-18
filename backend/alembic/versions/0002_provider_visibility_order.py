"""provider visibility and order"""
from alembic import op
import sqlalchemy as sa

revision = "0002_provider_visibility_order"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("provider_configs", sa.Column("is_visible", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("provider_configs", sa.Column("display_order", sa.Integer(), nullable=False, server_default=sa.text("0")))
    provider_configs = sa.table("provider_configs", sa.column("id", sa.Integer()), sa.column("display_order", sa.Integer()))
    connection = op.get_bind()
    rows = connection.execute(sa.select(provider_configs.c.id).order_by(provider_configs.c.id)).fetchall()
    for index, row in enumerate(rows):
        connection.execute(provider_configs.update().where(provider_configs.c.id == row.id).values(display_order=index))


def downgrade() -> None:
    op.drop_column("provider_configs", "display_order")
    op.drop_column("provider_configs", "is_visible")
