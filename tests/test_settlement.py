"""Settlement state machine (PRD 8, 9.3, 9.4).

The distinction these tests exist to protect: FAILED returns the budget,
INDETERMINATE holds it. Everything else here is a consequence of that.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from spendgate import InMemoryLedger, rupees
from spendgate.rail import FakeRazorpay, RailTimeout
from spendgate.settlement import AuthState, Authorization, Settlement
from spendgate.webhooks import (
    EventDeduplicator, WebhookEvent, WebhookVerificationError, receive, sign,
)

MANDATE, MERCHANT, SECRET = "mnd_1", "mrc_lumen", "whsec_test"
BUDGET, AMOUNT = rupees(15_000), rupees(1_200)
#: A pinned clock, for the tests that compare an order's expiry timestamp.
NOW = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)


@pytest.fixture
def rig():
    ledger = InMemoryLedger()
    ledger.open_account(MANDATE, BUDGET)
    rail = FakeRazorpay()
    return ledger, rail, Settlement(ledger=ledger, rail=rail)


def start(rig, amount=AMOUNT, auth_id="aut_1") -> Authorization:
    ledger, rail, s = rig
    ledger.reserve(MANDATE, auth_id, amount, datetime.now(timezone.utc), MERCHANT)
    return s.execute(Authorization(auth_id, MANDATE, "cs_1", amount, MERCHANT))


def deliver(rig, event: str, payment: dict, refund=None, event_id="evt_1"):
    _, rail, s = rig
    body = json.dumps(rail.webhook_body(event, payment, refund)).encode()
    headers = {"X-Razorpay-Signature": sign(body, SECRET), "x-razorpay-event-id": event_id}
    parsed = receive(body, headers, SECRET, EventDeduplicator())
    return s.on_event(parsed)


# ------------------------------------------------------------ happy path
def test_capture_commits_the_reservation(rig):
    ledger, rail, s = rig
    auth = start(rig)
    assert auth.state is AuthState.EXECUTING
    assert ledger.snapshot(MANDATE).reserved_minor == AMOUNT

    payment = rail.pay(auth.order_id)
    auth = deliver(rig, "payment.captured", payment)

    assert auth.state is AuthState.SETTLED
    assert ledger.snapshot(MANDATE).settled_minor == AMOUNT
    assert ledger.snapshot(MANDATE).reserved_minor == 0
    ledger.check_invariant(MANDATE)


def test_the_order_is_created_for_the_amount_spendgate_read(rig):
    _, rail, _ = rig
    auth = start(rig)
    assert rail.orders[auth.order_id]["amount"] == AMOUNT
    assert rail.orders[auth.order_id]["receipt"] == auth.auth_id


# ---------------------------------------------------- failed vs unknown
def test_failed_payment_returns_the_budget(rig):
    ledger, rail, s = rig
    auth = start(rig)
    rail.fail_next = True
    payment = rail.pay(auth.order_id)
    auth = deliver(rig, "payment.failed", payment)

    assert auth.state is AuthState.FAILED
    assert ledger.available(MANDATE) == BUDGET, "a failed payment must free its budget"
    ledger.check_invariant(MANDATE)


def test_rail_timeout_holds_the_budget_and_does_not_release(rig):
    """The distinction the module exists for. Releasing here would allow a
    double-spend if the original payment settles late."""
    ledger, rail, s = rig
    ledger.reserve(MANDATE, "aut_t", AMOUNT, datetime.now(timezone.utc), MERCHANT)
    rail.timeout_next = True
    auth = s.execute(Authorization("aut_t", MANDATE, "cs_t", AMOUNT, MERCHANT))

    assert auth.state is AuthState.INDETERMINATE
    assert ledger.snapshot(MANDATE).reserved_minor == AMOUNT, "must stay held"
    assert ledger.snapshot(MANDATE).settled_minor == 0, "must not be counted as spent"
    ledger.check_invariant(MANDATE)


def test_rejected_order_releases_because_nothing_moved(rig):
    ledger, rail, s = rig

    class Rejecting(FakeRazorpay):
        def create_order(self, **kw):
            from spendgate.rail import RailError
            raise RailError("400: invalid amount")

    s.rail = Rejecting()
    ledger.reserve(MANDATE, "aut_r", AMOUNT, datetime.now(timezone.utc), MERCHANT)
    auth = s.execute(Authorization("aut_r", MANDATE, "cs_r", AMOUNT, MERCHANT))
    assert auth.state is AuthState.FAILED
    assert ledger.available(MANDATE) == BUDGET
    ledger.check_invariant(MANDATE)


# ------------------------------------------------------------ reconcile
def test_reconcile_settles_a_payment_that_actually_captured(rig):
    ledger, rail, s = rig
    auth = start(rig, auth_id="aut_x")
    rail.pay(auth.order_id)                       # captured, webhook never arrived
    auth.to(AuthState.INDETERMINATE, "simulated lost webhook")

    auth = s.reconcile("aut_x")
    assert auth.state is AuthState.SETTLED
    assert ledger.snapshot(MANDATE).settled_minor == AMOUNT
    ledger.check_invariant(MANDATE)


def test_reconcile_releases_when_the_order_was_never_created(rig):
    ledger, rail, s = rig
    ledger.reserve(MANDATE, "aut_t", AMOUNT, datetime.now(timezone.utc), MERCHANT)
    rail.timeout_next = True
    s.execute(Authorization("aut_t", MANDATE, "cs_t", AMOUNT, MERCHANT))

    auth = s.reconcile("aut_t")
    assert auth.state is AuthState.FAILED
    assert ledger.available(MANDATE) == BUDGET
    ledger.check_invariant(MANDATE)


# ---------------------------------------------------- merchant integrity
def test_capturing_more_than_approved_does_not_settle(rig):
    """A7 / PRD 9.4. Committing here would let a merchant decide how much of
    the principal's budget to consume."""
    ledger, rail, s = rig
    auth = start(rig)
    rail.capture_amount_override = rupees(9_000)
    payment = rail.pay(auth.order_id)
    auth = deliver(rig, "payment.captured", payment)

    assert auth.state is AuthState.MISMATCH
    assert ledger.snapshot(MANDATE).settled_minor == 0, "must not be counted as spend"
    assert ledger.available(MANDATE) == BUDGET
    assert any("amount_mismatch" in a for a in s.anomalies)
    assert rail.refunds, "the over-capture must be refunded"
    ledger.check_invariant(MANDATE)


