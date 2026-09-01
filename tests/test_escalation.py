"""Escalation budget (PRD 7.7, attack A8).

The property: an attacker cannot spend an unlimited amount of the principal's
attention, and a prompt that cannot be shown refuses rather than approves.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from spendgate import AuthorizationRequest, Outcome
from spendgate.escalation import EscalationBudget

NOW = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)
P = "usr_8823"


# ------------------------------------------------------------ the budget
def test_pending_cap_blocks_further_prompts():
    b = EscalationBudget(max_pending=3, max_per_window=99)
    for i in range(3):
        assert b.check(P, NOW)[0] is True
        b.raise_prompt(P, f"aut_{i}", NOW)
    ok, why = b.check(P, NOW)
    assert ok is False and "already waiting on you" in why


def test_window_cap_blocks_further_prompts():
    b = EscalationBudget(max_pending=99, max_per_window=5, window_seconds=3600)
    for i in range(5):
        b.raise_prompt(P, f"aut_{i}", NOW)
    ok, why = b.check(P, NOW)
    assert ok is False and "in the last 60 minutes" in why


def test_answering_frees_a_pending_slot():
    b = EscalationBudget(max_pending=2, max_per_window=99)
    b.raise_prompt(P, "a1", NOW)
    b.raise_prompt(P, "a2", NOW)
    assert b.check(P, NOW)[0] is False
    b.resolve(P, "a1")
    assert b.check(P, NOW)[0] is True


def test_answering_does_not_refund_the_window_count():
    """Otherwise answering quickly becomes a way to buy unlimited prompts, and
    the attacker just needs a cooperative victim."""
    b = EscalationBudget(max_pending=99, max_per_window=3, window_seconds=3600)
    for i in range(3):
        b.raise_prompt(P, f"a{i}", NOW)
        b.resolve(P, f"a{i}")
    assert b.pending(P) == 0
    assert b.check(P, NOW)[0] is False, "attention was spent either way"


def test_the_window_rolls_forward():
    b = EscalationBudget(max_pending=99, max_per_window=2, window_seconds=3600)
    b.raise_prompt(P, "a1", NOW)
    b.raise_prompt(P, "a2", NOW)
    assert b.check(P, NOW)[0] is False
    assert b.check(P, NOW + timedelta(seconds=3601))[0] is True


def test_budgets_are_per_principal():
    b = EscalationBudget(max_pending=1, max_per_window=1)
    b.raise_prompt("usr_a", "a1", NOW)
    assert b.check("usr_a", NOW)[0] is False
    assert b.check("usr_b", NOW)[0] is True, "one principal cannot exhaust another"


# ------------------------------------------------------- through the gate
@pytest.fixture
def gate():
    from test_service import build
    return build(seed_merchant=False)      # every purchase is a first-seen merchant


def _ask(g):
    return g.authorize(AuthorizationRequest("mnd_01J9F2K7", "cs_8fK2mNp", "agt_shopper_01"))


def test_flooding_the_principal_is_refused_not_approved(gate):
    """The whole point. Fail closed: an unshowable prompt is not consent."""
    outcomes = [_ask(gate)[1] for _ in range(7)]
    assert [d.outcome for d in outcomes[:3]] == [Outcome.ESCALATED] * 3
    assert all(d.outcome is Outcome.DENIED for d in outcomes[3:])
    assert all(d.reason_code == "escalation_budget_exhausted" for d in outcomes[3:])
    assert not any(d.outcome is Outcome.APPROVED for d in outcomes), \
        "no request may be approved because the prompt could not be raised"


def test_a_refused_escalation_holds_no_budget(gate):
    for _ in range(7):
        _ask(gate)
    assert gate.ledger.snapshot("mnd_01J9F2K7").reserved_minor == 0
    gate.ledger.check_invariant("mnd_01J9F2K7")


def test_the_refusal_still_says_what_the_original_question_was(gate):
    """A person reading the log needs to know what they were not asked."""
    for _ in range(4):
        _, d = _ask(gate)
    assert d.reason_code == "escalation_budget_exhausted"
    assert "First purchase from" in d.reason_text


def test_answering_lets_the_next_prompt_through(gate):
    ids = []
    for _ in range(3):
        auth_id, d = _ask(gate)
        ids.append(auth_id)
    assert _ask(gate)[1].reason_code == "escalation_budget_exhausted"

    gate.resolve_escalation("mnd_01J9F2K7", ids[0])
    assert _ask(gate)[1].outcome is Outcome.ESCALATED


def test_an_exhausted_budget_never_downgrades_a_hard_rail(gate):
    """R38 must not turn a refusal into something softer."""
    from test_service import make_facts
    from spendgate import rupees

    for _ in range(4):
        _ask(gate)
    gate.resolver.sessions["cs_big"] = make_facts(checkout_session_id="cs_big",
                                                  total_minor=rupees(9_000))
    _, d = gate.authorize(AuthorizationRequest("mnd_01J9F2K7", "cs_big", "agt_shopper_01"))
    assert d.outcome is Outcome.DENIED
    assert d.rule_id == "R17", "the rail rule fires first, as it always did"
