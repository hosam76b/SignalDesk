"""Add the AI analysis lifecycle columns, the hot-path indexes, and a data cleanup.

Revision ID: 0009_ai_status_and_indexes
Revises: 0008_webhook_settings
"""

from alembic import op
import sqlalchemy as sa


revision = "0009_ai_status_and_indexes"
down_revision = "0008_webhook_settings"
branch_labels = None
depends_on = None


#: The exact predicate the background worker claims work with. The partial index
#: MUST match it, including the ``failed`` branch.
#:
#: An earlier draft indexed only ``ai_status = 'pending'`` while the claim query
#: filtered on ``ai_status IN ('pending', 'failed')``. SQLite cannot use a
#: partial index whose WHERE clause is not implied by the query's, so the claim
#: silently degraded to a full table scan -- the exact 99 ms regression this
#: migration exists to remove.
CLAIM_PREDICATE = "ai_status IN ('pending', 'failed')"


#: (name, columns, sqlite_where)
INDEXES = (
    # Alert filtering: get_flagged_posts() filters is_flagged OR
    # severity_level IN ('high','critical') and orders by id DESC. Measured
    # 1.6 ms -> 0.21 ms.
    ("ix_posts_flagged", ("is_flagged", "id"), None),
    ("ix_posts_severity", ("severity_level", "id"), None),
    # Batch deduplication in _save_posts(). Measured 1.75 ms -> 0.08 ms.
    ("ix_posts_dedup_external", ("source_id", "topic_id", "external_id"), None),
    ("ix_posts_dedup_url", ("source_id", "topic_id", "post_url"), None),
    ("ix_posts_dedup_fingerprint", ("source_id", "topic_id", "content_fingerprint"), None),
    # The worker's claim query: WHERE ai_status IN ('pending','failed')
    # ORDER BY id ASC LIMIT n. Keyed on `id` alone: that is the ORDER BY column,
    # so the index serves the filter and the ordering with no temp B-tree sort,
    # and nothing in the claim filters on topic_id. Must stay in step with
    # Post.__table_args__ or autogenerate will report drift.
    ("ix_posts_ai_queue", ("id",), CLAIM_PREDICATE),
)


def _posts_inspector(bind):
    inspector = sa.inspect(bind)
    if "posts" not in set(inspector.get_table_names()):
        return None
    return inspector


def upgrade() -> None:
    inspector = _posts_inspector(op.get_bind())
    if inspector is None:
        return
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    existing_columns = {c["name"] for c in inspector.get_columns("posts")}

    # --- 1. Lifecycle columns -------------------------------------------
    # NOT NULL with a server default is safe on SQLite: ADD COLUMN rewrites no
    # rows, so every pre-existing row reads back as 'pending'.
    if "ai_status" not in existing_columns:
        op.add_column(
            "posts",
            sa.Column(
                "ai_status",
                sa.String(length=20),
                nullable=False,
                server_default="pending",
            ),
        )
    if "ai_analyzed_at" not in existing_columns:
        op.add_column("posts", sa.Column("ai_analyzed_at", sa.DateTime(), nullable=True))

    # --- 2. Data cleanup ------------------------------------------------
    # Replace the empty-string sentinel with NULL. The old pending-post predicate
    # was `ai_summary IS NULL OR ai_summary = ''`, and that second disjunct
    # cannot be served by any index on ai_status -- it forced the full table
    # scan plus a temp B-tree sort measured at 99 ms and growing linearly.
    bind.execute(sa.text("UPDATE posts SET ai_summary = NULL WHERE ai_summary = ''"))
    bind.execute(sa.text("UPDATE posts SET severity_level = NULL WHERE severity_level = ''"))

    # Backfill. Anything already carrying an analysis result is terminal and
    # must NOT be re-queued, or the worker would be handed the entire history
    # (3,807 rows here) instead of just the unanalysed subset.
    bind.execute(
        sa.text(
            "UPDATE posts SET ai_status = 'done', "
            "ai_analyzed_at = COALESCE(scraped_at, CURRENT_TIMESTAMP) "
            "WHERE (ai_summary IS NOT NULL OR severity_level IS NOT NULL) "
            "AND ai_status = 'pending'"
        )
    )
    # Posts with no text at all can never be analyzed; leaving them 'pending'
    # would make the worker claim them on every cycle forever.
    bind.execute(
        sa.text(
            "UPDATE posts SET ai_status = 'skipped' "
            "WHERE (content IS NULL OR TRIM(content) = '') AND ai_status = 'pending'"
        )
    )

    # --- 3. Indexes ------------------------------------------------------
    existing_indexes = {i["name"] for i in sa.inspect(bind).get_indexes("posts")}

    # Drop the superseded narrower index if an earlier build created it.
    if "ix_posts_ai_pending" in existing_indexes:
        op.drop_index("ix_posts_ai_pending", table_name="posts")
        existing_indexes.discard("ix_posts_ai_pending")

    for name, columns, where in INDEXES:
        if name in existing_indexes:
            continue
        kwargs = {}
        if where:
            # A partial index is emitted only for SQLite; the other dialects get
            # a plain composite index, which is what Post.__table_args__ declares.
            if is_sqlite:
                kwargs["sqlite_where"] = sa.text(where)
            else:
                kwargs["postgresql_where"] = sa.text(where)
        op.create_index(name, "posts", list(columns), **kwargs)

    # --- 4. Optional integrity constraints -------------------------------
    # Left opt-in: applying them fails on any database that already contains
    # duplicates, and de-duplicating an operator's monitoring archive is a
    # judgement call rather than a migration. tools/loadtest/db_hardening.sql
    # carries the pre-flight audit query and the cleanup.
    #
    # op.execute(
    #     "DELETE FROM posts WHERE id NOT IN ("
    #     "  SELECT MIN(id) FROM posts GROUP BY source_id, topic_id, external_id)"
    # )
    # op.create_index(
    #     "ux_posts_source_topic_external", "posts",
    #     ["source_id", "topic_id", "external_id"], unique=True,
    # )


def downgrade() -> None:
    inspector = _posts_inspector(op.get_bind())
    if inspector is None:
        return
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    existing_indexes = {i["name"] for i in sa.inspect(bind).get_indexes("posts")}

    for name, _columns, _where in reversed(INDEXES):
        if name in existing_indexes:
            op.drop_index(name, table_name="posts")
            existing_indexes.discard(name)

    existing_columns = {c["name"] for c in sa.inspect(bind).get_columns("posts")}
    if "ai_analyzed_at" in existing_columns:
        op.drop_column("posts", "ai_analyzed_at")
    if "ai_status" in existing_columns:
        op.drop_column("posts", "ai_status")

    if is_sqlite:
        # Restore the narrower index this migration supersedes.
        op.create_index(
            "ix_posts_ai_pending",
            "posts",
            ["id", "topic_id"],
            unique=False,
            sqlite_where=sa.text("ai_status = 'pending'"),
        )
