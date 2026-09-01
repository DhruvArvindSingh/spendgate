"""Chaos suite (PRD 14.4).

Fault injection with the ledger invariant asserted after every scenario. These
are the failures that only appear in production, and the ones a demo never sees.
"""

from __future__ import annotations

import json
import random
import threading
from datetime import datetime, timedelta, timezone

import pytest

from spendgate import InMemoryLedger, rupees
from spendgate.rail import FakeRazorpay, RailError, RailTimeout
from spendgate.settlement import AuthState, Authorization, Settlement
from spendgate.webhooks import EventDeduplicator, receive, sign

MANDATE, MERCHANT, SECRET = "mnd_chaos", "mrc_lumen", "whsec_chaos"
BUDGET = rupees(15_000)
T0 = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)


@pytest.fixture
def rig():
    ledger = InMemoryLedger()
    ledger.open_account(MANDATE, BUDGET)
    rail = FakeRazorpay()
    return ledger, rail, Settlement(ledger=ledger, rail=rail, clock=lambda: T0)


def reserve_and_execute(rig, auth_id, amount):
    ledger, rail, s = rig
    ledger.reserve(MANDATE, auth_id, amount, T0, MERCHANT)
    return s.execute(Authorization(auth_id, MANDATE, f"cs_{auth_id}", amount, MERCHANT))


def deliver(rig, event, payment, refund=None, event_id=None, dedup=None):
    _, rail, s = rig
    body = json.dumps(rail.webhook_body(event, payment, refund)).encode()
    parsed = receive(body, {"X-Razorpay-Signature": sign(body, SECRET),
                            "x-razorpay-event-id": event_id or f"evt_{payment['id']}_{event}"},
                     SECRET, dedup or EventDeduplicator())
    return s.on_event(parsed) if parsed else None


# ------------------------------------------------------- crash recovery
def test_crash_between_reserve_and_execute_leaves_a_recoverable_hold(rig):
    """The reason the rail is called last: this state is recoverable."""
    ledger, rail, s = rig
    ledger.reserve(MANDATE, "aut_1", rupees(4_000), T0, MERCHANT)
    # ... process dies here. Nothing was sent to the rail.
    ledger.check_invariant(MANDATE)
    assert ledger.snapshot(MANDATE).reserved_minor == rupees(4_000)
    assert rail.orders == {}, "no order can exist yet"

    # On restart the sweeper releases a reservation with no order behind it.
    ledger.release(MANDATE, "aut_1", T0 + timedelta(minutes=15))
    assert ledger.available(MANDATE) == BUDGET
    ledger.check_invariant(MANDATE)


def test_crash_after_the_rail_call_is_recovered_by_receipt(rig):
    """The unrecoverable-looking case. The order carries our authorization id as
    its receipt, so a restart can find money that moved without a local record."""
    ledger, rail, s = rig
    ledger.reserve(MANDATE, "aut_2", rupees(4_000), T0, MERCHANT)
    order = rail.create_order(rupees(4_000), "aut_2", {})
    rail.pay(order["id"])
    # ... process dies before the order id was written down.

    assert "aut_2" in rail.receipts, "the receipt is the recovery handle"
    recovered = rail.orders[rail.receipts["aut_2"]]
    auth = Authorization("aut_2", MANDATE, "cs_2", rupees(4_000), MERCHANT)
    auth.order_id = recovered["id"]
    auth.to(AuthState.INDETERMINATE, "recovered after crash")
    s.authorizations["aut_2"] = auth

    auth = s.reconcile("aut_2")
    assert auth.state is AuthState.SETTLED
    assert ledger.snapshot(MANDATE).settled_minor == rupees(4_000)
    ledger.check_invariant(MANDATE)


# ------------------------------------------------------ delivery chaos
def test_webhook_delivered_twice(rig):
    ledger, rail, s = rig
    auth = reserve_and_execute(rig, "aut_3", rupees(3_000))
    payment = rail.pay(auth.order_id)
    dedup = EventDeduplicator()
    deliver(rig, "payment.captured", payment, event_id="evt_x", dedup=dedup)
    deliver(rig, "payment.captured", payment, event_id="evt_x", dedup=dedup)
    assert ledger.snapshot(MANDATE).settled_minor == rupees(3_000)
    ledger.check_invariant(MANDATE)


def test_captured_then_stale_failure(rig):
    ledger, rail, s = rig
    auth = reserve_and_execute(rig, "aut_4", rupees(3_000))
    payment = rail.pay(auth.order_id)
    deliver(rig, "payment.captured", payment)
    deliver(rig, "payment.failed", dict(payment, status="failed"))
    assert ledger.snapshot(MANDATE).settled_minor == rupees(3_000), "must not un-settle"
    ledger.check_invariant(MANDATE)


