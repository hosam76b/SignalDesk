"""Add post priority flags and audit logs.

Revision ID: 0002_audit_priority
Revises: 0001_topic_centric_schema
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_audit_priority"
down_revision = "0001_topic_centric_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("posts", sa.Column("is_important", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("posts", sa.Column("is_dangerous", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("posts", sa.Column("content_fingerprint", sa.String(length=32), nullable=True))
    op.add_column("posts", sa.Column("sentiment", sa.String(length=20), nullable=True))
    op.add_column("posts", sa.Column("sentiment_score", sa.Integer(), nullable=True))
    op.add_column("posts", sa.Column("entities", sa.JSON(), nullable=True))
    op.create_index("ix_posts_content_fingerprint", "posts", ["content_fingerprint"])
    op.create_index("ix_posts_is_important", "posts", ["is_important"])
    op.create_index("ix_posts_is_dangerous", "posts", ["is_dangerous"])
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("topic_id", sa.Integer(), sa.ForeignKey("topics.id", ondelete="SET NULL"), nullable=True),
        sa.Column("post_id", sa.Integer(), sa.ForeignKey("posts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    for column in ("user_id", "topic_id", "post_id", "action", "created_at"):
        op.create_index(f"ix_audit_logs_{column}", "audit_logs", [column])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_index("ix_posts_content_fingerprint", table_name="posts")
    op.drop_index("ix_posts_is_dangerous", table_name="posts")
    op.drop_index("ix_posts_is_important", table_name="posts")
    op.drop_column("posts", "is_dangerous")
    op.drop_column("posts", "is_important")
    op.drop_column("posts", "content_fingerprint")
    op.drop_column("posts", "sentiment")
    op.drop_column("posts", "sentiment_score")
    op.drop_column("posts", "entities")