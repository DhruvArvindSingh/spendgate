"""Settlement state machine (PRD 8).

Connects an approved decision to the rail and back to the ledger. The whole
point of this module is one distinction:

  a payment that FAILED       -> release the reservation, budget comes back
  a payment whose outcome is
  UNKNOWN (INDETERMINATE)     -> hold. Neither release nor commit.

Releasing an indeterminate payment invites a double-spend when it settles late;
committing it invents a charge that never happened. Collapsing the two is the
most common accounting bug in payment systems.

Ordering (PRD 8.2): the decision and reservation are already durable before
anything here runs. A crash between reservation and execution leaves a
recoverable held reservation; a crash between a rail call and its record would
leave money moved with no trace, which is why the rail is called last.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Callable

from .ledger import InMemoryLedger
from .money import Paise, fmt
from .rail import RESERVATION_TTL, Rail, RailError, RailTimeout
from .webhooks import WebhookEvent


class AuthState(str, Enum):
    RESERVED = "RESERVED"
    EXECUTING = "EXECUTING"
    SETTLED = "SETTLED"
    FAILED = "FAILED"
    INDETERMINATE = "INDETERMINATE"
    REFUNDED = "REFUNDED"
    MISMATCH = "MISMATCH"
    #: Reservation released after our own timeout on an order nobody paid.
    #: The order remains payable at Razorpay forever, so this state carries a
    #: compensating control: a late capture against it is refunded and alerted.
    ABANDONED = "ABANDONED"


#: Terminal states never transition again. A late webhook against one of these
#: is an anomaly to record, not an instruction to follow.
TERMINAL = {AuthState.SETTLED, AuthState.FAILED, AuthState.REFUNDED,
            AuthState.MISMATCH, AuthState.ABANDONED}


@dataclass
class Authorization:
    auth_id: str
    mandate_id: str
    checkout_session_id: str
    approved_minor: Paise
    merchant_id: str
    state: AuthState = AuthState.RESERVED
    order_id: str | None = None
    payment_id: str | None = None
    captured_minor: Paise | None = None
    sku: str | None = None
    reserved_at: datetime | None = None
    history: list[tuple[str, str]] = field(default_factory=list)

    def to(self, state: AuthState, note: str = "") -> None:
        self.history.append((state.value, note))
        self.state = state


@dataclass
class Settlement:
    ledger: InMemoryLedger
    rail: Rail
    authorizations: dict[str, Authorization] = field(default_factory=dict)
    anomalies: list[str] = field(default_factory=list)
    on_alert: object = None                 # callable(str) for principal alerts
    #: Injected, like the engine's. Ledger entries written here feed the
    #: windowed rules (velocity, aggregate), so a Settlement reading the wall
    #: clock while the engine reads an injected one silently moves settled
    #: payments outside the windows that are supposed to see them.
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
    #: How long a reservation is held for an order nobody has paid. Razorpay
    #: orders never expire, so this timeout is ours and the release is backed by
    #: a compensating control rather than by the order becoming unpayable.
    reservation_ttl_seconds: int = RESERVATION_TTL
    _lock: threading.RLock = field(default_factory=threading.RLock)

    def _now(self) -> datetime:
        return self.clock()

    def _alert(self, message: str) -> None:
        self.anomalies.append(message)
        if callable(self.on_alert):
            self.on_alert(message)

    # ------------------------------------------------------------- execute
    def execute(self, auth: Authorization) -> Authorization:
        """Create the order for the amount the BOUNCER read, never agent input."""
        with self._lock:
            auth.reserved_at = auth.reserved_at or self._now()
            self.authorizations[auth.auth_id] = auth
            try:
                order = self.rail.create_order(
                    amount_minor=auth.approved_minor,
                    receipt=auth.auth_id,
                    notes={"mandate_id": auth.mandate_id,
                           "checkout_session_id": auth.checkout_session_id},
                )
            except RailTimeout as exc:
                # Outcome unknown: the order may or may not exist. Hold.
                auth.to(AuthState.INDETERMINATE, f"order timeout: {exc}")
                return auth
            except RailError as exc:
                # A refused request never moved money, so the budget is safe to
                # return - the distinction the whole module turns on.
                auth.to(AuthState.FAILED, f"order rejected: {exc}")
                self.ledger.release(auth.mandate_id, auth.auth_id, self._now())
                return auth
            auth.order_id = order["id"]
            auth.to(AuthState.EXECUTING, f"order {order['id']}")
            return auth

    # -------------------------------------------------------------- events
    def on_event(self, event: WebhookEvent) -> Authorization | None:
        """Dispatch a verified webhook. Transitions are guarded by CURRENT state,
        not by arrival order, so out-of-order delivery is safe."""
        with self._lock:
            auth = self._find(event)
            if auth is None:
                self._alert(f"webhook for unknown authorization: {event.payment_id}")
                return None
            if event.event == "payment.captured":
                return self._captured(auth, event)
            if event.event == "payment.failed":
                return self._failed(auth, event)
            if event.event in ("refund.processed", "refund.created"):
                return self._refunded(auth, event)
            return auth

    def _find(self, event: WebhookEvent) -> Authorization | None:
        for a in self.authorizations.values():
            if (event.order_id and a.order_id == event.order_id) or (
                event.payment_id and a.payment_id == event.payment_id
            ):
                return a
        return None

    def _captured(self, auth: Authorization, event: WebhookEvent) -> Authorization:
        if auth.state is AuthState.SETTLED:
            return auth                                   # duplicate delivery
        if auth.state is AuthState.ABANDONED:
            # The compensating control. We released this budget because nobody
            # had paid; someone has now paid anyway. Money moved outside any
            # live reservation, so it is refunded rather than absorbed.
            self._alert(
                f"late capture on abandoned {auth.auth_id}: "
                f"{fmt(event.amount_minor or 0)} moved after the reservation was released"
            )
            try:
                if event.payment_id:
                    self.rail.refund(event.payment_id, event.amount_minor or auth.approved_minor)
            except RailError as exc:
                self._alert(f"refund of late capture failed: {exc}")
            return auth
        if auth.state in TERMINAL:
            self._alert(f"late payment.captured on {auth.state.value} {auth.auth_id}")
            return auth

        # Webhook receipt is not proof. Confirm independently with the rail
        # (PRD 9.4) rather than believing what we were told.
        captured = event.amount_minor
        try:
            confirmed = self.rail.fetch_payment(event.payment_id)
            captured = confirmed.get("amount", captured)
            if confirmed.get("status") != "captured":
                auth.to(AuthState.INDETERMINATE, "rail disagrees with webhook")
                return auth
        except RailError as exc:
            auth.to(AuthState.INDETERMINATE, f"could not confirm: {exc}")
            return auth

        auth.payment_id = event.payment_id
        auth.captured_minor = captured

        if captured != auth.approved_minor:
            # Merchant-side integrity failure (A7). Do not settle: alert and
            # refund the difference. Committing here would let a merchant
            # decide how much of the budget to consume.
            auth.to(AuthState.MISMATCH,
                    f"approved {auth.approved_minor}, captured {captured}")
            self._alert(
                f"amount_mismatch on {auth.auth_id}: approved {fmt(auth.approved_minor)}, "
                f"captured {fmt(captured)}"
            )
            try:
                self.rail.refund(event.payment_id, captured)
            except RailError as exc:
                self._alert(f"refund after mismatch failed: {exc}")
            self.ledger.release(auth.mandate_id, auth.auth_id, self._now())
            return auth

        self.ledger.commit(
            auth.mandate_id, auth.auth_id, self._now(),
            merchant_id=auth.merchant_id, sku=auth.sku,
            unit_minor=auth.approved_minor, ref=event.payment_id,
        )
        auth.to(AuthState.SETTLED, event.payment_id or "")
        return auth

    def _failed(self, auth: Authorization, event: WebhookEvent) -> Authorization:
        if auth.state is AuthState.FAILED:
            return auth
        if auth.state in TERMINAL:
            # A late failure for a payment that settled must NOT release budget.
            self._alert(f"late payment.failed on {auth.state.value} {auth.auth_id}")
            return auth
        auth.payment_id = event.payment_id
        self.ledger.release(auth.mandate_id, auth.auth_id, self._now())
        auth.to(AuthState.FAILED, event.error_description or "payment failed")
        return auth

    def _refunded(self, auth: Authorization, event: WebhookEvent) -> Authorization:
        if auth.state is not AuthState.SETTLED:
            self._alert(f"refund on non-settled {auth.auth_id} ({auth.state.value})")
            return auth
        amount = event.refund_amount or auth.approved_minor
        self.ledger.credit(auth.mandate_id, auth.auth_id, amount, self._now())
        auth.to(AuthState.REFUNDED, f"refunded {fmt(amount)}")
        return auth

    # ----------------------------------------------------------- reconcile
    def reconcile(self, auth_id: str) -> Authorization:
        """Resolve an INDETERMINATE authorization by asking the rail.

        The only path out of "we don't know". It never guesses: a reservation is
        released only once the money definitively did not move AND cannot still
        move. An order that is unpaid but still payable stays held, and says so.
        """
        with self._lock:
            auth = self.authorizations[auth_id]
            if auth.state is not AuthState.INDETERMINATE:
                return auth

            if auth.order_id is None:
                # No order exists, so nothing could have been charged.
                self.ledger.release(auth.mandate_id, auth.auth_id, self._now())
                auth.to(AuthState.FAILED, "reconciled: order was never created")
                return auth

            try:
                payments = self.rail.fetch_order_payments(auth.order_id)
                order = self.rail.fetch_order(auth.order_id)
            except RailError as exc:
                self._alert(f"reconcile failed for {auth_id}: {exc}")
                return auth

            captured = next((p for p in payments if p.get("status") == "captured"), None)
            if captured is not None:
                auth.payment_id = captured["id"]
                auth.captured_minor = captured["amount"]
                if captured["amount"] != auth.approved_minor:
                    auth.to(AuthState.MISMATCH, "reconciled with wrong amount")
                    self._alert(f"amount_mismatch on reconcile for {auth_id}")
                    self.ledger.release(auth.mandate_id, auth.auth_id, self._now())
                    return auth
                self.ledger.commit(
                    auth.mandate_id, auth.auth_id, self._now(),
                    merchant_id=auth.merchant_id, sku=auth.sku,
                    unit_minor=auth.approved_minor, ref=captured["id"],
                )
                auth.to(AuthState.SETTLED, "reconciled")
                return auth

            if payments and all(p.get("status") == "failed" for p in payments):
                self.ledger.release(auth.mandate_id, auth.auth_id, self._now())
                auth.to(AuthState.FAILED, "reconciled: all attempts failed")
                return auth

            # Nothing captured, nothing failed: nobody has paid yet. Razorpay
            # orders never expire, so there is no moment at which the rail
            # declares this dead. We hold for our own TTL and then release.
            held_for = (self._now() - (auth.reserved_at or self._now())).total_seconds()
            if held_for < self.reservation_ttl_seconds:
                remaining = int(self.reservation_ttl_seconds - held_for)
                auth.to(AuthState.INDETERMINATE,
                        f"order {order.get('id')} unpaid ({order.get('attempts', 0)} "
                        f"attempts); holding for another {remaining}s")
                return auth

            self.ledger.release(auth.mandate_id, auth.auth_id, self._now())
            auth.to(AuthState.ABANDONED,
                    f"unpaid after {int(held_for)}s; reservation released. "
                    "The order stays payable — a late capture will be refunded.")
            self._alert(f"{auth.auth_id} abandoned unpaid; order {order.get('id')} "
                        "remains payable at the rail")
            return auth
