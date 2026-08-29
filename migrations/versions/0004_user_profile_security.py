"""Add profile, security, and 2FA fields to users.

Revision ID: 0004_user_profile_security
Revises: 0003_approval_workflow
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_user_profile_security"
down_revision = "0003_approval_workflow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("avatar_url", sa.String(length=500), nullable=True))
    op.add_column("users", sa.Column("job_title", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(), nullable=True))
    op.add_column("users", sa.Column("password_changed_at", sa.DateTime(), nullable=False, server_default=sa.func.now()))
    op.add_column("users", sa.Column("totp_secret", sa.String(length=64), nullable=True))
    op.add_column("users", sa.Column("totp_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("users", "totp_enabled")
    op.drop_column("users", "totp_secret")
    op.drop_column("users", "password_changed_at")
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "job_title")
    op.drop_column("users", "avatar_url")