# -------------------------------------------------- delivery robustness
def test_duplicate_capture_webhook_is_idempotent(rig):
    ledger, rail, s = rig
    auth = start(rig)
    payment = rail.pay(auth.order_id)
    deliver(rig, "payment.captured", payment, event_id="evt_a")
    deliver(rig, "payment.captured", payment, event_id="evt_b")   # redelivered

    assert ledger.snapshot(MANDATE).settled_minor == AMOUNT, "must not double-count"
    ledger.check_invariant(MANDATE)


def test_late_failure_after_settlement_does_not_release_budget(rig):
    """Out-of-order delivery. Transitions are guarded by state, not arrival."""
    ledger, rail, s = rig
    auth = start(rig)
    payment = rail.pay(auth.order_id)
    deliver(rig, "payment.captured", payment, event_id="evt_a")

    stale = dict(payment, status="failed", error_description="stale event")
    auth = deliver(rig, "payment.failed", stale, event_id="evt_b")

    assert auth.state is AuthState.SETTLED
    assert ledger.snapshot(MANDATE).settled_minor == AMOUNT
    assert any("late payment.failed" in a for a in s.anomalies)
    ledger.check_invariant(MANDATE)


def test_refund_credits_the_budget_back(rig):
    ledger, rail, s = rig
    auth = start(rig)
    payment = rail.pay(auth.order_id)
    deliver(rig, "payment.captured", payment, event_id="evt_a")
    refund = rail.refund(payment["id"], AMOUNT)
    auth = deliver(rig, "refund.processed", payment, refund, event_id="evt_b")

    assert auth.state is AuthState.REFUNDED
    assert ledger.available(MANDATE) == BUDGET
    ledger.check_invariant(MANDATE)


# -------------------------------------------------------------- webhooks
def test_forged_signature_is_rejected(rig):
    _, rail, _ = rig
    body = json.dumps(rail.webhook_body("payment.captured", {"id": "pay_x"})).encode()
    with pytest.raises(WebhookVerificationError):
        receive(body, {"X-Razorpay-Signature": "0" * 64}, SECRET)
    with pytest.raises(WebhookVerificationError):
        receive(body, {}, SECRET)


