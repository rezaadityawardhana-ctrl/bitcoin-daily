"""Send the daily email over SMTP (works with Gmail, iCloud, Outlook, Fastmail...).

Settings come from .env - see .env.example. For Gmail, use an App Password
(Google Account -> Security -> 2-Step Verification -> App passwords), never your main password.
"""
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path

from common import SSL_CONTEXT


def send(subject: str, html_body: str, text_body: str, attachment: Path | None = None) -> None:
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "465"))
    user = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASSWORD"]
    to = [a.strip() for a in os.environ.get("EMAIL_TO", user).split(",") if a.strip()]

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = os.environ.get("EMAIL_FROM", user)
    msg["To"] = ", ".join(to)
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")
    if attachment and attachment.exists():
        msg.add_attachment(attachment.read_bytes(), maintype="text", subtype="html",
                           filename=attachment.name)

    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=SSL_CONTEXT, timeout=30) as s:
            s.login(user, password)
            s.send_message(msg)
    else:  # 587 / STARTTLS
        with smtplib.SMTP(host, port, timeout=30) as s:
            s.starttls(context=SSL_CONTEXT)
            s.login(user, password)
            s.send_message(msg)
