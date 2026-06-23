"""Generic SMTP notifier (works with Gmail, Fastmail, self-hosted, etc.).

For Gmail, use a Google *app password* as SMTP_PASS (not your account
password). Port 465 = implicit TLS (SMTP_SSL); 587 = STARTTLS.
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from .base import NotifierError


class SmtpNotifier:
    def __init__(self, host: str, port: int, user: str, password: str, recipient: str):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.recipient = recipient

    def send(self, subject: str, body: str) -> None:
        # WATCHER_RECIPIENT may list several addresses, comma-separated.
        recipients = [r.strip() for r in (self.recipient or "").split(",") if r.strip()]
        if not (self.user and self.password and recipients):
            raise NotifierError(
                "SMTP notifier requires SMTP_USER, SMTP_PASS, and WATCHER_RECIPIENT"
            )
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self.user
        # With multiple recipients, hide them from each other: the visible To is a
        # placeholder and actual delivery is via the explicit envelope (to_addrs),
        # so no recipient can see who else received the mail (BCC semantics).
        msg["To"] = recipients[0] if len(recipients) == 1 else "undisclosed-recipients:;"
        msg.set_content(body)

        if self.port == 465:
            with smtplib.SMTP_SSL(self.host, self.port, timeout=30) as smtp:
                smtp.login(self.user, self.password)
                smtp.send_message(msg, from_addr=self.user, to_addrs=recipients)
        else:
            with smtplib.SMTP(self.host, self.port, timeout=30) as smtp:
                smtp.starttls()
                smtp.login(self.user, self.password)
                smtp.send_message(msg, from_addr=self.user, to_addrs=recipients)
