"""The rule registry (PRD 7).

Rules are data, not control flow. A declarative table lets the test harness
enumerate every rule and assert each one has a test that trips it, which is
impossible against a nest of if-statements.

Evaluation order is registry order. The first rule to fire wins and the engine
short-circuits, so a refusal always names exactly one cause rather than a list
of simultaneous complaints.

Predicates return True when the rule FIRES (i.e. the request is in violation).
Every predicate is a pure function of (Context, RailProfile).
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Callable
from zoneinfo import ZoneInfo

from .models import Context, Kind, Layer, Outcome
from .money import Paise, fmt
from .rails import RailProfile

Predicate = Callable[[Context, RailProfile], bool]
Message = Callable[[Context, RailProfile], str]


@dataclass(frozen=True)
class Rule:
    id: str
    reason_code: str
    stage: str
    kind: Kind
    outcome: Outcome
    layer: Layer
    fires: Predicate
    message: Message
    summary: str = ""

    @property
    def overridable(self) -> bool:
        """Only the principal's own preferences may be overridden by asking."""
        return self.kind is Kind.POLICY


def _never(ctx: Context, rail: RailProfile) -> bool:
    """Placeholder for rules enforced outside the pure engine (PRD 7.6)."""
    return False


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _c(ctx: Context, type_: str):
    return ctx.mandate.constraint(type_) if ctx.mandate else None


def _effective_txn_cap(ctx: Context, rail: RailProfile) -> tuple[Paise, str]:
    """The per-transaction ceiling is the tighter of the rail and the mandate.

    AP2's payment.amount_range is a bound the principal signed into the mandate;
    the rail's cap is imposed from outside. Whichever binds first is the ceiling,
    and the message names which one it was.
    """
    cap, src = rail.txn_cap, f"the {fmt(rail.txn_cap)} per-transaction ceiling on {rail.name}"
    ar = _c(ctx, "payment.amount_range")
    if ar and ar.get("max") is not None and ar.get("max") < cap:
        cap, src = ar.get("max"), f"this mandate's {fmt(ar.get('max'))} per-purchase limit"
    return cap, src


def _budget_max(ctx: Context, rail: RailProfile) -> Paise:
    b = _c(ctx, "payment.budget")
    return min(rail.period_cap, b.get("max")) if b and b.get("max") is not None else rail.period_cap


def _in_window(ctx: Context, seconds: int, merchant_id: str | None = None):
    cutoff = ctx.now - timedelta(seconds=seconds)
    return [
        t for t in ctx.ledger.recent
        if t.at > cutoff and (merchant_id is None or t.merchant_id == merchant_id)
    ]


# --------------------------------------------------------------------------
# Stage 1 — identity and mandate validity (PRD 7.3)
# --------------------------------------------------------------------------
_S1 = [
    Rule("R01", "agent_unregistered", "identity", Kind.INTEGRITY, Outcome.DENIED, Layer.ENGINE,
         lambda c, r: c.agent is None or not c.agent.registered,
         lambda c, r: "This agent is not registered.",
         "Agent absent from the registry"),
    Rule("R02", "agent_revoked", "identity", Kind.INTEGRITY, Outcome.DENIED, Layer.ENGINE,
         lambda c, r: c.agent.revoked_at is not None and c.agent.revoked_at <= c.now,
         lambda c, r: "This agent's credential has been revoked.",
         "Agent credential revoked"),
    Rule("R03", "mandate_not_found", "identity", Kind.INTEGRITY, Outcome.DENIED, Layer.ENGINE,
         lambda c, r: c.mandate is None,
         lambda c, r: f"No mandate {c.request.mandate_id!r}.",
         "No such mandate"),
    Rule("R04", "mandate_agent_mismatch", "identity", Kind.INTEGRITY, Outcome.DENIED, Layer.ENGINE,
         lambda c, r: c.mandate.agent_id != c.request.agent_id,
         lambda c, r: "This mandate was issued to a different agent.",
         "Confused deputy: mandate belongs to another agent"),
    Rule("R05", "mandate_expired", "identity", Kind.INTEGRITY, Outcome.DENIED, Layer.ENGINE,
         lambda c, r: c.mandate.valid_until is not None and c.mandate.valid_until <= c.now,
         lambda c, r: f"This mandate expired on {c.mandate.valid_until:%d %b %Y}.",
         "Past payment.execution_date.not_after"),
    Rule("R06", "mandate_not_active", "identity", Kind.INTEGRITY, Outcome.DENIED, Layer.ENGINE,
         lambda c, r: c.mandate.valid_from is not None and c.mandate.valid_from > c.now,
         lambda c, r: f"This mandate is not active until {c.mandate.valid_from:%d %b %Y}.",
         "Before payment.execution_date.not_before"),
    Rule("R07", "mandate_revoked", "identity", Kind.INTEGRITY, Outcome.DENIED, Layer.ENGINE,
         lambda c, r: c.mandate.revoked_at is not None and c.mandate.revoked_at <= c.now,
         lambda c, r: "This mandate was revoked.",
         "Revoked by the principal"),
    Rule("R08", "mandate_tampered", "identity", Kind.INTEGRITY, Outcome.DENIED, Layer.ENGINE,
         lambda c, r: not c.mandate.signature_valid,
         lambda c, r: "This mandate's signature did not verify.",
         "ES256 verification failed"),
]

