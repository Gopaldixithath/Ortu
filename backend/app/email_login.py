from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage


class EmailError(RuntimeError):
    pass


def _config() -> tuple[str, int, str, str, str]:
    host = str(os.getenv("SMTP_HOST") or "").strip()
    port = int(str(os.getenv("SMTP_PORT") or "587").strip() or 587)
    username = str(os.getenv("SMTP_USERNAME") or "").strip()
    password = str(os.getenv("SMTP_PASSWORD") or "").strip()
    sender = str(os.getenv("SMTP_FROM") or "").strip() or username
    return host, port, username, password, sender


def is_configured() -> bool:
    host, _port, _username, _password, sender = _config()
    return bool(host and sender)


def send(to: str, subject: str, body: str, html: str | None = None) -> None:
    host, port, username, password, sender = _config()
    if not (host and sender):
        raise EmailError("Email sending is not configured yet.")
    message = EmailMessage()
    message["From"] = sender if "<" in sender else f"ORTU Fitness <{sender}>"
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    if html:
        message.add_alternative(html, subtype="html")
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=20) as server:
                if username and password:
                    server.login(username, password)
                server.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=20) as server:
                try:
                    server.ehlo()
                except smtplib.SMTPException:
                    pass
                if server.has_extn("starttls"):
                    server.starttls()
                    server.ehlo()
                if username and password:
                    server.login(username, password)
                server.send_message(message)
    except EmailError:
        raise
    except Exception as exc:
        raise EmailError(f"Could not send the sign-in email: {exc}") from exc
