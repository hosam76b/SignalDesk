"""Async transactional email delivery (password reset, security notices)."""

import logging

from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType

from config import settings

logger = logging.getLogger(__name__)


def _mail_config() -> ConnectionConfig:
    return ConnectionConfig(
        MAIL_USERNAME=settings.mail_username,
        MAIL_PASSWORD=settings.mail_password,
        MAIL_FROM=settings.mail_from,
        MAIL_FROM_NAME=settings.mail_from_name,
        MAIL_PORT=settings.mail_port,
        MAIL_SERVER=settings.mail_server,
        MAIL_STARTTLS=settings.mail_starttls,
        MAIL_SSL_TLS=settings.mail_ssl_tls,
        USE_CREDENTIALS=bool(settings.mail_username),
        VALIDATE_CERTS=True,
    )


def _reset_password_html(full_name: str, reset_link: str, expire_minutes: int) -> str:
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;color:#17212b">
      <h2 style="color:#39c7ce">Signaldesk</h2>
      <p>Hi {full_name},</p>
      <p>We received a request to reset your Signaldesk password. This link expires in
      {expire_minutes} minutes and can only be used once.</p>
      <p style="margin:24px 0">
        <a href="{reset_link}" style="background:#f17869;color:#fff;padding:12px 20px;
        border-radius:6px;text-decoration:none;font-weight:bold">Reset your password</a>
      </p>
      <p>If you did not request this, you can safely ignore this email.</p>
    </div>
    """


async def send_password_reset_email(to_email: str, full_name: str, reset_token: str) -> None:
    """Send the password reset email asynchronously. Never raises to the caller."""
    reset_link = f"{settings.frontend_url}/?reset_token={reset_token}"
    if not settings.mail_enabled:
        logger.info("MAIL_ENABLED is false; skipping SMTP delivery. Reset link for %s: %s", to_email, reset_link)
        return
    try:
        message = MessageSchema(
            subject="Reset your Signaldesk password",
            recipients=[to_email],
            body=_reset_password_html(full_name, reset_link, settings.password_reset_expire_minutes),
            subtype=MessageType.html,
        )
        await FastMail(_mail_config()).send_message(message)
    except Exception:
        logger.exception("Failed to send password reset email to %s", to_email)