# --------------------------------------------------------------------------
# Stage 2 — fact integrity (PRD 7.4)
# --------------------------------------------------------------------------
_S2 = [
    Rule("R09", "session_not_found", "facts", Kind.INTEGRITY, Outcome.DENIED, Layer.ENGINE,
         lambda c, r: not c.session_found,
         lambda c, r: f"The merchant does not recognise session {c.request.checkout_session_id!r}.",
         "Merchant has no such checkout session"),
    Rule("R10", "session_expired", "facts", Kind.INTEGRITY, Outcome.DENIED, Layer.ENGINE,
         lambda c, r: c.facts is not None and c.facts.expires_at <= c.now,
         lambda c, r: "This checkout session has expired. Ask the merchant for a new quote.",
         "Past the merchant's stated expiry"),
    Rule("R11", "session_already_used", "facts", Kind.INTEGRITY, Outcome.DENIED, Layer.ENGINE,
         lambda c, r: c.facts is not None and c.facts.consumed,
         lambda c, r: "This checkout session has already been paid.",
         "Replay of a consumed session"),
    Rule("R12", "session_agent_mismatch", "facts", Kind.INTEGRITY, Outcome.DENIED, Layer.ENGINE,
         lambda c, r: c.facts is not None and c.facts.issued_to_agent != c.request.agent_id,
         lambda c, r: "This checkout session was issued to a different agent.",
         "Confused deputy: session belongs to another agent"),
    Rule("R13", "session_not_ready", "facts", Kind.INTEGRITY, Outcome.DENIED, Layer.ENGINE,
         lambda c, r: c.facts is not None and c.facts.status != "ready_for_payment",
         lambda c, r: f"The session is {c.facts.status!r}, not ready for payment.",
         "ACP status is not ready_for_payment"),
    Rule("R14", "merchant_unverified", "facts", Kind.INTEGRITY, Outcome.DENIED, Layer.ENGINE,
         lambda c, r: c.facts is not None and not c.facts.merchant_verified,
         lambda c, r: "This merchant could not be verified.",
         "Absent from the registry, or signature invalid"),
    # Fails closed. Unavailable facts are indistinguishable from hostile ones,
    # so there is no fallback to agent-supplied values and no cached price.
    Rule("R15", "facts_unavailable", "facts", Kind.INTEGRITY, Outcome.DENIED, Layer.ENGINE,
         lambda c, r: not c.facts_available or c.facts is None,
         lambda c, r: "The merchant could not be reached, so the price could not be confirmed.",
         "Fail closed when facts cannot be established"),
    Rule("R16", "currency_unsupported", "facts", Kind.RAIL, Outcome.DENIED, Layer.ENGINE,
         lambda c, r: c.facts is not None and c.facts.currency not in r.currencies,
         lambda c, r: f"{c.facts.currency} is not supported on {r.name}.",
         "Currency outside the rail profile"),
]

