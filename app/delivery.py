"""Digest delivery — the seam where real providers plug in.

The product rule: siblings don't open the app, they read the digest. Sending
is where a real product gets its costs (transactional email, later SMS/WhatsApp
for markets where email dies at the 45–65 age band). So delivery is a tiny
interface, not a dependency.

Demo behavior: the "email" channel is simulated — each send is composed and
logged to the record's `deliveries` outbox. Nothing leaves the machine.
Going live = implement `deliver()` with SMTP or a provider (Postmark/SES);
the digest, opens, and gate metrics don't change shape.
"""
from __future__ import annotations

from datetime import datetime


def deliver(recipient: dict, subject: str, now: datetime) -> dict:
    """Deliver `subject` to `recipient`; return one delivery-log entry."""
    # Demo: simulated send, logged as sent.
    return {
        "member_id": recipient["id"],
        "channel": "email",
        "status": "sent",
        "at": now.isoformat(timespec="seconds"),
    }
