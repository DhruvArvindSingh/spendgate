"""The Policy Decision Point (PRD 5, C3).

    decide(ctx, rail) -> Decision

Pure. No network, no I/O, no randomness, no model inference, and no clock reads
(the clock is injected on the Context). Given the same inputs it returns the
same decision forever, which is what makes a decision replayable months later
during a dispute.
"""

from __future__ import annotations

from .models import Context, Decision, Layer, Outcome
from .rails import RailProfile, get as get_rail
from .rules import ENGINE_RULES, Rule

#: Fail-closed safety net. Not a policy rule: if a predicate raises, we do not
#: know whether the request is safe, and "don't know" is a refusal (cf. R15).
ENGINE_ERROR_CODE = "rule_evaluation_error"


def rail_for(ctx: Context) -> RailProfile:
    """Rail profile named by the mandate, defaulting to the strictest known."""
    from .rails import UPI_CIRCLE_V1

    if ctx.mandate is None:
        return UPI_CIRCLE_V1
    return get_rail(ctx.mandate.rail_profile)


def decide(ctx: Context, rail: RailProfile | None = None) -> Decision:
    rail = rail or rail_for(ctx)
    evaluated = 0

    for rule in ENGINE_RULES:
        evaluated += 1
        try:
            fired = rule.fires(ctx, rail)
        except Exception as exc:  # noqa: BLE001 - deliberate: unknown means no
            return Decision(
                outcome=Outcome.DENIED,
                reason_code=ENGINE_ERROR_CODE,
                reason_text=f"Rule {rule.id} could not be evaluated: {exc!s}",
                rule_id=rule.id,
                rules_evaluated=evaluated,
                overridable=False,
                amount_minor=ctx.amount,
                facts_hash=ctx.facts.facts_hash if ctx.facts else None,
                decided_at=ctx.now,
            )
        if fired:
            return Decision(
                outcome=rule.outcome,
                reason_code=rule.reason_code,
                reason_text=rule.message(ctx, rail),
                rule_id=rule.id,
                rules_evaluated=evaluated,
                overridable=rule.overridable,
                amount_minor=ctx.amount,
                facts_hash=ctx.facts.facts_hash if ctx.facts else None,
                decided_at=ctx.now,
            )

    return Decision(
        outcome=Outcome.APPROVED,
        reason_code=None,
        reason_text="Within mandate.",
        rules_evaluated=evaluated,
        amount_minor=ctx.amount,
        facts_hash=ctx.facts.facts_hash if ctx.facts else None,
        decided_at=ctx.now,
    )


def trace(ctx: Context, rail: RailProfile | None = None) -> list[tuple[str, bool]]:
    """Evaluate every rule without short-circuiting.

    Used only for the evidence bundle's rule_trace (PRD 13.2): the decisive rule
    explains the refusal, the full trace proves the decision was computed rather
    than reconstructed afterwards.
    """
    rail = rail or rail_for(ctx)
    out: list[tuple[str, bool]] = []
    for rule in ENGINE_RULES:
        try:
            out.append((rule.id, bool(rule.fires(ctx, rail))))
        except Exception:  # noqa: BLE001
            out.append((rule.id, True))
    return out
