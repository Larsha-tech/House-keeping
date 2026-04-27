"""Email transport via SMTP (aiosmtplib).

When SMTP_ENABLED is false (dev default) the service logs the message
instead of sending - useful for local testing.
"""
import logging
from email.message import EmailMessage
from typing import Iterable, Optional

import aiosmtplib

from ..core.config import settings

logger = logging.getLogger("hobb.email")


async def send_email(
    *,
    to: Iterable[str],
    subject: str,
    body: str,
    html: Optional[str] = None,
) -> bool:
    recipients = [r for r in to if r]
    if not recipients:
        return False

    if not settings.SMTP_ENABLED:
        logger.info("SMTP disabled — would send to=%s subject=%s", recipients, subject)
        return True

    msg = EmailMessage()
    msg["From"] = settings.SMTP_FROM
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.set_content(body)
    if html:
        msg.add_alternative(html, subtype="html")

    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
            start_tls=settings.SMTP_USE_TLS,
            timeout=15,
        )
        logger.info("email sent to=%s subject=%s", recipients, subject)
        return True
    except Exception as exc:
        logger.exception("email send failed: %s", exc)
        return False
