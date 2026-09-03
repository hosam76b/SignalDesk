"""Create webhook subscription and delivery tables for external integrations.

Revision ID: 0008_webhook_settings
Revises: 0007_remove_recreated_source_topic_id
"""

from alembic import op
import sqlalchemy as sa


revision = "0008_webhook_settings"
down_revision = "0007_remove_recreated_source_topic_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing_tables = set(sa.inspect(bind).get_table_names())

    if "webhooks" not in existing_tables:
        op.create_table(
            "webhooks",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("url", sa.String(length=1000), nullable=False),
            sa.Column("secret", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("events", sa.JSON(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_webhooks_id", "webhooks", ["id"])

    if "webhook_deliveries" not in existing_tables:
        op.create_table(
            "webhook_deliveries",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "webhook_id",
                sa.Integer(),
                sa.ForeignKey("webhooks.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("event", sa.String(length=100), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=True),
            sa.Column("status_code", sa.Integer(), nullable=True),
            sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_webhook_deliveries_id", "webhook_deliveries", ["id"])
        op.create_index("ix_webhook_deliveries_webhook_id", "webhook_deliveries", ["webhook_id"])
        op.create_index("ix_webhook_deliveries_event", "webhook_deliveries", ["event"])
        op.create_index("ix_webhook_deliveries_created_at", "webhook_deliveries", ["created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    existing_tables = set(sa.inspect(bind).get_table_names())
    if "webhook_deliveries" in existing_tables:
        op.drop_table("webhook_deliveries")
    if "webhooks" in existing_tables:
        op.drop_table("webhooks")
