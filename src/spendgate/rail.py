"""Razorpay rail adapter (PRD 5 C6, 11).

A thin client over the documented REST API rather than the SDK: it keeps the
dependency list short and makes the actual contract visible to a reader.

FakeRazorpay implements the same interface in memory so the settlement state
machine is genuinely exercised without live keys. Every failure mode Phase 2
claims to handle has a switch here.
"""

from __future__ import annotations

import itertools
import threading
import uuid
from dataclasses import dataclass, field
from typing import Protocol

import httpx

API_BASE = "https://api.razorpay.com/v1"


class RailError(RuntimeError):
    pass


class RailTimeout(RailError):
    """Outcome unknown. Never released, never committed — held for reconciliation."""


class Rail(Protocol):
    def create_order(self, amount_minor: int, receipt: str, notes: dict) -> dict: ...
    def fetch_payment(self, payment_id: str) -> dict: ...
    def fetch_order_payments(self, order_id: str) -> list[dict]: ...
    def refund(self, payment_id: str, amount_minor: int) -> dict: ...


@dataclass
class RazorpayRail:
    """Live (test-mode) Razorpay. Requires rzp_test_* credentials."""

    key_id: str
    key_secret: str
    base_url: str = API_BASE
    timeout: float = 10.0
    _client: httpx.Client | None = None

    def __post_init__(self) -> None:
        if self.key_id and not self.key_id.startswith("rzp_test"):
            raise ValueError(
                "SpendGate refuses non-test keys. This system has never moved real "
                "money and must not be the first thing to try."
            )

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.base_url, timeout=self.timeout,
                auth=(self.key_id, self.key_secret),
            )
        return self._client

    def _call(self, method: str, path: str, **kw) -> dict:
        try:
            r = self._http().request(method, path, **kw)
        except httpx.TimeoutException as exc:
            raise RailTimeout(str(exc)) from exc
        except httpx.HTTPError as exc:
            raise RailError(str(exc)) from exc
        if r.status_code >= 500:
            raise RailTimeout(f"rail returned {r.status_code}")   # outcome unknown
        if r.status_code >= 400:
            raise RailError(f"{r.status_code}: {r.text[:300]}")
        return r.json()

    def create_order(self, amount_minor: int, receipt: str, notes: dict) -> dict:
        # The amount is set here, server side, from facts resolved out of band.
        # `receipt` carries our authorization id so a retry is reconcilable.
        return self._call("POST", "/orders", json={
            "amount": amount_minor, "currency": "INR",
            "receipt": receipt, "notes": notes, "payment_capture": 1,
        })

    def fetch_payment(self, payment_id: str) -> dict:
        return self._call("GET", f"/payments/{payment_id}")

    def fetch_order_payments(self, order_id: str) -> list[dict]:
        return self._call("GET", f"/orders/{order_id}/payments").get("items", [])

    def refund(self, payment_id: str, amount_minor: int) -> dict:
        return self._call("POST", f"/payments/{payment_id}/refund",
                          json={"amount": amount_minor})

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None


@dataclass
class FakeRazorpay:
    """In-memory rail with the same contract and a switch for each failure mode."""

    orders: dict[str, dict] = field(default_factory=dict)
    payments: dict[str, dict] = field(default_factory=dict)
    refunds: dict[str, dict] = field(default_factory=dict)
    receipts: dict[str, str] = field(default_factory=dict)
    fail_next: bool = False              # payment declines (failure@razorpay)
    timeout_next: bool = False           # outcome unknown
    capture_amount_override: int | None = None   # A7: capture more than approved
    _seq: itertools.count = field(default_factory=lambda: itertools.count(1))
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def create_order(self, amount_minor: int, receipt: str, notes: dict) -> dict:
        if self.timeout_next:
            self.timeout_next = False
            raise RailTimeout("simulated rail timeout")
        with self._lock:
            if receipt in self.receipts:                 # idempotent by receipt
                return self.orders[self.receipts[receipt]]
            oid = f"order_{next(self._seq):012d}"
            order = {"id": oid, "amount": amount_minor, "currency": "INR",
                     "receipt": receipt, "notes": notes, "status": "created"}
            self.orders[oid] = order
            self.receipts[receipt] = oid
            return order

    def pay(self, order_id: str) -> dict:
        """Simulate the customer completing (or failing) the payment."""
        with self._lock:
            order = self.orders[order_id]
            pid = f"pay_{next(self._seq):012d}"
            if self.fail_next:
                self.fail_next = False
                payment = {"id": pid, "order_id": order_id, "amount": order["amount"],
                           "currency": "INR", "status": "failed",
                           "error_code": "BAD_REQUEST_ERROR",
                           "error_description": "Payment failed at the bank."}
            else:
                captured = self.capture_amount_override or order["amount"]
                self.capture_amount_override = None
                payment = {"id": pid, "order_id": order_id, "amount": captured,
                           "currency": "INR", "status": "captured", "method": "upi"}
                order["status"] = "paid"
            self.payments[pid] = payment
            return payment

    def fetch_payment(self, payment_id: str) -> dict:
        if payment_id not in self.payments:
            raise RailError(f"no such payment {payment_id}")
        return self.payments[payment_id]

    def fetch_order_payments(self, order_id: str) -> list[dict]:
        return [p for p in self.payments.values() if p["order_id"] == order_id]

    def refund(self, payment_id: str, amount_minor: int) -> dict:
        rid = f"rfnd_{next(self._seq):012d}"
        r = {"id": rid, "payment_id": payment_id, "amount": amount_minor,
             "status": "processed"}
        self.refunds[rid] = r
        return r

    # ------------------------------------------------------------- webhooks
    def webhook_body(self, event: str, payment: dict, refund: dict | None = None) -> dict:
        payload: dict = {"payment": {"entity": payment}}
        if refund is not None:
            payload["refund"] = {"entity": refund}
        return {"entity": "event", "event": event, "contains": list(payload),
                "payload": payload, "created_at": 1_756_000_000}