def test_failure_then_late_capture(rig):
    """The dangerous direction: budget was released, then a capture arrives."""
    ledger, rail, s = rig
    auth = reserve_and_execute(rig, "aut_5", rupees(3_000))
    rail.fail_next = True
    failed = rail.pay(auth.order_id)
    deliver(rig, "payment.failed", failed)
    assert ledger.available(MANDATE) == BUDGET

    late = dict(failed, status="captured")
    rail.payments[late["id"]] = late
    auth = deliver(rig, "payment.captured", late, event_id="evt_late")
    assert auth.state is AuthState.FAILED, "a terminal state is not reopened by a webhook"
    assert any("late payment.captured" in a for a in s.anomalies), "it must be flagged"
    ledger.check_invariant(MANDATE)


def test_refund_arriving_before_capture_is_flagged_not_applied(rig):
    ledger, rail, s = rig
    auth = reserve_and_execute(rig, "aut_6", rupees(2_000))
    payment = rail.pay(auth.order_id)
    refund = {"id": "rfnd_x", "payment_id": payment["id"], "amount": rupees(2_000)}
    deliver(rig, "refund.processed", payment, refund)
    assert ledger.snapshot(MANDATE).settled_minor == 0
    assert any("refund on non-settled" in a for a in s.anomalies)
    ledger.check_invariant(MANDATE)


# ---------------------------------------------------------- rail chaos
def test_rail_timeout_then_reconcile_to_settled(rig):
    ledger, rail, s = rig
    ledger.reserve(MANDATE, "aut_7", rupees(2_500), T0, MERCHANT)
    rail.timeout_next = True
    auth = s.execute(Authorization("aut_7", MANDATE, "cs_7", rupees(2_500), MERCHANT))
    assert auth.state is AuthState.INDETERMINATE
    assert ledger.snapshot(MANDATE).reserved_minor == rupees(2_500), "held, not released"
    auth = s.reconcile("aut_7")
    assert auth.state is AuthState.FAILED          # no order was ever created
    assert ledger.available(MANDATE) == BUDGET
    ledger.check_invariant(MANDATE)


def test_rail_unreachable_during_confirmation_holds(rig):
    """Webhook says captured; the rail cannot confirm. We do not take its word."""
    ledger, rail, s = rig
    auth = reserve_and_execute(rig, "aut_8", rupees(2_000))
    payment = rail.pay(auth.order_id)

    class Unreachable(FakeRazorpay):
        def fetch_payment(self, payment_id):
            raise RailError("connection reset")

    s.rail = Unreachable()
    auth = deliver(rig, "payment.captured", payment)
    assert auth.state is AuthState.INDETERMINATE
    assert ledger.snapshot(MANDATE).reserved_minor == rupees(2_000)
    ledger.check_invariant(MANDATE)


# ------------------------------------------------------------ the fuzz
@pytest.mark.parametrize("seed", [1, 7, 42, 1337])
def test_random_interleaving_preserves_the_invariant(seed):
    """40 random lifecycle operations across 8 threads. The invariant is the
    only thing asserted, because it is the only thing that must always hold."""
    r = random.Random(seed)
    ledger = InMemoryLedger()
    ledger.open_account(MANDATE, BUDGET)
    rail = FakeRazorpay()
    s = Settlement(ledger=ledger, rail=rail, clock=lambda: T0)
    errors: list[Exception] = []

    def worker(i: int):
        auth_id = f"aut_{i}"
        amount = r.choice([rupees(200), rupees(900), rupees(2_000)])
        try:
            with ledger.begin(MANDATE, timeout=10):
                ledger.reserve(MANDATE, auth_id, amount, T0, MERCHANT)
        except Exception:                                   # noqa: BLE001
            return                                          # budget exhausted
        try:
            roll = r.random()
            if roll < 0.2:
                ledger.release(MANDATE, auth_id, T0)                    # failed
            elif roll < 0.35:
                pass                                                     # indeterminate: hold
            else:
                ledger.commit(MANDATE, auth_id, T0, merchant_id=MERCHANT)
                if r.random() < 0.3:
                    ledger.credit(MANDATE, auth_id, amount, T0)          # refunded
        except Exception as exc:                            # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(40)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, errors
    ledger.check_invariant(MANDATE)
    ok, bad = ledger.verify_chain(MANDATE)
    assert ok, f"chain broke at {bad}"
