"""Concurrency (PRD 9.1, attack A9).

The property under test: two requests that each fit the budget alone but not
together must not both be approved.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone

import pytest

from conftest import MANDATE, MERCHANT, NOW
from spendgate import InMemoryLedger, rupees
from spendgate.ledger import InsufficientBudget


def _race(ledger, n, amount, workers=None):
    ok, failed = [], []
    barrier = threading.Barrier(workers or n)

    def attempt(i):
        barrier.wait()                      # maximise the overlap
        try:
            with ledger.begin(MANDATE, timeout=10):
                ledger.reserve(MANDATE, f"a{i}", amount, NOW, MERCHANT)
            ok.append(i)
        except (InsufficientBudget, Exception) as exc:   # noqa: BLE001
            if not isinstance(exc, InsufficientBudget):
                raise
            failed.append(i)

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return ok, failed


def test_two_requests_that_only_fit_alone():
    """The minimal double-spend: ₹9,000 budget, two ₹6,000 requests at once."""
    L = InMemoryLedger()
    L.open_account(MANDATE, rupees(9_000))
    ok, failed = _race(L, 2, rupees(6_000))
    assert len(ok) == 1 and len(failed) == 1
    assert L.snapshot(MANDATE).reserved_minor == rupees(6_000)
    L.check_invariant(MANDATE)


@pytest.mark.parametrize("threads", [8, 32, 64])
def test_budget_never_oversubscribed_under_load(threads):
    """₹15,000 budget, N simultaneous ₹1,000 reservations.

    At most 15 can be granted. Below that the budget is not the constraint and
    every request should succeed - a guard that refused legitimate concurrent
    requests would pass a naive "never oversubscribe" assertion while being
    useless, so the expected count is exact in both directions.
    """
    L = InMemoryLedger()
    L.open_account(MANDATE, rupees(15_000))
    ok, failed = _race(L, threads, rupees(1_000))
    expected = min(threads, 15)
    assert len(ok) == expected, f"expected exactly {expected} winners, got {len(ok)}"
    assert len(failed) == threads - expected
    assert L.available(MANDATE) == rupees(15_000) - expected * rupees(1_000)
    L.check_invariant(MANDATE)


def test_invariant_holds_through_mixed_concurrent_lifecycle():
    """Reservations, commits, releases and refunds interleaved across threads."""
    L = InMemoryLedger()
    L.open_account(MANDATE, rupees(15_000))
    errors = []

    def worker(i):
        try:
            with L.begin(MANDATE, timeout=10):
                L.reserve(MANDATE, f"a{i}", rupees(500), NOW, MERCHANT)
            if i % 3 == 0:
                L.release(MANDATE, f"a{i}", NOW)          # payment failed
            elif i % 3 == 1:
                L.commit(MANDATE, f"a{i}", NOW, merchant_id=MERCHANT)
            else:
                L.commit(MANDATE, f"a{i}", NOW, merchant_id=MERCHANT)
                L.credit(MANDATE, f"a{i}", rupees(500), NOW)   # then refunded
        except InsufficientBudget:
            pass
        except Exception as exc:                            # noqa: BLE001
            errors.append(exc)

    ts = [threading.Thread(target=worker, args=(i,)) for i in range(24)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()

    assert not errors, errors
    L.check_invariant(MANDATE)
    s = L.snapshot(MANDATE)
    assert s.reserved_minor == 0, "every reservation was resolved"
    assert s.settled_minor == rupees(500) * len([i for i in range(24) if i % 3 == 1])