def test_signature_covers_the_raw_body(rig):
    """Verifying a re-serialised body would accept a tampered payload whose
    parsed form is equivalent. The signature is over bytes."""
    _, rail, _ = rig
    body = json.dumps(rail.webhook_body("payment.captured", {"id": "pay_x", "amount": 100})).encode()
    signature = sign(body, SECRET)
    tampered = body.replace(b'"amount": 100', b'"amount": 900')
    with pytest.raises(WebhookVerificationError):
        receive(tampered, {"X-Razorpay-Signature": signature}, SECRET)


def test_event_id_deduplication(rig):
    _, rail, _ = rig
    dedup = EventDeduplicator()
    body = json.dumps(rail.webhook_body("payment.captured", {"id": "pay_x"})).encode()
    headers = {"X-Razorpay-Signature": sign(body, SECRET), "x-razorpay-event-id": "evt_dup"}
    assert receive(body, headers, SECRET, dedup) is not None
    assert receive(body, headers, SECRET, dedup) is None, "redelivery must be dropped"


# ---------------------------------------------------------------- the clock
def test_settlement_writes_ledger_entries_at_the_injected_time():
    """Regression. Settlement used to stamp entries with the wall clock while
    the engine read an injected one. Ledger entries feed the windowed rules
    (velocity, aggregate), so the drift silently moved settled payments outside
    the windows meant to see them — structuring stopped being detected, with
    every component individually correct.
    """
    from spendgate.settlement import Settlement

    ledger = InMemoryLedger()
    ledger.open_account(MANDATE, BUDGET)
    rail = FakeRazorpay()
    t = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    s = Settlement(ledger=ledger, rail=rail, clock=lambda: t)

    ledger.reserve(MANDATE, "aut_c", AMOUNT, t, MERCHANT)
    auth = s.execute(Authorization("aut_c", MANDATE, "cs_c", AMOUNT, MERCHANT))
    payment = rail.pay(auth.order_id)
    body = json.dumps(rail.webhook_body("payment.captured", payment)).encode()
    s.on_event(receive(body, {"X-Razorpay-Signature": sign(body, SECRET)}, SECRET))

    settled = ledger.snapshot(MANDATE).recent
    assert settled and settled[-1].at == t, (
        f"ledger entry stamped {settled[-1].at}, expected the injected {t}"
    )


def test_a_settled_payment_is_visible_to_the_windowed_rules():
    """The consequence the bug above hid: what settles must be inside the
    window the next decision looks at."""
    from datetime import timedelta as _td

    from spendgate.settlement import Settlement

    ledger = InMemoryLedger()
    ledger.open_account(MANDATE, BUDGET)
    rail = FakeRazorpay()
    t = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    s = Settlement(ledger=ledger, rail=rail, clock=lambda: t)

    ledger.reserve(MANDATE, "aut_w", AMOUNT, t, MERCHANT)
    auth = s.execute(Authorization("aut_w", MANDATE, "cs_w", AMOUNT, MERCHANT))
    payment = rail.pay(auth.order_id)
    body = json.dumps(rail.webhook_body("payment.captured", payment)).encode()
    s.on_event(receive(body, {"X-Razorpay-Signature": sign(body, SECRET)}, SECRET))

    recent = ledger.snapshot(MANDATE).recent
    cutoff = (t + _td(minutes=5)) - _td(seconds=3600)
    assert [x for x in recent if x.at > cutoff], "settled payment fell outside its own window"


# --------------------------------------------------- unpaid orders (BUGS §9)
def _indeterminate(rig, auth_id="aut_u", amount=AMOUNT):
    """An authorization whose order exists but whose webhook never arrived."""
    ledger, rail, s = rig
    s.clock = lambda: NOW
    ledger.reserve(MANDATE, auth_id, amount, NOW, MERCHANT)
    auth = s.execute(Authorization(auth_id, MANDATE, f"cs_{auth_id}", amount, MERCHANT))
    auth.to(AuthState.INDETERMINATE, "simulated lost webhook")
    return auth


