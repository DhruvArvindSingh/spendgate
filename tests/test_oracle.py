"""The adjudicator (PRD 14.3).

Every number in the evaluation comes from this file, so it gets tested directly
rather than trusted. It deliberately shares no code with the rule engine.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evaluation.oracle import Charge, adjudicate  # noqa: E402
from spendgate import Constraint, Mandate, rupees  # noqa: E402

AGENT, MERCHANT = "agt_shopper_01", "mrc_lumen"
T = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)
RAIL_TXN, RAIL_PERIOD = rupees(5_000), rupees(15_000)
PROHIBITED = {"gambling", "crypto", "adult"}


def mandate(**patch) -> Mandate:
    base = {
        "payment.budget": {"max": rupees(15_000)},
        "payment.amount_range": {"max": rupees(5_000)},
        "payment.allowed_payees": {"allowed": [MERCHANT]},
        "spendgate.allowed_categories": {"allowed": ["grocery", "electronics"]},
        "spendgate.aggregate": {"max_amount": rupees(5_000), "window_seconds": 3600},
    }
    base.update(patch)
    return Mandate(
        mandate_id="m", principal_id="p", agent_id=AGENT, rail_profile="upi_circle.v1",
        constraints=tuple(Constraint(t, v) for t, v in base.items() if v is not None),
        issued_at=T,
    )


def judge(charges, m=None):
    return adjudicate(m or mandate(), RAIL_TXN, RAIL_PERIOD, PROHIBITED, charges, AGENT)


def charge(amount, minutes=0, category="grocery", merchant=MERCHANT,
           session=None, agent=AGENT) -> Charge:
    return Charge(T + timedelta(minutes=minutes), merchant, amount, category,
                  session or f"cs_{minutes}_{amount}", agent)


def test_a_compliant_purchase_is_clean():
    assert judge([charge(rupees(1_200))]).clean


def test_over_the_per_transaction_cap():
    v = judge([charge(rupees(6_000))])
    assert v.unauthorized_minor == rupees(6_000), "the whole charge, not the excess"
    assert "over per-txn cap" in v.violations[0]


def test_over_the_period_cap():
    charges = [charge(rupees(4_000), minutes=i * 120, session=f"cs{i}") for i in range(5)]
    v = judge(charges)
    assert v.unauthorized_minor > 0
    assert any("period cap" in x for x in v.violations)


def test_structuring_is_caught_by_the_aggregate_window():
    """Three ₹2,000 charges in one hour: each legal, the total is not."""
    charges = [charge(rupees(2_000), minutes=m, session=f"cs{m}") for m in (0, 20, 40)]
    v = judge(charges)
    assert not v.clean
    assert any("aggregate" in x for x in v.violations)


def test_the_same_charges_spread_beyond_the_window_are_clean():
    """The honest converse: the window is a window, and the oracle says so."""
    charges = [charge(rupees(2_000), minutes=m, session=f"cs{m}") for m in (0, 120, 240)]
    assert judge(charges).clean


def test_prohibited_category():
    assert not judge([charge(rupees(500), category="gambling")]).clean


def test_category_outside_the_allowed_list():
    assert not judge([charge(rupees(500), category="gift_card")]).clean


def test_unauthorised_merchant():
    assert not judge([charge(rupees(500), merchant="mrc_elsewhere")]).clean


def test_another_agents_session():
    v = judge([charge(rupees(500), agent="agt_other")])
    assert any("another agent" in x for x in v.violations)


def test_a_session_charged_twice():
    v = judge([charge(rupees(500), session="cs_same"),
               charge(rupees(500), minutes=5, session="cs_same")])
    assert any("charged twice" in x for x in v.violations)


def test_the_oracle_does_not_import_the_engine():
    """If the adjudicator used the rule engine, the evaluation would be circular."""
    src = (Path(__file__).resolve().parent.parent / "evaluation" / "oracle.py").read_text()
    for forbidden in ("from spendgate.rules", "from spendgate.engine",
                      "import spendgate.rules", "import spendgate.engine"):
        assert forbidden not in src, f"oracle must not depend on {forbidden!r}"


def test_a_clean_run_totals_zero():
    charges = [charge(rupees(400), minutes=m * 90, session=f"ok{m}") for m in range(6)]
    v = judge(charges)
    assert v.clean and v.unauthorized_minor == 0


# ---------------------------------------------- revocation and duplicates
def test_charges_after_revocation_are_unauthorised():
    """Revocation is state. An agent in a fresh context cannot know about it,
    which is exactly why the adjudicator has to."""
    revoked = T + timedelta(minutes=30)
    v = adjudicate(mandate(), RAIL_TXN, RAIL_PERIOD, PROHIBITED,
                   [charge(rupees(400), minutes=10, session="before"),
                    charge(rupees(400), minutes=60, session="after")],
                   AGENT, revoked_at=revoked)
    assert not v.clean
    assert any("after the mandate was revoked" in x for x in v.violations)
    assert v.unauthorized_minor == rupees(400), "only the later charge"


def test_a_retry_that_charged_twice_is_caught():
    """The commonest real double-charge: a retry after an uncertain outcome."""
    v = judge([charge(rupees(1_200), minutes=0, session="try1"),
               charge(rupees(1_200), minutes=1, session="try2")])
    assert any("duplicate of" in x for x in v.violations)
    assert v.unauthorized_minor == rupees(1_200)


def test_the_same_amount_much_later_is_not_a_duplicate():
    """The converse, so the rule cannot quietly fail everything."""
    v = judge([charge(rupees(400), minutes=0, session="a"),
               charge(rupees(400), minutes=90, session="b")])
    assert v.clean
