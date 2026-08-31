"""Ledger accounting and integrity (PRD 6.6, 8.1)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from conftest import MANDATE, MERCHANT, NOW
from spendgate import InMemoryLedger, rupees
from spendgate.ledger import EntryKind, InsufficientBudget


@pytest.fixture
def ledger():
    L = InMemoryLedger()
    L.open_account(MANDATE, rupees(15_000))
    return L


def test_reserve_then_commit_becomes_spend(ledger):
    ledger.reserve(MANDATE, "a1", rupees(1_200), NOW, MERCHANT)
    assert ledger.available(MANDATE) == rupees(13_800), "reservation must hold budget"
    ledger.commit(MANDATE, "a1", NOW, merchant_id=MERCHANT)
    s = ledger.snapshot(MANDATE)
    assert s.settled_minor == rupees(1_200) and s.reserved_minor == 0
    ledger.check_invariant(MANDATE)


def test_failed_payment_returns_the_budget(ledger):
    """The single most valuable line in the state machine.

    Without this, every failed payment silently eats budget and the agent
    starves on a mandate that still has money in it.
    """
    ledger.reserve(MANDATE, "a1", rupees(4_000), NOW, MERCHANT)
    ledger.release(MANDATE, "a1", NOW)
    assert ledger.available(MANDATE) == rupees(15_000)
    assert ledger.snapshot(MANDATE).settled_minor == 0
    ledger.check_invariant(MANDATE)


def test_indeterminate_payment_holds_its_reservation(ledger):
    """PRD 8.1: a payment whose outcome is UNKNOWN neither commits nor releases.

    Releasing it invites a double-spend when the original settles late;
    committing it invents a charge that never happened.
    """
    ledger.reserve(MANDATE, "a1", rupees(4_000), NOW, MERCHANT)
    # ... rail times out. Nothing is called. The reservation stands.
    assert ledger.available(MANDATE) == rupees(11_000)
    assert ledger.snapshot(MANDATE).reserved_minor == rupees(4_000)
    ledger.check_invariant(MANDATE)

    # The reconciler later finds it captured.
    ledger.commit(MANDATE, "a1", NOW + timedelta(minutes=3), merchant_id=MERCHANT)
    assert ledger.snapshot(MANDATE).settled_minor == rupees(4_000)
    ledger.check_invariant(MANDATE)


def test_refund_credits_budget_back(ledger):
    ledger.reserve(MANDATE, "a1", rupees(3_000), NOW, MERCHANT)
    ledger.commit(MANDATE, "a1", NOW, merchant_id=MERCHANT)
    ledger.credit(MANDATE, "a1", rupees(3_000), NOW + timedelta(days=1))
    assert ledger.available(MANDATE) == rupees(15_000)
    ledger.check_invariant(MANDATE)


def test_cannot_reserve_beyond_budget(ledger):
    ledger.reserve(MANDATE, "a1", rupees(14_000), NOW, MERCHANT)
    with pytest.raises(InsufficientBudget):
        ledger.reserve(MANDATE, "a2", rupees(2_000), NOW, MERCHANT)
    ledger.check_invariant(MANDATE)


def test_hash_chain_verifies(ledger):
    for i in range(5):
        ledger.reserve(MANDATE, f"a{i}", rupees(100), NOW, MERCHANT)
        ledger.commit(MANDATE, f"a{i}", NOW, merchant_id=MERCHANT)
    ok, bad = ledger.verify_chain(MANDATE)
    assert ok and bad is None
    assert len(ledger.entries(MANDATE)) == 10


def test_tampering_breaks_the_chain(ledger):
    """Rewriting history after the fact is detectable (PRD 13.1, A12)."""
    ledger.reserve(MANDATE, "a1", rupees(1_000), NOW, MERCHANT)
    ledger.commit(MANDATE, "a1", NOW, merchant_id=MERCHANT)
    ledger.reserve(MANDATE, "a2", rupees(2_000), NOW, MERCHANT)

    entries = ledger._acct(MANDATE).entries
    import dataclasses
    entries[1] = dataclasses.replace(entries[1], amount_minor=rupees(50))  # quietly reduce a charge

    ok, bad = ledger.verify_chain(MANDATE)
    assert not ok and bad == 3, "the entry after the edit must fail to link"


def test_approvals_are_logged_too(ledger):
    """An audit trail of only refusals cannot answer why a payment WAS allowed."""
    ledger.reserve(MANDATE, "a1", rupees(1_000), NOW, MERCHANT)
    ledger.commit(MANDATE, "a1", NOW, merchant_id=MERCHANT)
    kinds = [e.kind for e in ledger.entries(MANDATE)]
    assert kinds == [EntryKind.RESERVE, EntryKind.COMMIT]
