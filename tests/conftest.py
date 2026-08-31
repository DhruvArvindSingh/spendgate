"""Scenario builders.

The base scenario is deliberately clean: it must return APPROVED. Every rule
test then mutates exactly one thing and asserts that rule fires first. If the
base ever starts tripping a rule, `test_base_scenario_is_approved` fails loudly
rather than letting every other test pass for the wrong reason.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from spendgate import (
    AgentRecord, AuthorizationRequest, Constraint, Context, LedgerSnapshot,
    LineItem, Mandate, ResolvedFacts, SettledTxn, rupees,
)

IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 9, 1, 14, 0, tzinfo=IST)      # a quiet, ordinary afternoon

PRINCIPAL = "usr_8823"
AGENT = "agt_shopper_01"
MANDATE = "mnd_01J9F2K7"
MERCHANT = "mrc_lumen"
SESSION = "cs_8fK2mNp"


def base_constraints() -> tuple[Constraint, ...]:
    return (
        Constraint("payment.budget", {"max": rupees(15_000), "currency": "INR"}),
        Constraint("payment.amount_range", {"min": 0, "max": rupees(5_000), "currency": "INR"}),
        Constraint("payment.agent_recurrence", {"frequency": "MONTHLY", "max_occurrences": 40}),
        Constraint("payment.allowed_payees", {"allowed": [MERCHANT, "mrc_kirana"]}),
        Constraint("payment.allowed_payment_instruments", {"allowed": ["upi", "card"]}),
        Constraint("spendgate.allowed_categories", {"allowed": ["grocery", "household", "electronics"]}),
        Constraint("spendgate.velocity", {"max_count": 10, "window_seconds": 3600}),
        Constraint("spendgate.aggregate", {"max_amount": rupees(5_000), "window_seconds": 86400,
                                           "group_by": "merchant_id"}),
        Constraint("spendgate.step_up_above", {"amount": rupees(2_000)}),
        Constraint("spendgate.quiet_hours", {"not_between": ["23:00", "07:00"], "tz": "Asia/Kolkata"}),
        Constraint("spendgate.price_anomaly", {"factor": 2.0, "min_observations": 3}),
    )


def make_mandate(**over) -> Mandate:
    kw = dict(
        mandate_id=MANDATE, principal_id=PRINCIPAL, agent_id=AGENT,
        rail_profile="upi_circle.v1", constraints=base_constraints(),
        issued_at=NOW - timedelta(days=1),
        valid_from=NOW - timedelta(days=1), valid_until=NOW + timedelta(days=29),
    )
    if "constraints" in over and isinstance(over["constraints"], dict):
        # convenience: {"type": {...params}} replaces or adds that constraint
        patch = over.pop("constraints")
        merged = {c.type: c for c in kw["constraints"]}
        for t, p in patch.items():
            merged[t] = None if p is None else Constraint(t, p)
        kw["constraints"] = tuple(c for c in merged.values() if c is not None)
    kw.update(over)
    return Mandate(**kw)


def make_facts(**over) -> ResolvedFacts:
    kw = dict(
        checkout_session_id=SESSION, merchant_id=MERCHANT, merchant_verified=True,
        status="ready_for_payment", currency="INR", total_minor=rupees(1_200),
        category="grocery", issued_to_agent=AGENT,
        expires_at=NOW + timedelta(minutes=8), resolved_at=NOW,
        line_items=(LineItem("SPK-14", 1, rupees(1_200)),), instrument="upi",
    )
    kw.update(over)
    return ResolvedFacts(**kw)


def make_ledger(**over) -> LedgerSnapshot:
    kw = dict(settled_minor=0, reserved_minor=0, occurrences=0, recent=(),
              merchants_seen=frozenset({MERCHANT}), price_history={}, active_delegates=1)
    kw.update(over)
    return LedgerSnapshot(**kw)


def make_agent(**over) -> AgentRecord:
    kw = dict(agent_id=AGENT, principal_id=PRINCIPAL, registered=True, revoked_at=None)
    kw.update(over)
    return AgentRecord(**kw)


def make_request(**over) -> AuthorizationRequest:
    kw = dict(mandate_id=MANDATE, checkout_session_id=SESSION, agent_id=AGENT)
    kw.update(over)
    return AuthorizationRequest(**kw)


def ctx(**over) -> Context:
    """Build a Context. Pass mandate=/facts=/ledger=/agent=/request=/now= to override."""
    kw = dict(request=make_request(), now=NOW, mandate=make_mandate(),
              facts=make_facts(), agent=make_agent(), ledger=make_ledger(),
              facts_available=True, session_found=True)
    kw.update(over)
    return Context(**kw)


def txn(amount, minutes_ago=10, merchant=MERCHANT, sku=None) -> SettledTxn:
    return SettledTxn(merchant, amount, NOW - timedelta(minutes=minutes_ago), sku)


@pytest.fixture
def now() -> datetime:
    return NOW