def test_orders_carry_no_expiry_because_the_rail_rejects_one(rig):
    """Razorpay's Orders API answers expire_by with "not required and should not
    be sent" — it is a Payment Links field. Sending one fails the whole call, so
    the reservation timeout has to be ours instead."""
    ledger, rail, s = rig
    auth = _indeterminate(rig, "aut_x")
    assert "expire_by" not in rail.fetch_order(auth.order_id)
    assert s.reservation_ttl_seconds > 0, "the timeout lives on our side"


def test_reconcile_holds_an_unpaid_reservation_inside_the_ttl(rig):
    """Releasing early invites a double-spend: the order is still payable."""
    ledger, rail, s = rig
    auth = _indeterminate(rig)

    auth = s.reconcile(auth.auth_id)

    assert auth.state is AuthState.INDETERMINATE
    assert "holding for another" in auth.history[-1][1]
    assert ledger.snapshot(MANDATE).reserved_minor == AMOUNT
    assert ledger.snapshot(MANDATE).settled_minor == 0
    ledger.check_invariant(MANDATE)


def test_reconcile_abandons_an_unpaid_reservation_after_the_ttl(rig):
    """Budget cannot be held forever for an order nobody paid, so it is
    released — and the state records that the order is still live."""
    ledger, rail, s = rig
    auth = _indeterminate(rig)
    s.clock = lambda: NOW + timedelta(seconds=s.reservation_ttl_seconds + 60)

    auth = s.reconcile(auth.auth_id)

    assert auth.state is AuthState.ABANDONED
    assert "remains payable" in " ".join(s.anomalies)
    assert ledger.available(MANDATE) == BUDGET
    ledger.check_invariant(MANDATE)


def test_a_late_capture_on_an_abandoned_authorization_is_refunded(rig):
    """The compensating control that makes the release safe. Money moved with no
    live reservation behind it, so it is handed back rather than absorbed."""
    ledger, rail, s = rig
    auth = _indeterminate(rig)
    s.clock = lambda: NOW + timedelta(seconds=s.reservation_ttl_seconds + 60)
    auth = s.reconcile(auth.auth_id)
    assert auth.state is AuthState.ABANDONED

    payment = rail.pay(auth.order_id)          # someone pays the stale link
    auth = deliver(rig, "payment.captured", payment)

    assert auth.state is AuthState.ABANDONED, "a terminal state is not reopened"
    assert ledger.snapshot(MANDATE).settled_minor == 0, "no budget is consumed"
    assert any("late capture on abandoned" in a for a in s.anomalies)
    assert rail.refunds, "the late capture must be refunded"
    ledger.check_invariant(MANDATE)


def test_a_paid_order_still_settles_on_reconcile(rig):
    """The TTL check must not shadow the case that actually matters."""
    ledger, rail, s = rig
    auth = _indeterminate(rig, "aut_p")
    rail.pay(auth.order_id)

    auth = s.reconcile("aut_p")

    assert auth.state is AuthState.SETTLED
    assert ledger.snapshot(MANDATE).settled_minor == AMOUNT
    ledger.check_invariant(MANDATE)


def test_reconcile_does_not_raise_when_the_reservation_is_already_gone(rig):
    """The recovery path must be the last thing to crash. Found by the demo:
    an escalated authorization has no reservation, and reconcile released
    unconditionally."""
    ledger, rail, s = rig
    s.clock = lambda: NOW
    auth = Authorization("aut_none", MANDATE, "cs_none", AMOUNT, MERCHANT)
    auth.reserved_at = NOW
    auth.to(AuthState.INDETERMINATE, "never reserved")
    s.authorizations["aut_none"] = auth

    auth = s.reconcile("aut_none")           # must not raise

    assert auth.state is AuthState.FAILED
    assert any("nothing held to release" in a for a in s.anomalies)
    ledger.check_invariant(MANDATE)


def test_a_double_release_is_reported_not_raised(rig):
    """Two paths can reach the same authorization after a crash."""
    ledger, rail, s = rig
    auth = start(rig, auth_id="aut_dbl")
    rail.fail_next = True
    payment = rail.pay(auth.order_id)
    deliver(rig, "payment.failed", payment, event_id="e1")
    assert ledger.available(MANDATE) == BUDGET

    released_again = s._release(auth, "duplicate path")
    assert released_again is False
    assert ledger.available(MANDATE) == BUDGET, "budget must not be credited twice"
    ledger.check_invariant(MANDATE)
