"""Service layer: idempotency, fail-closed resolution, and the structuring
attack end-to-end through the real ledger (PRD 9.2, 12.2 A3).
"""

from __future__ import annotations

import threading
from datetime import timedelta

import pytest

from conftest import AGENT, MANDATE, MERCHANT, NOW, make_agent, make_facts, make_mandate, make_request
from spendgate import (
    Constraint, InMemoryLedger, Outcome, ResolvedFacts, SpendGate, rupees,
)
from spendgate.service import FactsUnavailable


class StubResolver:
    """Stands in for the server-to-server ACP fetch. The agent is not in this path."""

    def __init__(self, sessions: dict[str, ResolvedFacts], unavailable: bool = False):
        self.sessions = sessions
        self.unavailable = unavailable
        self.calls: list[str] = []

    def resolve(self, checkout_session_id: str):
        self.calls.append(checkout_session_id)
        if self.unavailable:
            raise FactsUnavailable(checkout_session_id)
        return self.sessions.get(checkout_session_id)


def build(mandate=None, sessions=None, seed_merchant=True, **kw) -> SpendGate:
    mandate = mandate or make_mandate()
    L = InMemoryLedger()
    L.open_account(MANDATE, rupees(15_000))
    if seed_merchant:
        # A prior settled purchase, so these tests are not all shadowed by R31
        # (merchant_first_seen), which correctly fires on any brand-new payee.
        L.reserve(MANDATE, "seed", rupees(500), NOW - timedelta(hours=2), MERCHANT)
        L.commit(MANDATE, "seed", NOW - timedelta(hours=2), merchant_id=MERCHANT)
    clock = kw.pop("clock", lambda: NOW)
    return SpendGate(
        ledger=L,
        resolver=StubResolver(sessions if sessions is not None else {"cs_8fK2mNp": make_facts()}),
        mandates={mandate.mandate_id: mandate},
        agents={AGENT: make_agent()},
        clock=clock,
        **kw,
    )


# ---------------------------------------------------------------- happy path
def test_approval_reserves_budget_before_the_rail_is_called():
    gate = build()
    _, d = gate.authorize(make_request())
    assert d.outcome is Outcome.APPROVED
    assert gate.ledger.snapshot(MANDATE).reserved_minor == rupees(1_200)
    assert gate.ledger.snapshot(MANDATE).settled_minor == rupees(500)  # the seed
    gate.ledger.check_invariant(MANDATE)


def test_facts_are_fetched_from_the_merchant_not_the_request():
    gate = build()
    gate.authorize(make_request())
    assert gate.resolver.calls == ["cs_8fK2mNp"], "the price must come from the merchant"


# ------------------------------------------------------------- fail closed
def test_unreachable_merchant_denies_rather_than_guesses():
    """R15. Unavailable facts are indistinguishable from hostile ones."""
    gate = build()
    gate.resolver.unavailable = True
    _, d = gate.authorize(make_request())
    assert d.outcome is Outcome.DENIED and d.reason_code == "facts_unavailable"
    assert gate.ledger.snapshot(MANDATE).reserved_minor == 0


# ------------------------------------------------------------- idempotency
def test_replay_returns_the_stored_result(): 
    gate = build()
    req = make_request(idempotency_key="k-1")
    _, first = gate.authorize(req)
    _, second = gate.authorize(req)
    assert first.outcome is Outcome.APPROVED
    assert second.outcome is Outcome.REPLAYED
    assert gate.ledger.snapshot(MANDATE).reserved_minor == rupees(1_200), "must not double-reserve"


def test_same_key_different_body_conflicts():
    gate = build(sessions={"cs_8fK2mNp": make_facts(), "cs_other": make_facts(checkout_session_id="cs_other")})
    gate.authorize(make_request(idempotency_key="k-1"))
    _, d = gate.authorize(make_request(checkout_session_id="cs_other", idempotency_key="k-1"))
    assert d.reason_code == "idempotency_conflict"


def test_in_flight_key_is_rejected_with_retry():
    gate = build()
    gate.idempotency.begin(f"{AGENT}:POST /v1/authorizations", "k-1", "some-hash-still-running")
    # A second request with the same key but the same body hash would replay;
    # here the original is still marked in flight.
    from spendgate.service import _body_hash
    req = make_request(idempotency_key="k-1")
    gate.idempotency._d[(f"{AGENT}:POST /v1/authorizations", "k-1")].body_hash = _body_hash(req)
    _, d = gate.authorize(req)
    assert d.reason_code == "idempotency_in_flight"


def test_lock_contention_maps_to_a_retryable_refusal():
    """R29. The lock is never held across a network call, so this is rare - but
    it must refuse rather than proceed on a stale balance."""
    gate = build(lock_timeout=0.05)
    held = threading.Event()
    done = threading.Event()

    def hold():
        with gate.ledger.begin(MANDATE, timeout=5):
            held.set()
            done.wait(2)

    t = threading.Thread(target=hold)
    t.start()
    held.wait(2)
    _, d = gate.authorize(make_request())
    done.set()
    t.join()

    assert d.reason_code == "concurrent_budget_conflict"
    assert d.outcome is Outcome.DENIED


# ------------------------------------------------------- the headline attack
def test_structuring_is_caught_on_the_second_split():
    """₹5,000 per-transaction cap. The agent wants ₹8,000 of headphones and
    splits it into two ₹4,000 purchases, each individually legal.

    The aggregate rule assembles them and escalates - it does not refuse,
    because the principal may genuinely want the item (PRD 7.7).
    """
    mandate = make_mandate(constraints={
        "spendgate.step_up_above": None,      # not what is under test here
        "spendgate.velocity": None,
        "spendgate.aggregate": {"max_amount": rupees(5_000), "window_seconds": 86400,
                                "group_by": "merchant_id"},
    })
    clock = {"t": NOW}
    sessions = {f"cs_{i}": make_facts(checkout_session_id=f"cs_{i}", total_minor=rupees(4_000))
                for i in (1, 2)}
    # build() seeds a prior purchase, so this merchant is already known.
    gate = build(mandate=mandate, sessions=sessions, clock=lambda: clock["t"])

    _, first = gate.authorize(make_request(checkout_session_id="cs_1"))
    assert first.outcome is Outcome.APPROVED, first.reason_text
    gate.ledger.commit(MANDATE, f"{MANDATE}:cs_1", clock["t"], merchant_id=MERCHANT)

    clock["t"] = NOW + timedelta(minutes=5)          # past the 60s duplicate window
    _, second = gate.authorize(make_request(checkout_session_id="cs_2"))

    assert second.outcome is Outcome.ESCALATED
    assert second.reason_code == "aggregate_pattern"
    assert second.overridable, "the principal must be able to say yes"
    assert "8,500" in second.reason_text, second.reason_text
    assert gate.ledger.snapshot(MANDATE).settled_minor == rupees(4_500), \
        "only the first split settled; the second is waiting on a human"
    gate.ledger.check_invariant(MANDATE)


def test_first_purchase_from_a_new_merchant_asks_the_principal():
    """R31 on a genuinely cold ledger - the behaviour the seeding above hides."""
    gate = build(seed_merchant=False)
    _, d = gate.authorize(make_request())
    assert d.outcome is Outcome.ESCALATED
    assert d.reason_code == "merchant_first_seen"
    assert gate.ledger.snapshot(MANDATE).reserved_minor == 0, \
        "an escalated request holds no budget until the principal answers"
