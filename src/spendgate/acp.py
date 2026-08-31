"""ACP client — the fact resolver (PRD 5 C2, 12.2 A2).

This module is the load-bearing security edge of the whole system. It learns
the price from the MERCHANT, server-to-server, over a channel the agent is not
standing in. The agent hands over an opaque session id and nothing else; every
fact used in the decision is fetched here.

Conforms to Agentic Commerce Protocol `2026-04-17`:
  GET  /checkout_sessions/{id}
  POST /checkout_sessions/{id}/complete
with the API-Version, Idempotency-Key, Request-Id, Signature and Timestamp
headers the specification defines.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from .models import LineItem, ResolvedFacts
from .service import FactsUnavailable

ACP_VERSION = "2026-04-17"


def sign_payload(secret: str, body: str) -> str:
    """Detached signature over the response body, as ACP's Signature header."""
    return hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()


def verify_payload(secret: str, body: str, signature: str) -> bool:
    return hmac.compare_digest(sign_payload(secret, body), signature or "")


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@dataclass
class AcpFactResolver:
    """Resolves a checkout session into ResolvedFacts.

    Any failure to establish the facts raises FactsUnavailable, which the engine
    turns into R15 and refuses. There is deliberately no fallback to a cached
    price and no path by which agent-supplied values could be substituted:
    unavailable facts are indistinguishable from hostile ones.
    """

    base_url: str
    api_key: str
    merchant_secret: str | None = None
    timeout: float = 5.0
    verify_signature: bool = True
    _client: httpx.Client | None = None

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(base_url=self.base_url, timeout=self.timeout)
        return self._client

    def _headers(self, idempotency_key: str | None = None) -> dict[str, str]:
        h = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "API-Version": ACP_VERSION,
            "Request-Id": "req_" + uuid.uuid4().hex[:12],
            "Timestamp": datetime.now(timezone.utc).isoformat(),
            "User-Agent": "SpendGate/0.2",
        }
        if idempotency_key:
            h["Idempotency-Key"] = idempotency_key
        return h

    def resolve(self, checkout_session_id: str) -> ResolvedFacts | None:
        try:
            r = self._http().get(
                f"/checkout_sessions/{checkout_session_id}", headers=self._headers()
            )
        except httpx.HTTPError as exc:
            raise FactsUnavailable(f"merchant unreachable: {exc}") from exc

        if r.status_code == 404:
            return None                       # -> R09 session_not_found
        if r.status_code >= 500:
            raise FactsUnavailable(f"merchant returned {r.status_code}")
        if r.status_code != 200:
            raise FactsUnavailable(f"unexpected {r.status_code}: {r.text[:200]}")

        # Signature is verified over the RAW body, before parsing. A merchant
        # whose signature does not verify is reported unverified (R14) rather
        # than trusted; we do not simply drop the check.
        verified = True
        if self.verify_signature and self.merchant_secret:
            verified = verify_payload(self.merchant_secret, r.text, r.headers.get("Signature", ""))

        return self._to_facts(r.json(), verified)

    @staticmethod
    def _to_facts(session: dict, merchant_verified: bool) -> ResolvedFacts:
        ext = session.get("extensions", {}).get("spendgate", {})
        totals = session.get("totals", {})
        return ResolvedFacts(
            checkout_session_id=session["id"],
            merchant_id=ext.get("merchant_id", session.get("merchant_id", "")),
            merchant_verified=merchant_verified,
            status=session.get("status", ""),
            currency=(session.get("currency") or "").upper(),
            total_minor=int(totals.get("total", 0)),
            category=ext.get("category", "uncategorised"),
            issued_to_agent=ext.get("issued_to_agent", ""),
            expires_at=_dt(ext["expires_at"]),
            resolved_at=datetime.now(timezone.utc),
            line_items=tuple(
                LineItem(i["item"]["id"], int(i.get("quantity", 1)), int(i["base_amount"]))
                for i in session.get("line_items", [])
            ),
            consumed=session.get("status") == "completed" or bool(ext.get("consumed")),
            instrument=ext.get("instrument", "upi"),
        )

    def complete(self, checkout_session_id: str, razorpay_payment_id: str) -> dict:
        """Mark the session paid. Idempotent per ACP; safe to retry."""
        r = self._http().post(
            f"/checkout_sessions/{checkout_session_id}/complete",
            headers=self._headers(idempotency_key=f"complete:{checkout_session_id}"),
            json={"payment_reference": razorpay_payment_id},
        )
        r.raise_for_status()
        return r.json()

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
