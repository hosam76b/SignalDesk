"""Make monitored sources global and deduplicate existing source targets.

Revision ID: 0006_global_monitored_sources
Revises: 0005_media_processing
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_global_monitored_sources"
down_revision = "0005_media_processing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    duplicate_targets = bind.execute(sa.text(
        "SELECT url_or_handle, MIN(id) AS canonical_id "
        "FROM monitored_sources GROUP BY url_or_handle HAVING COUNT(*) > 1"
    )).mappings()
    for duplicate in duplicate_targets:
        duplicate_ids = bind.execute(sa.text(
            "SELECT id FROM monitored_sources "
            "WHERE url_or_handle = :target AND id != :canonical_id"
        ), duplicate).scalars().all()
        if duplicate_ids:
            bind.execute(sa.text(
                "UPDATE posts SET source_id = :canonical_id WHERE source_id IN :duplicate_ids"
            ).bindparams(sa.bindparam("duplicate_ids", expanding=True)), {
                "canonical_id": duplicate["canonical_id"], "duplicate_ids": duplicate_ids,
            })
            bind.execute(sa.text(
                "DELETE FROM monitored_sources WHERE id IN :duplicate_ids"
            ).bindparams(sa.bindparam("duplicate_ids", expanding=True)), {"duplicate_ids": duplicate_ids})

    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("monitored_sources")}
    with op.batch_alter_table("monitored_sources") as batch_op:
        if "ix_monitored_sources_topic_id" in indexes:
            batch_op.drop_index("ix_monitored_sources_topic_id")
        batch_op.drop_column("topic_id")
        batch_op.create_unique_constraint("uq_monitored_sources_url_or_handle", ["url_or_handle"])


def downgrade() -> None:
    with op.batch_alter_table("monitored_sources") as batch_op:
        batch_op.drop_constraint("uq_monitored_sources_url_or_handle", type_="unique")
        batch_op.add_column(sa.Column("topic_id", sa.Integer(), nullable=True))