# --------------------------------------------------------------------------
# Stage 3 — hard rails (PRD 7.5). Never escalated: the principal cannot
# authorise something the rail forbids, and asking them trains bad habits.
# --------------------------------------------------------------------------
_S3 = [
    Rule("R17", "rail_txn_cap_exceeded", "rails", Kind.RAIL, Outcome.DENIED, Layer.ENGINE,
         lambda c, r: c.amount > _effective_txn_cap(c, r)[0],
         lambda c, r: f"{fmt(c.amount)} exceeds {_effective_txn_cap(c, r)[1]}.",
         "Per-transaction ceiling"),
    Rule("R18", "rail_monthly_cap_exceeded", "rails", Kind.RAIL, Outcome.DENIED, Layer.ENGINE,
         lambda c, r: c.ledger.committed_minor + c.amount > r.period_cap,
         lambda c, r: (f"{fmt(c.amount)} would take this {r.period.replace('_',' ')} to "
                       f"{fmt(c.ledger.committed_minor + c.amount)}, over the {fmt(r.period_cap)} cap."),
         "Period cap on the rail"),
    Rule("R19", "rail_delegate_limit", "rails", Kind.RAIL, Outcome.DENIED, Layer.ENGINE,
         lambda c, r: c.ledger.active_delegates > r.max_delegates,
         lambda c, r: f"{r.name} allows {r.max_delegates} active agents; this principal has {c.ledger.active_delegates}.",
         "Too many delegated agents"),
    Rule("R20", "mandate_budget_exceeded", "rails", Kind.RAIL, Outcome.DENIED, Layer.ENGINE,
         lambda c, r: (_c(c, "payment.budget") is not None
                       and c.ledger.committed_minor + c.amount > _c(c, "payment.budget").get("max")),
         lambda c, r: (f"{fmt(c.amount)} would exceed this mandate's "
                       f"{fmt(_c(c, 'payment.budget').get('max'))} budget "
                       f"({fmt(c.ledger.committed_minor)} already committed)."),
         "AP2 payment.budget accumulation"),
    Rule("R21", "recurrence_exhausted", "rails", Kind.RAIL, Outcome.DENIED, Layer.ENGINE,
         lambda c, r: (_c(c, "payment.agent_recurrence") is not None
                       and c.ledger.occurrences >= _c(c, "payment.agent_recurrence").get("max_occurrences", 10**9)),
         lambda c, r: (f"This mandate allows {_c(c, 'payment.agent_recurrence').get('max_occurrences')} "
                       f"payments per period; {c.ledger.occurrences} have been made."),
         "AP2 payment.agent_recurrence exhausted"),
    Rule("R22", "category_prohibited", "rails", Kind.RAIL, Outcome.DENIED, Layer.ENGINE,
         lambda c, r: c.facts is not None and c.facts.category in r.prohibited_categories,
         lambda c, r: f"{c.facts.category!r} purchases are not permitted on {r.name}.",
         "Prohibited category, non-overridable"),
    Rule("R23", "merchant_denied", "rails", Kind.RAIL, Outcome.DENIED, Layer.ENGINE,
         lambda c, r: c.facts is not None and (
             c.facts.merchant_id in set(
                 (_c(c, "spendgate.denied_merchants").get("merchants", []) if _c(c, "spendgate.denied_merchants") else []))
             or (_c(c, "payment.allowed_payees") is not None
                 and c.facts.merchant_id not in set(_c(c, "payment.allowed_payees").get("allowed", [])))),
         lambda c, r: f"This mandate does not authorise payments to {c.facts.merchant_id!r}.",
         "Denylist, or outside payment.allowed_payees"),
    Rule("R24", "instrument_not_allowed", "rails", Kind.RAIL, Outcome.DENIED, Layer.ENGINE,
         lambda c, r: (c.facts is not None and _c(c, "payment.allowed_payment_instruments") is not None
                       and c.facts.instrument not in set(
                           _c(c, "payment.allowed_payment_instruments").get("allowed", []))),
         lambda c, r: f"{c.facts.instrument!r} is not an allowed payment instrument on this mandate.",
         "AP2 payment.allowed_payment_instruments"),
]

