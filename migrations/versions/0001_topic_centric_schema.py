"""Create the current topic-centric schema.

Revision ID: 0001_topic_centric_schema
Revises:
"""

from alembic import op

from app.db.session import Base
import app.models  # noqa: F401

revision = "0001_topic_centric_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create all ORM tables for a new installation."""
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    """Drop all ORM tables for a full rollback."""
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
