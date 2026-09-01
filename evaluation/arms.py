"""The two arms (PRD 14.1). Same corpus, same merchant, same rail, one variable.

Arm A is a good-faith implementation of the prevailing pattern, not a strawman.
It checks a per-transaction cap and a running monthly total, refuses prohibited
categories, and is otherwise a reasonable thing to write. Its single flaw is the
one this project is about: the numbers it checks are supplied by the agent, and
it has no memory shaped like a budget.

Arm B is the same flow with SpendGate in the middle.
"""

from __future__ import annotations

import dataclasses
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import httpx

from spendgate import AuthorizationRequest, InMemoryLedger, Outcome, SpendGate
from spendgate.acp import AcpFactResolver
from spendgate.merchant import CATALOG, MERCHANT_ID, MerchantState
from spendgate.rail import FakeRazorpay
from spendgate.settlement import AuthState, Authorization, Settlement

from .corpus import Attempt
from .oracle import Charge

AGENT = "agt_shopper_01"
MANDATE = "mnd_eval"
SECRET = "whsec_eval"


@dataclass
class AttemptResult:
    case_id: str
    arm: str
    allowed: bool
    outcome: str
    reason: str | None
    rule_id: str | None
    charged_minor: int
    latency_ms: float


@dataclass
class ArmContext:
    """Shared world: one merchant, one clock, one rail per run."""

    url: str
    mstate: MerchantState
    clock: dict
    rail: FakeRazorpay = field(default_factory=FakeRazorpay)
    sessions: list[str] = field(default_factory=list)

    def advance(self, seconds: int) -> None:
        self.clock["t"] += timedelta(seconds=seconds)

    def quote(self, sku: str, agent: str = AGENT) -> str:
        r = httpx.post(
            f"{self.url}/checkout_sessions",
            json={"items": [{"id": sku, "quantity": 1}]},
            headers={"Authorization": f"Bearer {agent}", "API-Version": "2026-04-17",
                     "Idempotency-Key": f"q-{len(self.sessions)}-{time.monotonic_ns()}"},
        )
        r.raise_for_status()
        sid = r.json()["id"]
        self.sessions.append(sid)
        return sid

    def prepare(self, a: Attempt) -> str:
        self.advance(a.delay_s)
        self.mstate.hostile = a.reprice_to is not None
        self.mstate.reprice_to = a.reprice_to
        if a.reuse_index is not None and a.reuse_index < len(self.sessions):
            return self.sessions[a.reuse_index]
        return self.quote(a.sku, a.as_agent or AGENT)


# ---------------------------------------------------------------- Arm A
@dataclass
class NaiveArm:
    """Agent holds the payment tool; limits live in its instructions."""

    ctx: ArmContext
    per_txn_cap: int
    monthly_cap: int
    prohibited: set[str]
    spent: int = 0
    charges: list[Charge] = field(default_factory=list)
    name: str = "A_naive"

    def _session_total(self, sid: str, fallback: int) -> int:
        try:
            r = httpx.get(f"{self.ctx.url}/checkout_sessions/{sid}",
                          headers={"Authorization": f"Bearer {AGENT}",
                                   "API-Version": "2026-04-17"}, timeout=5.0)
            return int(r.json()["totals"]["total"]) if r.status_code == 200 else fallback
        except Exception:                                  # noqa: BLE001
            return fallback

    def attempt(self, case_id: str, a: Attempt) -> AttemptResult:
        t0 = time.perf_counter()
        sid = self.ctx.prepare(a)

        # Arm A charges what the merchant's session says, exactly as Arm B does.
        # Modelling it with a catalogue constant would quietly exempt Arm A from
        # merchant-side repricing and flatter it.
        real_category = CATALOG[a.sku]["category"]
        real = self._session_total(sid, fallback=CATALOG[a.sku]["amount"])
        # Everything the guard reads comes from the agent.
        claimed = a.claimed_minor if a.claimed_minor is not None else real
        claimed_category = a.claimed_category or real_category

        def done(allowed, outcome, reason, charged=0):
            return AttemptResult(case_id, self.name, allowed, outcome, reason, None,
                                 charged, (time.perf_counter() - t0) * 1000)

        if claimed > self.per_txn_cap:
            return done(False, "REFUSED", "over per-transaction limit")
        if self.spent + claimed > self.monthly_cap:
            return done(False, "REFUSED", "over monthly limit")
        if claimed_category in self.prohibited:
            return done(False, "REFUSED", "prohibited category")

        # Approved on the agent's numbers. The charge follows the merchant's
        # checkout session, which is where the real price lives.
        order = self.ctx.rail.create_order(real, f"naive-{sid}", {})
        self.ctx.rail.capture_amount_override = a.over_capture_to
        payment = self.ctx.rail.pay(order["id"])
        charged = payment["amount"]
        self.spent += claimed                      # it tracks what it was told
        self.charges.append(Charge(self.ctx.clock["t"], MERCHANT_ID, charged,
                                   real_category, sid, a.as_agent or AGENT))
        return done(True, "SETTLED", None, charged)


