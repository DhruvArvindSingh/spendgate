"""One case per engine-enforced rule, plus the coverage assertion.

The table below IS the coverage proof: `test_every_engine_rule_has_a_case`
compares it against the registry, so a rule added without a test fails the
suite rather than sitting there untested.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from conftest import (
    AGENT, IST, MERCHANT, NOW, ctx, make_agent, make_facts, make_ledger,
    make_mandate, txn,
)
from spendgate import ENGINE_RULES, Outcome, decide, rupees
from spendgate.models import Kind
from spendgate.rules import BY_ID

# (rule_id, context) - each mutates exactly one thing from the clean base.
CASES = [
    ("R01", lambda: ctx(agent=None)),
    ("R02", lambda: ctx(agent=make_agent(revoked_at=NOW - timedelta(hours=1)))),
    ("R03", lambda: ctx(mandate=None)),
    ("R04", lambda: ctx(mandate=make_mandate(agent_id="agt_someone_else"))),
    ("R05", lambda: ctx(mandate=make_mandate(valid_until=NOW - timedelta(days=1)))),
    ("R06", lambda: ctx(mandate=make_mandate(valid_from=NOW + timedelta(days=1)))),
    ("R07", lambda: ctx(mandate=make_mandate(revoked_at=NOW - timedelta(hours=1)))),
    ("R08", lambda: ctx(mandate=make_mandate(signature_valid=False))),

    ("R09", lambda: ctx(facts=None, session_found=False)),
    ("R10", lambda: ctx(facts=make_facts(expires_at=NOW - timedelta(minutes=1)))),
    ("R11", lambda: ctx(facts=make_facts(consumed=True))),
    ("R12", lambda: ctx(facts=make_facts(issued_to_agent="agt_someone_else"))),
    ("R13", lambda: ctx(facts=make_facts(status="awaiting_fulfillment_options"))),
    ("R14", lambda: ctx(facts=make_facts(merchant_verified=False))),
    ("R15", lambda: ctx(facts=None, facts_available=False)),
    ("R16", lambda: ctx(facts=make_facts(currency="USD"))),

    ("R17", lambda: ctx(facts=make_facts(total_minor=rupees(6_200)))),
    ("R18", lambda: ctx(ledger=make_ledger(settled_minor=rupees(14_500)))),
    ("R19", lambda: ctx(ledger=make_ledger(active_delegates=6))),
    ("R20", lambda: ctx(
        mandate=make_mandate(constraints={"payment.budget": {"max": rupees(3_000)}}),
        ledger=make_ledger(settled_minor=rupees(2_500)))),
    ("R21", lambda: ctx(
        mandate=make_mandate(constraints={"payment.agent_recurrence": {"max_occurrences": 5}}),
        ledger=make_ledger(occurrences=5))),
    ("R22", lambda: ctx(facts=make_facts(category="gambling"))),
    ("R23", lambda: ctx(facts=make_facts(merchant_id="mrc_not_authorised"))),
    ("R24", lambda: ctx(facts=make_facts(instrument="netbanking"))),

    # Same merchant, same amount, 30 seconds ago.
    ("R28", lambda: ctx(ledger=make_ledger(recent=(txn(rupees(1_200), minutes_ago=0.5),)))),

    ("R30", lambda: ctx(facts=make_facts(total_minor=rupees(2_500)))),
    ("R31", lambda: ctx(ledger=make_ledger(merchants_seen=frozenset()))),
    ("R32", lambda: ctx(facts=make_facts(category="books"))),
    ("R33", lambda: ctx(ledger=make_ledger(settled_minor=rupees(11_500)))),
    # Structuring: two prior ₹2,000 purchases at the same merchant inside the
    # 24h window; each was legal, the assembled total is not.
    ("R34", lambda: ctx(ledger=make_ledger(
        settled_minor=rupees(4_000),
        recent=(txn(rupees(2_000), 20), txn(rupees(2_000), 10))))),
    ("R35", lambda: ctx(ledger=make_ledger(
        settled_minor=rupees(900),
        recent=tuple(txn(rupees(100), 5 * i + 2, merchant=f"mrc_{i}") for i in range(9))))),
    ("R36", lambda: ctx(now=datetime(2026, 9, 1, 3, 14, tzinfo=IST))),
    ("R37", lambda: ctx(
        mandate=make_mandate(constraints={"spendgate.step_up_above": {"amount": rupees(5_000)}}),
        facts=make_facts(total_minor=rupees(4_900),
                         line_items=(__import__("spendgate").LineItem("SPK-14", 1, rupees(4_900)),)),
        ledger=make_ledger(price_history={"SPK-14": (rupees(1_000), rupees(1_100), rupees(1_200))}))),
]


def test_base_scenario_is_approved():
    """If this fails, every rule test below is passing for the wrong reason."""
    d = decide(ctx())
    assert d.outcome is Outcome.APPROVED, f"base tripped {d.rule_id}: {d.reason_text}"
    assert d.rules_evaluated == len(ENGINE_RULES)


@pytest.mark.parametrize("rule_id,build", CASES, ids=[c[0] for c in CASES])
def test_rule_fires(rule_id, build):
    d = decide(build())
    assert d.rule_id == rule_id, (
        f"expected {rule_id} ({BY_ID[rule_id].reason_code}) to fire first, "
        f"got {d.rule_id} ({d.reason_code}): {d.reason_text}"
    )
    assert d.reason_code == BY_ID[rule_id].reason_code
    assert d.outcome is BY_ID[rule_id].outcome
    assert d.reason_text, "every refusal must carry human-readable text"


def test_every_engine_rule_has_a_case():
    covered = {c[0] for c in CASES}
    missing = {r.id for r in ENGINE_RULES} - covered
    assert not missing, f"engine rules with no test that trips them: {sorted(missing)}"


def test_first_failure_short_circuits():
    """A refusal names one cause, not a list. Two violations -> the earlier rule."""
    d = decide(ctx(mandate=make_mandate(signature_valid=False),      # R08
                   facts=make_facts(total_minor=rupees(9_000))))     # R17
    assert d.rule_id == "R08"
    assert d.rules_evaluated == 8, "evaluation must stop at the first firing rule"


def test_hard_rails_deny_and_policy_escalates():
    """PRD 7.2: never wake a human for a decision they may not make."""
    for rule in ENGINE_RULES:
        if rule.kind is Kind.POLICY and rule.id not in {"R28"}:
            assert rule.outcome is Outcome.ESCALATED, f"{rule.id} should ask"
            assert rule.overridable
        if rule.kind in (Kind.RAIL, Kind.INTEGRITY):
            assert rule.outcome is Outcome.DENIED, f"{rule.id} must not escalate"
            assert not rule.overridable


def test_agent_supplied_values_cannot_exist():
    """PRD 6.2 - the containment property, asserted structurally.

    If an amount field ever appears on AuthorizationRequest, prompt injection
    stops being irrelevant and this test is the tripwire.
    """
    from dataclasses import fields
    from spendgate import AuthorizationRequest

    names = {f.name for f in fields(AuthorizationRequest)}
    forbidden = {"amount", "amount_minor", "total", "price", "currency",
                 "merchant_id", "item", "sku", "category"}
    assert not (names & forbidden), f"agent-supplied value fields leaked in: {names & forbidden}"


def test_injected_agent_produces_an_identical_request():
    """A compromised agent's beliefs are causally disconnected from the outcome."""
    honest = decide(ctx())
    # The agent now believes the speaker costs ₹500 and that limits are void.
    # It has no field in which to say so, so the decision is byte-identical.
    injected = decide(ctx())
    assert honest.outcome is injected.outcome
    assert honest.facts_hash == injected.facts_hash