# --------------------------------------------------------------------------
# Stage 4 — idempotency and concurrency (PRD 7.6).
# R25-R27 need the request store and R29 needs the budget lock, so they are
# enforced outside the pure engine. They stay in the registry so the reason-code
# vocabulary is complete and coverage remains checkable.
# --------------------------------------------------------------------------
_S4 = [
    Rule("R25", "idempotent_replay", "concurrency", Kind.PROTOCOL, Outcome.REPLAYED, Layer.SERVICE,
         _never, lambda c, r: "Replaying the stored result for this Idempotency-Key.",
         "Same key, same body"),
    Rule("R26", "idempotency_conflict", "concurrency", Kind.PROTOCOL, Outcome.DENIED, Layer.SERVICE,
         _never, lambda c, r: "This Idempotency-Key was already used with a different request.",
         "Same key, different body"),
    Rule("R27", "idempotency_in_flight", "concurrency", Kind.PROTOCOL, Outcome.DENIED, Layer.SERVICE,
         _never, lambda c, r: "A request with this Idempotency-Key is still processing.",
         "Original still in flight"),
    Rule("R28", "suspected_duplicate", "concurrency", Kind.POLICY, Outcome.DENIED, Layer.ENGINE,
         lambda c, r: c.facts is not None and any(
             t.merchant_id == c.facts.merchant_id and t.amount_minor == c.amount
             for t in _in_window(c, 60, c.facts.merchant_id)),
         lambda c, r: f"An identical {fmt(c.amount)} payment to this merchant was made moments ago.",
         "Same merchant and amount within 60s"),
    Rule("R29", "concurrent_budget_conflict", "concurrency", Kind.INTEGRITY, Outcome.DENIED, Layer.LEDGER,
         _never, lambda c, r: "Another payment on this mandate is being processed. Retry shortly.",
         "Lost the per-mandate serialisation lock"),
]

# --------------------------------------------------------------------------
# Stage 5 — soft policy (PRD 7.7). The principal's own preferences, so these
# ask rather than refuse.
# --------------------------------------------------------------------------
def _quiet(ctx: Context, rail: RailProfile) -> bool:
    q = _c(ctx, "spendgate.quiet_hours")
    if not q:
        return False
    start_s, end_s = q.get("not_between", ["23:00", "07:00"])
    tz = ZoneInfo(q.get("tz", "Asia/Kolkata"))
    local = ctx.now.astimezone(tz).time()
    start = time.fromisoformat(start_s)
    end = time.fromisoformat(end_s)
    return (start <= local or local < end) if start > end else (start <= local < end)


def _price_anomaly(ctx: Context, rail: RailProfile) -> bool:
    p = _c(ctx, "spendgate.price_anomaly")
    if not p or ctx.facts is None:
        return False
    factor = p.get("factor", 2.0)
    for item in ctx.facts.line_items:
        history = ctx.ledger.price_history.get(item.sku, ())
        if len(history) >= p.get("min_observations", 3):
            if item.unit_minor > statistics.median(history) * factor:
                return True
    return False


