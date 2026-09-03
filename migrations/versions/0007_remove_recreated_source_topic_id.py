"""Remove the legacy source topic column recreated by startup compatibility code.

Revision ID: 0007_remove_recreated_source_topic_id
Revises: 0006_global_monitored_sources
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_remove_recreated_source_topic_id"
down_revision = "0006_global_monitored_sources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("monitored_sources")}
    if "topic_id" in columns:
        with op.batch_alter_table("monitored_sources") as batch_op:
            batch_op.drop_column("topic_id")


def downgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("monitored_sources")}
    if "topic_id" not in columns:
        with op.batch_alter_table("monitored_sources") as batch_op:
            batch_op.add_column(sa.Column("topic_id", sa.Integer(), nullable=True))