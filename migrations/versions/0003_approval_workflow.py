"""Add approval workflow status to sources/keywords and proposal tracking.

Revision ID: 0003_approval_workflow
Revises: 0002_audit_priority
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_approval_workflow"
down_revision = "0002_audit_priority"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("monitored_sources", sa.Column("approval_status", sa.String(length=20), nullable=False, server_default="approved"))
    op.add_column("monitored_sources", sa.Column("proposed_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True))
    op.add_column("monitored_sources", sa.Column("reviewed_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True))
    op.add_column("monitored_sources", sa.Column("reviewed_at", sa.DateTime(), nullable=True))
    op.create_index("ix_monitored_sources_approval_status", "monitored_sources", ["approval_status"])

    op.add_column("keywords", sa.Column("approval_status", sa.String(length=20), nullable=False, server_default="approved"))
    op.add_column("keywords", sa.Column("proposed_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True))
    op.add_column("keywords", sa.Column("reviewed_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True))
    op.add_column("keywords", sa.Column("reviewed_at", sa.DateTime(), nullable=True))
    op.create_index("ix_keywords_approval_status", "keywords", ["approval_status"])


def downgrade() -> None:
    op.drop_index("ix_keywords_approval_status", table_name="keywords")
    op.drop_column("keywords", "reviewed_at")
    op.drop_column("keywords", "reviewed_by_id")
    op.drop_column("keywords", "proposed_by_id")
    op.drop_column("keywords", "approval_status")

    op.drop_index("ix_monitored_sources_approval_status", table_name="monitored_sources")
    op.drop_column("monitored_sources", "reviewed_at")
    op.drop_column("monitored_sources", "reviewed_by_id")
    op.drop_column("monitored_sources", "proposed_by_id")
    op.drop_column("monitored_sources", "approval_status")
