"""Razorpay webhook verification (PRD 9.3, attack A10).

Three rules, none of them optional:

  1. Verify BEFORE parsing. The signature covers raw bytes; any framework that
     deserialises first has already lost the ability to verify.
  2. Compare in constant time.
  3. Deduplicate on x-razorpay-event-id. Delivery is at-least-once, so
     duplicates are normal operation rather than an anomaly.

Out-of-order delivery is assumed. Transitions are guarded by current state, not
by arrival order (see settlement.py).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import threading
from dataclasses import dataclass, field

SIGNATURE_HEADER = "X-Razorpay-Signature"
EVENT_ID_HEADER = "x-razorpay-event-id"


class WebhookVerificationError(Exception):
    """Signature absent or wrong. The event is discarded, never processed."""


def verify_signature(raw_body: bytes, signature: str | None, secret: str) -> bool:
    """HMAC-SHA256 of the raw body, keyed with the webhook secret."""
    if not signature:
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def sign(raw_body: bytes, secret: str) -> str:
    """Test helper: produce what Razorpay would send."""
    return hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class WebhookEvent:
    event: str
    payment_id: str | None
    order_id: str | None
    amount_minor: int | None
    status: str | None
    error_code: str | None
    error_description: str | None
    refund_amount: int | None
    event_id: str | None
    raw: dict

    @classmethod
    def parse(cls, body: dict, event_id: str | None = None) -> "WebhookEvent":
        payload = body.get("payload", {})
        pay = payload.get("payment", {}).get("entity", {}) or {}
        ref = payload.get("refund", {}).get("entity", {}) or {}
        return cls(
            event=body.get("event", ""),
            payment_id=pay.get("id") or ref.get("payment_id"),
            order_id=pay.get("order_id"),
            amount_minor=pay.get("amount"),
            status=pay.get("status"),
            error_code=pay.get("error_code"),
            error_description=pay.get("error_description"),
            refund_amount=ref.get("amount"),
            event_id=event_id,
            raw=body,
        )


@dataclass
class EventDeduplicator:
    seen: set[str] = field(default_factory=set)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def is_new(self, event_id: str | None) -> bool:
        if not event_id:
            return True                       # nothing to dedupe on; process once
        with self._lock:
            if event_id in self.seen:
                return False
            self.seen.add(event_id)
            return True


def receive(raw_body: bytes, headers: dict[str, str], secret: str,
            dedup: EventDeduplicator | None = None) -> WebhookEvent | None:
    """Verify, dedupe, then parse. Returns None for a duplicate."""
    lower = {k.lower(): v for k, v in headers.items()}
    if not verify_signature(raw_body, lower.get(SIGNATURE_HEADER.lower()), secret):
        raise WebhookVerificationError("signature did not verify")
    event_id = lower.get(EVENT_ID_HEADER)
    if dedup is not None and not dedup.is_new(event_id):
        return None
    return WebhookEvent.parse(json.loads(raw_body), event_id)