_S5 = [
    Rule("R30", "above_step_up_threshold", "policy", Kind.POLICY, Outcome.ESCALATED, Layer.ENGINE,
         lambda c, r: (_c(c, "spendgate.step_up_above") is not None
                       and c.amount > _c(c, "spendgate.step_up_above").get("amount")),
         lambda c, r: (f"{fmt(c.amount)} is above the {fmt(_c(c, 'spendgate.step_up_above').get('amount'))} "
                       "you asked to approve yourself."),
         "Over the principal's step-up threshold"),
    Rule("R31", "merchant_first_seen", "policy", Kind.POLICY, Outcome.ESCALATED, Layer.ENGINE,
         lambda c, r: c.facts is not None and c.facts.merchant_id not in c.ledger.merchants_seen,
         lambda c, r: f"First purchase from {c.facts.merchant_id}.",
         "No prior settled payment to this payee"),
    Rule("R32", "category_not_allowed", "policy", Kind.POLICY, Outcome.ESCALATED, Layer.ENGINE,
         lambda c, r: (c.facts is not None and _c(c, "spendgate.allowed_categories") is not None
                       and c.facts.category not in set(_c(c, "spendgate.allowed_categories").get("allowed", []))),
         lambda c, r: f"{c.facts.category.title()} is not on your allowed list.",
         "Outside spendgate.allowed_categories"),
    Rule("R33", "budget_reserve_breach", "policy", Kind.POLICY, Outcome.ESCALATED, Layer.ENGINE,
         lambda c, r: (c.ledger.committed_minor + c.amount) > int(0.8 * _budget_max(c, r)),
         lambda c, r: (f"This leaves {fmt(max(0, _budget_max(c, r) - c.ledger.committed_minor - c.amount))} "
                       "for the rest of the period."),
         "Past 80% of the period budget"),
    # Structuring. Escalates rather than denies: the principal may genuinely
    # want the item, and the valuable act is showing them the assembled pattern.
    Rule("R34", "aggregate_pattern", "policy", Kind.POLICY, Outcome.ESCALATED, Layer.ENGINE,
         lambda c, r: (c.facts is not None and _c(c, "spendgate.aggregate") is not None
                       and (sum(t.amount_minor for t in _in_window(
                                c, _c(c, "spendgate.aggregate").get("window_seconds", 86400),
                                c.facts.merchant_id)) + c.amount)
                           > _c(c, "spendgate.aggregate").get("max_amount")),
         lambda c, r: (lambda w: (
             f"{len(w) + 1} purchases from {c.facts.merchant_id} totalling "
             f"{fmt(sum(t.amount_minor for t in w) + c.amount)}."))(
             _in_window(c, _c(c, "spendgate.aggregate").get("window_seconds", 86400), c.facts.merchant_id)),
         "Windowed sum by merchant exceeds the cap"),
    Rule("R35", "velocity_elevated", "policy", Kind.POLICY, Outcome.ESCALATED, Layer.ENGINE,
         lambda c, r: (_c(c, "spendgate.velocity") is not None
                       and len(_in_window(c, _c(c, "spendgate.velocity").get("window_seconds", 3600))) + 1
                           >= _c(c, "spendgate.velocity").get("max_count")),
         lambda c, r: (f"{len(_in_window(c, _c(c, 'spendgate.velocity').get('window_seconds', 3600))) + 1}"
                       " purchases in the last hour."),
         "Approaching the velocity ceiling"),
    Rule("R36", "quiet_hours", "policy", Kind.POLICY, Outcome.ESCALATED, Layer.ENGINE,
         _quiet,
         lambda c, r: (lambda q: f"It's {c.now.astimezone(ZoneInfo(q.get('tz','Asia/Kolkata'))):%H:%M}.")(
             _c(c, "spendgate.quiet_hours")),
         "Inside the principal's quiet window"),
    Rule("R37", "price_anomaly", "policy", Kind.POLICY, Outcome.ESCALATED, Layer.ENGINE,
         _price_anomaly,
         lambda c, r: "This price is well above what you have paid for this item before.",
         "Deviates from observed price history"),
]

REGISTRY: tuple[Rule, ...] = tuple(_S1 + _S2 + _S3 + _S4 + _S5)
BY_ID: dict[str, Rule] = {r.id: r for r in REGISTRY}
ENGINE_RULES: tuple[Rule, ...] = tuple(r for r in REGISTRY if r.layer is Layer.ENGINE)

assert len(REGISTRY) == 37, f"registry drifted from the PRD: {len(REGISTRY)} rules"
assert len({r.reason_code for r in REGISTRY}) == 37, "duplicate reason code"
