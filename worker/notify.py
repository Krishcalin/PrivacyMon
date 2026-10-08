"""Notification delivery for material changes (SRS FR-7.4 / monitoring).

Two channels, both best-effort (a delivery failure never breaks a scan):
  - Webhooks: POST a JSON event to each active ``webhooks`` row subscribed to the event
    type, signed with an HMAC-SHA256 header when the webhook has a secret.
  - Email (optional): a plain SMTP send, only when SMTP env vars are configured.

Everything here uses the Python standard library so the worker needs no extra deps.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import smtplib
import urllib.request
from email.message import EmailMessage
from typing import Any

from platform_db import crypto
from platform_db.models.platform_tables import Webhook


def _sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def deliver_webhooks(session, event_type: str, payload: dict[str, Any], *,
                     timeout: float = 5.0) -> int:
    """POST ``payload`` to every active webhook subscribed to ``event_type``. Returns the
    number of successful deliveries. Never raises."""
    delivered = 0
    try:
        hooks = session.query(Webhook).filter(Webhook.active.is_(True)).all()
    except Exception:  # noqa: BLE001
        return 0
    body = json.dumps({"event": event_type, "data": payload}).encode("utf-8")
    for h in hooks:
        types = list(h.event_types or [])
        if types and event_type not in types:
            continue
        headers = {"Content-Type": "application/json",
                   "X-PrivacyMon-Event": event_type}
        if h.secret_ref:
            try:
                secret = crypto.resolve_secret(h.secret_ref)
                headers["X-PrivacyMon-Signature"] = _sign(secret, body)
            except Exception:  # noqa: BLE001 — unsigned delivery is better than none
                pass
        try:
            req = urllib.request.Request(h.url, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
                if 200 <= resp.status < 300:
                    delivered += 1
        except Exception:  # noqa: BLE001 — best-effort
            continue
    return delivered


def smtp_configured() -> bool:
    return bool(os.getenv("PRIVACYMON_SMTP_HOST"))


def send_email(subject: str, body: str, recipients: list[str], *,
               timeout: float = 10.0) -> bool:
    """Send a plain-text email if SMTP is configured and there are recipients. Returns
    True on success. Never raises."""
    if not smtp_configured() or not recipients:
        return False
    host = os.getenv("PRIVACYMON_SMTP_HOST")
    port = int(os.getenv("PRIVACYMON_SMTP_PORT", "587"))
    user = os.getenv("PRIVACYMON_SMTP_USER")
    password = os.getenv("PRIVACYMON_SMTP_PASSWORD")
    sender = os.getenv("PRIVACYMON_SMTP_FROM", "privacymon@localhost")
    use_tls = os.getenv("PRIVACYMON_SMTP_TLS", "1") != "0"
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.set_content(body)
    try:
        with smtplib.SMTP(host, port, timeout=timeout) as s:
            if use_tls:
                s.starttls()
            if user and password:
                s.login(user, password)
            s.send_message(msg)
        return True
    except Exception:  # noqa: BLE001 — best-effort
        return False
