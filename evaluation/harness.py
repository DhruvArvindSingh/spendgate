"""Two-arm runner and metrics (PRD 14.3).

Each case gets a fresh world — fresh ledger, fresh rail, fresh clock — so cases
cannot contaminate each other. Both arms see identical inputs.

Rules this corpus exercises and rules it does not: step_up_above, quiet_hours
and price_anomaly are absent from the evaluation mandate. The first two would
add time-of-day noise to a containment measurement, and the third is inert
without price history (see README limitations). They are covered by unit tests
instead, and the corpus makes no claim about them.
"""

from __future__ import annotations

import statistics
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone

from spendgate import Constraint, Mandate, rupees
from spendgate.merchant import MERCHANT_ID, MerchantState, serve
from spendgate.rails import UPI_CIRCLE_V1

from .arms import (
    AGENT, MANDATE, ArmContext, AttemptResult, NaiveArm, build_spendgate_arm,
)
from .corpus import CLASSES, Case, build_corpus
from .oracle import adjudicate

BUDGET = rupees(15_000)


def eval_mandate(now: datetime) -> Mandate:
    return Mandate(
        mandate_id=MANDATE, principal_id="usr_eval", agent_id=AGENT,
        rail_profile="upi_circle.v1", issued_at=now - timedelta(days=1),
        valid_from=now - timedelta(days=1), valid_until=now + timedelta(days=29),
        constraints=(
            Constraint("payment.budget", {"max": BUDGET, "currency": "INR"}),
            Constraint("payment.amount_range", {"min": 0, "max": rupees(5_000),
                                                "currency": "INR"}),
            Constraint("payment.allowed_payees", {"allowed": [MERCHANT_ID]}),
            Constraint("spendgate.allowed_categories",
                       {"allowed": ["grocery", "electronics", "household"]}),
            Constraint("spendgate.aggregate", {"max_amount": rupees(5_000),
                                               "window_seconds": 3600,
                                               "group_by": "merchant_id"}),
            Constraint("spendgate.velocity", {"max_count": 10, "window_seconds": 3600}),
        ),
    )


@dataclass
class CaseOutcome:
    case_id: str
    klass: str
    arm: str
    settled_count: int
    settled_minor: int
    unauthorized_minor: int
    violations: list[str]
    outcomes: list[str]
    rules: list[str]
    latencies: list[float]

    @property
    def contained(self) -> bool:
        return self.unauthorized_minor == 0


def _run_case(arm, case: Case) -> list[AttemptResult]:
    if any(a.concurrent for a in case.attempts):
        results: list[AttemptResult] = []
        lock = threading.Lock()

        def go(a):
            try:
                r = arm.attempt(case.id, a)
            except Exception as exc:                       # noqa: BLE001
                r = AttemptResult(case.id, arm.name, False, "ERROR", str(exc), None, 0, 0.0)
            with lock:
                results.append(r)

        threads = [threading.Thread(target=go, args=(a,)) for a in case.attempts]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        return results

    out = []
    for a in case.attempts:
        try:
            out.append(arm.attempt(case.id, a))
        except Exception as exc:                           # noqa: BLE001
            out.append(AttemptResult(case.id, arm.name, False, "ERROR", str(exc), None, 0, 0.0))
    return out


def run(cases: list[Case] | None = None, verbose: bool = False) -> dict:
    cases = cases or build_corpus()
    rows: list[CaseOutcome] = []
    escalations = 0

    with serve() as (url, mstate):
        for case in cases:
            for arm_name in ("A_naive", "B_spendgate"):
                if arm_name not in case.applies_to:
                    continue
                now = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)
                clock = {"t": now}
                mstate.clock = lambda c=clock: c["t"]
                mstate.hostile, mstate.reprice_to = False, None
                ctx = ArmContext(url=url, mstate=mstate, clock=clock)
                mandate = eval_mandate(now)

                if arm_name == "A_naive":
                    arm = NaiveArm(ctx=ctx, per_txn_cap=rupees(5_000),
                                   monthly_cap=BUDGET,
                                   prohibited=set(UPI_CIRCLE_V1.prohibited_categories))
                else:
                    arm = build_spendgate_arm(ctx, mandate, BUDGET)

                results = _run_case(arm, case)
                verdict = adjudicate(
                    mandate, UPI_CIRCLE_V1.txn_cap, UPI_CIRCLE_V1.period_cap,
                    set(UPI_CIRCLE_V1.prohibited_categories), arm.charges, AGENT,
                )
                if arm_name == "B_spendgate":
                    escalations += getattr(arm, "escalations", 0)

                rows.append(CaseOutcome(
                    case_id=case.id, klass=case.klass, arm=arm_name,
                    settled_count=sum(1 for r in results if r.allowed),
                    settled_minor=sum(r.charged_minor for r in results),
                    unauthorized_minor=verdict.unauthorized_minor,
                    violations=verdict.violations,
                    outcomes=[r.outcome for r in results],
                    rules=[r.rule_id for r in results if r.rule_id],
                    latencies=[r.latency_ms for r in results],
                ))
            if verbose and len(rows) % 40 == 0:
                print(f"  … {len(rows)//2}/{len(cases)} cases")

    return summarise(rows, cases, escalations)


def summarise(rows: list[CaseOutcome], cases: list[Case], escalations: int) -> dict:
    by_arm = {"A_naive": [r for r in rows if r.arm == "A_naive"],
              "B_spendgate": [r for r in rows if r.arm == "B_spendgate"]}
    hostile_ids = {c.id for c in cases if c.hostile}
    benign_ids = {c.id for c in cases if not c.hostile}

    summary: dict = {"cases": len(cases), "classes": {}, "arms": {}}

    for arm, rs in by_arm.items():
        hostile = [r for r in rs if r.case_id in hostile_ids]
        benign = [r for r in rs if r.case_id in benign_ids]
        lat = [x for r in rs for x in r.latencies]
        summary["arms"][arm] = {
            "unauthorized_minor": sum(r.unauthorized_minor for r in rs),
            "settled_minor": sum(r.settled_minor for r in rs),
            "hostile_cases": len(hostile),
            "hostile_contained": sum(1 for r in hostile if r.contained),
            "containment_rate": round(
                sum(1 for r in hostile if r.contained) / max(1, len(hostile)), 4),
            "benign_cases": len(benign),
            "benign_settled": sum(1 for r in benign if r.settled_count > 0),
            "false_refusal_rate": round(
                1 - sum(1 for r in benign if r.settled_count > 0) / max(1, len(benign)), 4),
            "latency_ms_p50": round(statistics.median(lat), 2) if lat else None,
            "latency_ms_p95": round(
                statistics.quantiles(lat, n=20)[18], 2) if len(lat) > 20 else None,
        }

    for klass in CLASSES:
        entry = {}
        for arm, rs in by_arm.items():
            sub = [r for r in rs if r.klass == klass]
            entry[arm] = {
                "cases": len(sub),
                "contained": sum(1 for r in sub if r.contained),
                "unauthorized_minor": sum(r.unauthorized_minor for r in sub),
                "applicable": bool(sub),
            }
        summary["classes"][klass] = entry

    summary["escalations_arm_b"] = escalations
    summary["rows"] = [asdict(r) for r in rows]
    return summary
