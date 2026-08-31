"""The whole stack: agent -> merchant (HTTP) -> resolver -> engine -> ledger
-> rail -> webhook -> ledger.

Everything except the rail is real here; the rail is FakeRazorpay because live
test-mode keys are not committed. Every boundary the design depends on is
crossed for real, including the socket the price travels over.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from spendgate import (
    AgentRecord, AuthorizationRequest, Constraint, InMemoryLedger, Mandate,
    Outcome, SpendGate, rupees,
)
from spendgate.acp import AcpFactResolver
from spendgate.merchant import MERCHANT_ID, serve
from spendgate.rail import FakeRazorpay
from spendgate.settlement import AuthState, Authorization, Settlement
from spendgate.webhooks import EventDeduplicator, receive, sign

AGENT, MANDATE, SECRET = "agt_shopper_01", "mnd_e2e", "whsec_test"


@pytest.fixture
def stack():
    """Yields (url, merchant_state, gate, rail, settlement, clock).

    `clock` is a mutable dict so a test can advance SpendGate's notion of time
    without waiting. Sessions still carry the merchant's real-time expiry, so
    advancing beyond the 10-minute TTL would (correctly) trip R10.
    """
    with serve() as (url, mstate):
        ledger = InMemoryLedger()
        ledger.open_account(MANDATE, rupees(15_000))
        now = datetime.now(timezone.utc)
        # A prior settled purchase so the merchant is not first-seen (R31),
        # placed two hours back so it falls OUTSIDE the one-hour aggregate
        # window and does not inflate the structuring totals under test.
        earlier = now - timedelta(hours=2)
        ledger.reserve(MANDATE, "seed", rupees(500), earlier, MERCHANT_ID)
        ledger.commit(MANDATE, "seed", earlier, merchant_id=MERCHANT_ID)

        gate = SpendGate(
            ledger=ledger,
            resolver=AcpFactResolver(url, AGENT, mstate.secret),
            mandates={MANDATE: Mandate(
                mandate_id=MANDATE, principal_id="usr_1", agent_id=AGENT,
                rail_profile="upi_circle.v1", issued_at=now - timedelta(days=1),
                valid_from=now - timedelta(days=1), valid_until=now + timedelta(days=29),
                constraints=(
                    Constraint("payment.budget", {"max": rupees(15_000), "currency": "INR"}),
                    Constraint("payment.allowed_payees", {"allowed": [MERCHANT_ID]}),
                    Constraint("spendgate.aggregate", {"max_amount": rupees(5_000),
                                                       "window_seconds": 3600,
                                                       "group_by": "merchant_id"}),
                ),
            )},
            agents={AGENT: AgentRecord(AGENT, "usr_1")},
        )
        clock = {"t": now}
        gate.clock = lambda: clock["t"]
        rail = FakeRazorpay()
        yield url, mstate, gate, rail, Settlement(ledger=ledger, rail=rail), clock


def quote(url, sku, qty=1, key=None):
    r = httpx.post(f"{url}/checkout_sessions", json={"items": [{"id": sku, "quantity": qty}]},
                   headers={"Authorization": f"Bearer {AGENT}", "API-Version": "2026-04-17",
                            "Idempotency-Key": key or f"k-{sku}-{qty}"})
    r.raise_for_status()
    return r.json()["id"]


def pay_and_notify(rail, settle, auth, event="payment.captured", fail=False):
    rail.fail_next = fail
    payment = rail.pay(auth.order_id)
    body = json.dumps(rail.webhook_body(event, payment)).encode()
    parsed = receive(body, {"X-Razorpay-Signature": sign(body, SECRET),
                            "x-razorpay-event-id": f"evt_{payment['id']}"},
                     SECRET, EventDeduplicator())
    return settle.on_event(parsed)


def buy(stack, sku, key=None):
    url, _, gate, rail, settle, clock = stack
    sid = quote(url, sku, key=key)
    auth_id, decision = gate.authorize(AuthorizationRequest(MANDATE, sid, AGENT))
    return sid, auth_id, decision


def test_ordinary_purchase_settles(stack):
    url, _, gate, rail, settle, clock = stack
    sid, auth_id, d = buy(stack, "SPK-14")
    assert d.outcome is Outcome.APPROVED, d.reason_text

    auth = settle.execute(Authorization(f"{MANDATE}:{sid}", MANDATE, sid,
                                        d.amount_minor, MERCHANT_ID, sku="SPK-14"))
    auth = pay_and_notify(rail, settle, auth)

    assert auth.state is AuthState.SETTLED
    s = gate.ledger.snapshot(MANDATE)
    assert s.settled_minor == rupees(500) + rupees(1_200)
    assert s.reserved_minor == 0
    gate.ledger.check_invariant(MANDATE)


def test_injected_agent_moves_no_money_through_the_whole_stack(stack):
    """The end-to-end form of A1: hostile copy, real merchant, real socket,
    real engine. Nothing reaches the rail."""
    url, _, gate, rail, settle, clock = stack
    sid, _, d = buy(stack, "TV-99")

    assert d.outcome is Outcome.DENIED
    assert d.amount_minor == rupees(40_000)
    assert gate.ledger.snapshot(MANDATE).reserved_minor == 0
    assert rail.orders == {}, "a refused decision must never reach the rail"
    gate.ledger.check_invariant(MANDATE)


def test_failed_payment_frees_budget_for_the_next_purchase(stack):
    url, _, gate, rail, settle, clock = stack
    before = gate.ledger.available(MANDATE)

    sid, _, d = buy(stack, "HP-77")
    auth = settle.execute(Authorization(f"{MANDATE}:{sid}", MANDATE, sid,
                                        d.amount_minor, MERCHANT_ID))
    auth = pay_and_notify(rail, settle, auth, event="payment.failed", fail=True)

    assert auth.state is AuthState.FAILED
    assert gate.ledger.available(MANDATE) == before, "budget must be spendable again"
    gate.ledger.check_invariant(MANDATE)


def test_structuring_is_caught_after_a_real_settlement(stack):
    """Two ₹4,000 splits, five minutes apart. The first settles through the
    rail; the second is escalated because the ledger now knows about the first."""
    url, _, gate, rail, settle, clock = stack

    sid1, _, d1 = buy(stack, "HP-77", key="split-1")
    assert d1.outcome is Outcome.APPROVED
    auth = settle.execute(Authorization(f"{MANDATE}:{sid1}", MANDATE, sid1,
                                        d1.amount_minor, MERCHANT_ID))
    assert pay_and_notify(rail, settle, auth).state is AuthState.SETTLED

    clock["t"] += timedelta(minutes=5)          # past the 60s duplicate window
    sid2, _, d2 = buy(stack, "HP-77", key="split-2")

    assert d2.outcome is Outcome.ESCALATED
    assert d2.reason_code == "aggregate_pattern"
    assert "8,000" in d2.reason_text, d2.reason_text
    assert len(rail.orders) == 1, "the escalated split must not reach the rail"
    gate.ledger.check_invariant(MANDATE)


def test_rapid_identical_splits_are_denied_as_duplicates_not_escalated(stack):
    """R28 shadows R34 when the splits are the same amount inside 60 seconds.

    Both are correct refusals, but they are not interchangeable: R28 denies
    (a same-amount repeat that fast is far more likely a non-idempotent retry
    than a deliberate purchase), while R34 escalates and shows the assembled
    pattern. Documented here so the difference is a decision, not a surprise.
    """
    url, _, gate, rail, settle, clock = stack

    sid1, _, d1 = buy(stack, "HP-77", key="rapid-1")
    assert d1.outcome is Outcome.APPROVED
    auth = settle.execute(Authorization(f"{MANDATE}:{sid1}", MANDATE, sid1,
                                        d1.amount_minor, MERCHANT_ID))
    pay_and_notify(rail, settle, auth)

    clock["t"] += timedelta(seconds=20)         # still inside the window
    _, _, d2 = buy(stack, "HP-77", key="rapid-2")

    assert d2.outcome is Outcome.DENIED
    assert d2.reason_code == "suspected_duplicate"
    assert len(rail.orders) == 1
    gate.ledger.check_invariant(MANDATE)


def test_prohibited_category_never_reaches_the_rail(stack):
    url, _, gate, rail, settle, clock = stack
    _, _, d = buy(stack, "BET-01")
    assert d.reason_code == "category_prohibited"
    assert rail.orders == {}


def test_replaying_a_completed_session_is_refused(stack):
    """A4. The merchant marks the session consumed on completion; a second
    authorization against it is refused by R11."""
    url, _, gate, rail, settle, clock = stack
    sid, _, d = buy(stack, "SPK-14")
    auth = settle.execute(Authorization(f"{MANDATE}:{sid}", MANDATE, sid,
                                        d.amount_minor, MERCHANT_ID))
    pay_and_notify(rail, settle, auth)
    gate.resolver.complete(sid, auth.payment_id)

    _, replay = gate.authorize(AuthorizationRequest(MANDATE, sid, AGENT))
    assert replay.reason_code == "session_already_used"
    gate.ledger.check_invariant(MANDATE)
