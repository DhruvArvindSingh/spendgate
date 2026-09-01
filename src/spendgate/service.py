"""Orchestration (PRD 9, 10).

Holds the three things the pure engine deliberately cannot: the idempotency
store (R25-R27), the per-mandate lock (R29), and the fact resolver's network
boundary.

Ordering rule (PRD 8.2): persist the decision, persist the reservation, then
call the rail. A crash between reservation and execution leaves a recoverable
held reservation. A crash between a rail call and its record leaves money moved
with no trace, which is not recoverable - so the order is fixed.
"""

from __future__ import annotations

import hashlib
import json
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Protocol

from .engine import decide
from .escalation import EscalationBudget
from .ledger import BudgetLockTimeout, InMemoryLedger
from .models import (
    AgentRecord, AuthorizationRequest, Context, Decision, Mandate,
    Outcome, ResolvedFacts,
)
from .rules import BY_ID


class FactsUnavailable(RuntimeError):
    """The merchant could not be reached. Maps to R15; never falls back."""


class FactResolver(Protocol):
    def resolve(self, checkout_session_id: str) -> ResolvedFacts | None: ...


def _body_hash(req: AuthorizationRequest) -> str:
    return hashlib.sha256(
        json.dumps(
            {"m": req.mandate_id, "cs": req.checkout_session_id, "a": req.agent_id},
            sort_keys=True, separators=(",", ":"),
        ).encode()
    ).hexdigest()


@dataclass
class _Record:
    body_hash: str
    in_flight: bool = True
    result: Decision | None = None


class IdempotencyStore:
    """ACP semantics (PRD 9.2): replay on match, 422 on conflict, 409 in flight."""

    def __init__(self) -> None:
        self._d: dict[tuple[str, str], _Record] = {}
        self._lock = threading.Lock()

    def begin(self, scope: str, key: str, body_hash: str) -> tuple[str, Decision | None]:
        with self._lock:
            rec = self._d.get((scope, key))
            if rec is None:
                self._d[(scope, key)] = _Record(body_hash)
                return "new", None
            if rec.body_hash != body_hash:
                return "conflict", None
            if rec.in_flight:
                return "in_flight", None
            return "replay", rec.result

    def finish(self, scope: str, key: str, result: Decision) -> None:
        with self._lock:
            rec = self._d.get((scope, key))
            if rec:
                rec.in_flight = False
                rec.result = result


def _denied(rule_id: str, ctx: Context | None = None) -> Decision:
    rule = BY_ID[rule_id]
    return Decision(
        outcome=rule.outcome,
        reason_code=rule.reason_code,
        reason_text=rule.message(ctx, None) if ctx else rule.summary,
        rule_id=rule.id,
        overridable=rule.overridable,
        decided_at=datetime.now(timezone.utc),
    )


@dataclass
class SpendGate:
    ledger: InMemoryLedger
    resolver: FactResolver
    mandates: dict[str, Mandate] = field(default_factory=dict)
    agents: dict[str, AgentRecord] = field(default_factory=dict)
    idempotency: IdempotencyStore = field(default_factory=IdempotencyStore)
    #: Human attention is finite; an attacker who can raise unlimited prompts
    #: has a denial-of-service against it (PRD 7.7, A8).
    escalation: EscalationBudget = field(default_factory=EscalationBudget)
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
    lock_timeout: float = 2.0

    def authorize(self, req: AuthorizationRequest) -> tuple[str, Decision]:
        """Returns (authorization_id, decision)."""
        scope = f"{req.agent_id}:POST /v1/authorizations"
        if req.idempotency_key:
            state, stored = self.idempotency.begin(scope, req.idempotency_key, _body_hash(req))
            if state == "conflict":
                return "", _denied("R26")
            if state == "in_flight":
                return "", _denied("R27")
            if state == "replay" and stored is not None:
                return "", Decision(**{**stored.__dict__, "outcome": Outcome.REPLAYED})

        auth_id = "aut_" + uuid.uuid4().hex[:12]
        decision = self._evaluate(req, auth_id)
        if req.idempotency_key:
            self.idempotency.finish(scope, req.idempotency_key, decision)
        return auth_id, decision

    def _gate_escalation(self, mandate: Mandate, decision: Decision,
                         auth_id: str, now: datetime) -> Decision:
        """Charge a prompt to the principal's attention budget, or refuse.

        Refusing is the only safe answer: a prompt that cannot be shown is a
        decision the principal did not make, and treating it as approval is
        exactly the fatigue attack this exists to stop.
        """
        allowed, why = self.escalation.check(mandate.principal_id, now)
        if allowed:
            self.escalation.raise_prompt(mandate.principal_id, auth_id, now)
            return decision
        rule = BY_ID["R38"]
        return Decision(
            outcome=rule.outcome,
            reason_code=rule.reason_code,
            reason_text=f"{why}. The original reason was: {decision.reason_text}",
            rule_id=rule.id,
            rules_evaluated=decision.rules_evaluated,
            overridable=False,
            amount_minor=decision.amount_minor,
            facts_hash=decision.facts_hash,
            decided_at=now,
        )

    def resolve_escalation(self, mandate_id: str, auth_id: str) -> None:
        """The principal answered. Frees a pending slot, not the window count."""
        mandate = self.mandates.get(mandate_id)
        if mandate is not None:
            self.escalation.resolve(mandate.principal_id, auth_id)

    def _evaluate(self, req: AuthorizationRequest, auth_id: str = "") -> Decision:
        now = self.clock()
        mandate = self.mandates.get(req.mandate_id)
        agent = self.agents.get(req.agent_id)

        facts, available, found = None, True, True
        if mandate is not None:
            try:
                facts = self.resolver.resolve(req.checkout_session_id)
                found = facts is not None
            except FactsUnavailable:
                available = False

        base = dict(request=req, now=now, mandate=mandate, facts=facts,
                    agent=agent, facts_available=available, session_found=found)

        if mandate is None:
            return decide(Context(**base))

        # Decision and reservation share one critical section (PRD 9.1).
        try:
            with self.ledger.begin(req.mandate_id, timeout=self.lock_timeout):
                ctx = Context(**base, ledger=self.ledger.snapshot(req.mandate_id))
                decision = decide(ctx)
                if decision.outcome is Outcome.ESCALATED:
                    decision = self._gate_escalation(mandate, decision, auth_id, now)
                if decision.outcome is Outcome.APPROVED:
                    self.ledger.reserve(
                        req.mandate_id, _auth_key(req), decision.amount_minor, now,
                        facts.merchant_id if facts else None,
                    )
                return decision
        except BudgetLockTimeout:
            return _denied("R29")


def _auth_key(req: AuthorizationRequest) -> str:
    """Reservation key. Session-scoped so a retry of the same session reserves once."""
    return f"{req.mandate_id}:{req.checkout_session_id}"
