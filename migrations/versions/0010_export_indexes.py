"""Add the composite indexes backing the Export Data tab.

Revision ID: 0010_export_indexes
Revises: 0009_ai_status_and_indexes
"""

from alembic import op
import sqlalchemy as sa


revision = "0010_export_indexes"
down_revision = "0009_ai_status_and_indexes"
branch_labels = None
depends_on = None


#: (name, columns) -- kept in step with ``Post.__table_args__`` so autogenerate
#: does not report drift, and mirrored by the self-heal in ``app/db/init_db.py``.
#:
#: The export is the only query in the app that filters ``posts`` on an
#: arbitrary ``published_at`` window, and ``ix_posts_ai_queue`` cannot help it:
#: that index is keyed on ``id`` and partial to ``ai_status IN ('pending',
#: 'failed')``, so it serves neither a date range nor the ``done``/``skipped``/
#: ``processing`` statuses the export filter offers.
INDEXES = (
    # Default "last N days" export, ordered `published_at DESC, id DESC`.
    # Leading `published_at` turns the window into an index range scan that
    # already yields rows in the requested order, so no temp B-tree sort.
    ("ix_posts_export_date", ("published_at", "id")),
    # Status-filtered export: `ai_status` first so the seek lands on the
    # requested subset, then walks the window.
    ("ix_posts_export_ai_date", ("ai_status", "published_at", "id")),
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
    existing_columns = {c["name"] for c in inspector.get_columns("posts")}
    existing_indexes = {i["name"] for i in inspector.get_indexes("posts")}

    for name, columns in INDEXES:
        if name in existing_indexes:
            continue
        missing = [c for c in columns if c not in existing_columns]
        if missing:
            # An index is an optimization, never a correctness requirement, so
            # a legacy posts table without these columns simply goes without.
            continue
        op.create_index(name, "posts", list(columns))


def downgrade() -> None:
    inspector = _posts_inspector(op.get_bind())
    if inspector is None:
        return
    bind = op.get_bind()
    existing_indexes = {i["name"] for i in inspector.get_indexes(bind, "posts")}

    for name, _columns in reversed(INDEXES):
        if name in existing_indexes:
            op.drop_index(name, table_name="posts")
            existing_indexes.discard(name)
