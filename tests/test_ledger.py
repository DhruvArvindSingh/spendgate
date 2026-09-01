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


# ------------------------------------------------- tamper evidence (mutation)
def test_a_repaired_chain_defeats_internal_verification():
    """The uncomfortable one. A hash chain alone is NOT tamper-evident: an
    attacker who rewrites the log can recompute every hash and repair every
    prev_hash, and verify_chain will happily pass it.

    This test exists to document that honestly, so the claim is not overstated.
    """
    import dataclasses

    L = InMemoryLedger()
    L.open_account(MANDATE, rupees(15_000))
    for i in range(3):
        L.reserve(MANDATE, f"a{i}", rupees(1_000), NOW, MERCHANT)
        L.commit(MANDATE, f"a{i}", NOW, merchant_id=MERCHANT)

    entries = L._acct(MANDATE).entries
    entries[1] = dataclasses.replace(entries[1], amount_minor=rupees(1))
    assert L.verify_chain(MANDATE)[0] is False, "a naive edit is caught"

    for i in range(1, len(entries)):
        entries[i] = dataclasses.replace(entries[i], prev_hash=entries[i - 1].hash)
    assert L.verify_chain(MANDATE)[0] is True, (
        "a repaired chain passes internal verification — this is why an "
        "external anchor is required, not optional"
    )


def test_an_anchor_catches_the_repaired_chain():
    """The property people mean by "tamper-evident": the head hash is held
    somewhere the rewrite cannot reach."""
    import dataclasses

    from spendgate.ledger import InMemoryAnchor

    anchor = InMemoryAnchor()
    L = InMemoryLedger(anchor=anchor)
    L.open_account(MANDATE, rupees(15_000))
    for i in range(3):
        L.reserve(MANDATE, f"a{i}", rupees(1_000), NOW, MERCHANT)
        L.commit(MANDATE, f"a{i}", NOW, merchant_id=MERCHANT)
    assert L.verify_against_anchor(MANDATE)[0] is True

    entries = L._acct(MANDATE).entries
    entries[1] = dataclasses.replace(entries[1], amount_minor=rupees(1))
    for i in range(1, len(entries)):
        entries[i] = dataclasses.replace(entries[i], prev_hash=entries[i - 1].hash)

    ok, why = L.verify_against_anchor(MANDATE)
    assert ok is False and "head mismatch" in why


def test_without_an_anchor_the_ledger_says_so():
    """Silence would imply a guarantee that is not being provided."""
    L = InMemoryLedger()
    L.open_account(MANDATE, rupees(15_000))
    ok, why = L.verify_against_anchor(MANDATE)
    assert ok is False and "no anchor" in why


def test_file_anchor_survives_a_new_ledger_object():
    """An anchor that lives in the same object it protects is not an anchor."""
    import tempfile
    from pathlib import Path

    from spendgate.ledger import FileAnchor

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "anchor.log"
        L1 = InMemoryLedger(anchor=FileAnchor(path))
        L1.open_account(MANDATE, rupees(15_000))
        L1.reserve(MANDATE, "a1", rupees(1_000), NOW, MERCHANT)
        L1.commit(MANDATE, "a1", NOW, merchant_id=MERCHANT)
        head = FileAnchor(path).head(MANDATE)

        assert head is not None and head[0] == 2
        assert head[1] == L1.entries(MANDATE)[-1].hash


def test_check_invariant_fails_on_a_repaired_chain_when_anchored():
    """The invariant is the single assertion everything else leans on, so it
    must use the strongest check available rather than the convenient one."""
    import dataclasses

    import pytest

    from spendgate.ledger import InMemoryAnchor

    L = InMemoryLedger(anchor=InMemoryAnchor())
    L.open_account(MANDATE, rupees(15_000))
    L.reserve(MANDATE, "a1", rupees(1_000), NOW, MERCHANT)
    L.commit(MANDATE, "a1", NOW, merchant_id=MERCHANT)
    L.check_invariant(MANDATE)

    entries = L._acct(MANDATE).entries
    entries[0] = dataclasses.replace(entries[0], amount_minor=rupees(1))
    for i in range(1, len(entries)):
        entries[i] = dataclasses.replace(entries[i], prev_hash=entries[i - 1].hash)

    with pytest.raises(AssertionError, match="diverged from its anchor"):
        L.check_invariant(MANDATE)