# ---------------------------------------------------------------- Arm B
@dataclass
class SpendGateArm:
    ctx: ArmContext
    gate: SpendGate
    settle: Settlement
    charges: list[Charge] = field(default_factory=list)
    escalations: int = 0
    name: str = "B_spendgate"

    def attempt(self, case_id: str, a: Attempt) -> AttemptResult:
        t0 = time.perf_counter()

        if a.expire_mandate or a.revoke_mandate:
            m = self.gate.mandates[MANDATE]
            field_ = "valid_until" if a.expire_mandate else "revoked_at"
            self.gate.mandates[MANDATE] = dataclasses.replace(
                m, **{field_: self.ctx.clock["t"] - timedelta(minutes=1)})

        sid = self.ctx.prepare(a)
        real_category = CATALOG[a.sku]["category"]

        def done(allowed, outcome, reason, rule, charged=0):
            return AttemptResult(case_id, self.name, allowed, outcome, reason, rule,
                                 charged, (time.perf_counter() - t0) * 1000)

        _, d = self.gate.authorize(AuthorizationRequest(MANDATE, sid, AGENT))
        if d.outcome is Outcome.ESCALATED:
            self.escalations += 1
            # An escalation holds no budget and moves no money until a human
            # answers. Unanswered inside the run is a deny by default (PRD 7.7).
            return done(False, "ESCALATED", d.reason_text, d.rule_id)
        if d.outcome is not Outcome.APPROVED:
            return done(False, "REFUSED", d.reason_text, d.rule_id)

        auth = self.settle.execute(Authorization(
            f"{MANDATE}:{sid}", MANDATE, sid, d.amount_minor, MERCHANT_ID, sku=a.sku))
        if auth.state is not AuthState.EXECUTING:
            return done(False, auth.state.value, "rail did not accept the order", None)

        self.ctx.rail.capture_amount_override = a.over_capture_to
        payment = self.ctx.rail.pay(auth.order_id)
        auth = self._notify(auth, payment)

        if auth.state is AuthState.SETTLED:
            self.charges.append(Charge(self.ctx.clock["t"], MERCHANT_ID,
                                       auth.captured_minor or d.amount_minor,
                                       real_category, sid, AGENT))
            try:
                self.gate.resolver.complete(sid, auth.payment_id)
            except Exception:                       # noqa: BLE001 - best effort
                pass
            return done(True, "SETTLED", None, None, auth.captured_minor or d.amount_minor)
        return done(False, auth.state.value, auth.history[-1][1] if auth.history else None, None)

    def _notify(self, auth: Authorization, payment: dict) -> Authorization:
        import json

        from spendgate.webhooks import EventDeduplicator, receive, sign

        event = "payment.failed" if payment["status"] == "failed" else "payment.captured"
        body = json.dumps(self.ctx.rail.webhook_body(event, payment)).encode()
        parsed = receive(body, {"X-Razorpay-Signature": sign(body, SECRET),
                                "x-razorpay-event-id": f"evt_{payment['id']}"},
                         SECRET, EventDeduplicator())
        return self.settle.on_event(parsed) or auth


def build_spendgate_arm(ctx: ArmContext, mandate, budget_minor: int) -> SpendGateArm:
    from spendgate import AgentRecord

    ledger = InMemoryLedger()
    ledger.open_account(MANDATE, budget_minor)
    # A prior settled purchase two hours back, so the merchant is not first-seen
    # (R31) and the seed sits outside the aggregate window.
    earlier = ctx.clock["t"] - timedelta(hours=2)
    ledger.reserve(MANDATE, "seed", 50_000, earlier, MERCHANT_ID)
    ledger.commit(MANDATE, "seed", earlier, merchant_id=MERCHANT_ID)

    gate = SpendGate(
        ledger=ledger,
        resolver=AcpFactResolver(ctx.url, AGENT, ctx.mstate.secret),
        mandates={MANDATE: mandate},
        agents={AGENT: AgentRecord(AGENT, "usr_eval")},
        clock=lambda: ctx.clock["t"],
    )
    return SpendGateArm(ctx=ctx, gate=gate,
                        settle=Settlement(ledger=ledger, rail=ctx.rail,
                                          clock=lambda: ctx.clock["t"]))
