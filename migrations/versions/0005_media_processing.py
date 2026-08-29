"""Add multi-modal media extraction fields to posts.

Revision ID: 0005_media_processing
Revises: 0004_user_profile_security
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_media_processing"
down_revision = "0004_user_profile_security"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("posts", sa.Column("extracted_ocr_text", sa.Text(), nullable=True))
    op.add_column("posts", sa.Column("video_transcript", sa.Text(), nullable=True))
    op.add_column("posts", sa.Column("media_status", sa.String(length=20), nullable=False, server_default="pending"))
    op.create_index("ix_posts_media_status", "posts", ["media_status"])


def downgrade() -> None:
    op.drop_index("ix_posts_media_status", table_name="posts")
    op.drop_column("posts", "media_status")
    op.drop_column("posts", "video_transcript")
    op.drop_column("posts", "extracted_ocr_text")
