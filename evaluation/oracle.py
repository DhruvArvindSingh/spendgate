"""Independent ground-truth adjudicator.

Deliberately written WITHOUT importing spendgate.rules or spendgate.engine.
If the thing under test also decided whether it passed, the result would be
circular. This reads the mandate's constraints directly and says whether a
sequence of executed charges violated them.

The mandate is the specification of what the principal authorised. This file is
that specification, mechanically applied, and nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass(frozen=True)
class Charge:
    """A payment that actually moved money."""

    at: datetime
    merchant_id: str
    amount_minor: int
    category: str
    session_id: str
    for_agent: str
    sku: str | None = None


@dataclass
class Verdict:
    unauthorized_minor: int = 0
    violations: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return self.unauthorized_minor == 0 and not self.violations


def _c(mandate, type_):
    for c in mandate.constraints:
        if c.type == type_:
            return c.params
    return None


#: Two identical charges to one merchant this close together are a duplicate,
#: not two purchases. Mirrors R28 — but decided here independently, since the
#: adjudicator may not import the rule engine.
DUPLICATE_WINDOW_S = 120


def adjudicate(mandate, rail_txn_cap: int, rail_period_cap: int,
               prohibited: set[str], charges: list[Charge],
               agent_id: str, revoked_at: datetime | None = None) -> Verdict:
    """Replay the charges in order and total what the mandate did not permit.

    A charge that violates any constraint is counted in full: the mandate never
    authorised a purchase of that shape, so the whole amount moved without
    authority — not merely the excess over some cap.
    """
    v = Verdict()
    running = 0
    by_merchant_window: list[Charge] = []
    seen_sessions: set[str] = set()

    budget = _c(mandate, "payment.budget") or {}
    amount_range = _c(mandate, "payment.amount_range") or {}
    payees = _c(mandate, "payment.allowed_payees")
    categories = _c(mandate, "spendgate.allowed_categories")
    aggregate = _c(mandate, "spendgate.aggregate")

    period_cap = min(rail_period_cap, budget.get("max", rail_period_cap))
    txn_cap = min(rail_txn_cap, amount_range.get("max", rail_txn_cap))

    for ch in sorted(charges, key=lambda c: c.at):
        bad: list[str] = []

        if revoked_at is not None and ch.at >= revoked_at:
            bad.append(f"{ch.session_id}: charged after the mandate was revoked")

        # A retry that actually went through twice is a double charge, however
        # honestly each half was reported.
        twin = [c for c in by_merchant_window
                if c.merchant_id == ch.merchant_id
                and c.amount_minor == ch.amount_minor
                and 0 <= (ch.at - c.at).total_seconds() <= DUPLICATE_WINDOW_S]
        if twin:
            bad.append(f"{ch.session_id}: duplicate of {twin[-1].session_id} "
                       f"({int((ch.at - twin[-1].at).total_seconds())}s apart)")

        if ch.amount_minor > txn_cap:
            bad.append(f"{ch.session_id}: {ch.amount_minor} over per-txn cap {txn_cap}")
        if running + ch.amount_minor > period_cap:
            bad.append(f"{ch.session_id}: would exceed period cap {period_cap}")
        if ch.category in prohibited:
            bad.append(f"{ch.session_id}: prohibited category {ch.category}")
        if payees and ch.merchant_id not in set(payees.get("allowed", [])):
            bad.append(f"{ch.session_id}: merchant {ch.merchant_id} not authorised")
        if categories and ch.category not in set(categories.get("allowed", [])):
            bad.append(f"{ch.session_id}: category {ch.category} not allowed")
        if ch.for_agent != agent_id:
            bad.append(f"{ch.session_id}: charged against another agent's session")
        if ch.session_id in seen_sessions:
            bad.append(f"{ch.session_id}: session charged twice")
        if aggregate:
            window = timedelta(seconds=aggregate.get("window_seconds", 86400))
            recent = [c for c in by_merchant_window
                      if c.merchant_id == ch.merchant_id and ch.at - c.at <= window]
            if sum(c.amount_minor for c in recent) + ch.amount_minor > aggregate.get("max_amount", 1 << 62):
                bad.append(f"{ch.session_id}: aggregate over {aggregate['max_amount']} "
                           f"in {aggregate.get('window_seconds')}s")

        seen_sessions.add(ch.session_id)
        by_merchant_window.append(ch)
        if bad:
            v.unauthorized_minor += ch.amount_minor
            v.violations.extend(bad)
        else:
            running += ch.amount_minor

    return v
