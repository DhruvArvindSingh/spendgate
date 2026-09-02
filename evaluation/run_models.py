#!/usr/bin/env python3
"""Run the LLM arms across several models and report who leaked what.

    python -m evaluation.run_models                       # everything, 1 rep
    python -m evaluation.run_models --reps 2
    python -m evaluation.run_models --only openai/gpt-5,z-ai/glm-4.7
    python -m evaluation.run_models --scenarios merchant_reprice,revoked_authority
    python -m evaluation.run_models --merge results/models.json --scenarios ...

`--scenarios` runs a subset; `--merge` folds the result into an existing file
instead of replacing it, so adding a scenario does not mean paying to re-run
the ones already measured.

Each model plays both arms against its own private world — its own merchant
sessions, its own ledger, its own rail — so one model cannot affect another's
result. Models run in parallel because they are independent.

Cost comes from OpenRouter's own accounting, not an estimate.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import dataclasses  # noqa: E402

from spendgate import rupees  # noqa: E402
from spendgate.dotenv import find_and_load  # noqa: E402
from spendgate.merchant import MerchantState, serve  # noqa: E402
from spendgate.rails import UPI_CIRCLE_V1  # noqa: E402

find_and_load(Path(__file__).resolve().parent.parent)

from evaluation.arms import (  # noqa: E402
    AGENT, MANDATE, ArmContext, NaiveArm, build_spendgate_arm,
)
from evaluation.harness import BUDGET, eval_mandate  # noqa: E402
from evaluation.llm import LlmUnavailable, OpenRouter, available  # noqa: E402
from evaluation.llm_agent import run_case  # noqa: E402
from evaluation.oracle import adjudicate  # noqa: E402
from evaluation.run_llm import EXTRAS, SCENARIOS  # noqa: E402

RESULTS = Path(__file__).resolve().parent.parent / "results"

#: One current model per family. Pinned rather than latest-aliased so a rerun
#: months from now measures the same thing.
MODELS = [
    ("openai/gpt-5", "GPT-5"),
    ("google/gemini-3-flash-preview", "Gemini 3 Flash"),
    ("anthropic/claude-sonnet-4.5", "Claude Sonnet 4.5"),
    ("z-ai/glm-4.7", "GLM-4.7"),
    ("moonshotai/kimi-k2.5", "Kimi K2.5"),
    ("minimax/minimax-m2.5", "MiniMax M2.5"),
]

_print_lock = threading.Lock()


def say(*args) -> None:
    with _print_lock:
        print(*args, flush=True)


def fmt(minor: int) -> str:
    return f"₹{minor / 100:,.0f}"


def run_model(model: str, label: str, url: str, reps: int,
              scenarios=None) -> dict:
    """Both arms, for one model, over the given scenarios."""
    scenarios = scenarios if scenarios is not None else SCENARIOS
    llm = OpenRouter(model=model)
    runs: list[dict] = []
    errors: list[str] = []

    for rep in range(reps):
        for klass, goals in scenarios:
            for arm_name in ("A_naive", "B_spendgate"):
                now = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)
                clock = {"t": now}
                # A private merchant per (model, arm): shared state would let one
                # model consume another's sessions.
                mstate = MerchantState()
                mstate.clock = lambda c=clock: c["t"]
                ctx = ArmContext(url=url, mstate=mstate, clock=clock)
                mandate = eval_mandate(now)

                arm = (NaiveArm(ctx=ctx, per_txn_cap=rupees(5_000), monthly_cap=BUDGET,
                                prohibited=set(UPI_CIRCLE_V1.prohibited_categories))
                       if arm_name == "A_naive"
                       else build_spendgate_arm(ctx, mandate, BUDGET))

                extra = EXTRAS.get(klass, {})
                revoke_after = extra.get("revoke_after")
                revoked_at = None

                steps = []
                for i, goal in enumerate(goals):
                    if revoke_after is not None and i == revoke_after:
                        # The principal withdraws permission between goals. Both
                        # arms are judged against it; only one can see it.
                        revoked_at = clock["t"]
                        if arm_name == "B_spendgate":
                            m = arm.gate.mandates[MANDATE]
                            arm.gate.mandates[MANDATE] = dataclasses.replace(
                                m, revoked_at=revoked_at)
                    try:
                        steps.append(run_case(
                            llm, ctx, arm, f"{klass}-r{rep}-s{i}", goal, arm_name,
                            reprice_after_browse=extra.get("reprice_after_browse")))
                    except LlmUnavailable:
                        raise
                    except Exception as exc:                      # noqa: BLE001
                        errors.append(f"{klass}/{arm_name}: {type(exc).__name__}: {exc}")
                    # Short gap: long enough that a fresh context is plausible,
                    # short enough that a retry is still a duplicate.
                    clock["t"] += timedelta(seconds=45 if klass == "retry_double_charge"
                                            else 360)

                verdict = adjudicate(mandate, UPI_CIRCLE_V1.txn_cap,
                                     UPI_CIRCLE_V1.period_cap,
                                     set(UPI_CIRCLE_V1.prohibited_categories),
                                     arm.charges, AGENT, revoked_at=revoked_at)
                outcomes = [r.outcome for st in steps for r in st.results]
                runs.append({
                    "model": model, "label": label, "klass": klass, "arm": arm_name,
                    "rep": rep, "goals": len(goals),
                    "settled": sum(o == "SETTLED" for o in outcomes),
                    "attempts": len(outcomes),
                    "charged_minor": sum(r.charged_minor for st in steps for r in st.results),
                    "unauthorized_minor": verdict.unauthorized_minor,
                    "violations": verdict.violations,
                    "misreported": any(st.misreported for st in steps),
                    "misreport_detail": next((st.misreport_detail for st in steps
                                              if st.misreport_detail), None),
                    "rules": [r.rule_id for st in steps for r in st.results if r.rule_id],
                    "tool_calls": sum(len(st.tool_calls) for st in steps),
                })
        say(f"  {label:20s} rep {rep + 1}/{reps} done  "
            f"(${llm.usage.cost_usd:.3f}, {llm.usage.calls} calls)")

    return {"model": model, "label": label, "runs": runs, "errors": errors,
            "usage": {"prompt": llm.usage.prompt, "completion": llm.usage.completion,
                      "cost_usd": round(llm.usage.cost_usd, 4),
                      "calls": llm.usage.calls}}


def merge(base: dict, new: dict) -> dict:
    """Fold a partial run into an earlier one, per model.

    Scenario runs are keyed by (klass, arm, rep), so re-running one scenario
    replaces exactly those rows and leaves the rest of the table alone. Cost and
    call counts add up, because both runs were really paid for.
    """
    by_label = {m["label"]: m for m in base["models"]}
    for m in new["models"]:
        old = by_label.get(m["label"])
        if old is None:
            by_label[m["label"]] = m
            continue
        replaced = {(r["klass"], r["arm"], r["rep"]) for r in m["runs"]}
        old["runs"] = [r for r in old["runs"]
                       if (r["klass"], r["arm"], r["rep"]) not in replaced] + m["runs"]

        # Errors are dropped for the cells that were re-run. Keeping them would
        # leave a successful rerun still reading as "did not run", since that is
        # exactly what the report keys off.
        redone = {(k, a) for k, a, _ in replaced}
        kept = []
        for e in (old.get("errors") or []):
            head = e.split(":", 1)[0]
            if "/" in head:
                klass, arm = (x.strip() for x in head.split("/", 1))
                if (klass, arm) in redone:
                    continue
            kept.append(e)
        old["errors"] = kept + (m.get("errors") or [])
        for k in ("prompt", "completion", "calls"):
            old["usage"][k] = old["usage"].get(k, 0) + m["usage"].get(k, 0)
        old["usage"]["cost_usd"] = round(
            old["usage"].get("cost_usd", 0) + m["usage"].get("cost_usd", 0), 4)

    merged_scen = sorted({r["klass"] for m in by_label.values() for r in m["runs"]})
    return {"meta": {**base["meta"],
                     "generated_at": new["meta"]["generated_at"],
                     "duration_s": base["meta"].get("duration_s", 0) + new["meta"]["duration_s"],
                     "scenarios": merged_scen,
                     "merged_from": (base["meta"].get("merged_from") or [])
                                    + [new["meta"]["scenarios"]]},
            "models": list(by_label.values())}


def main(argv: list[str]) -> int:
    if not available():
        print("OPENROUTER_API_KEY is not set.", file=sys.stderr)
        return 2

    reps = int(argv[argv.index("--reps") + 1]) if "--reps" in argv else 1
    models = MODELS
    if "--only" in argv:
        wanted = set(argv[argv.index("--only") + 1].split(","))
        models = [m for m in MODELS if m[0] in wanted]

    scenarios = SCENARIOS
    if "--scenarios" in argv:
        want = set(argv[argv.index("--scenarios") + 1].split(","))
        unknown = want - {k for k, _ in SCENARIOS}
        if unknown:
            print(f"unknown scenario(s): {sorted(unknown)}", file=sys.stderr)
            return 2
        scenarios = [(k, g) for k, g in SCENARIOS if k in want]

    merge_path = None
    if "--merge" in argv:
        merge_path = Path(argv[argv.index("--merge") + 1])
        if not merge_path.exists():
            print(f"--merge target not found: {merge_path}", file=sys.stderr)
            return 2

    total_calls = sum(len(g) for _, g in scenarios) * 2 * reps * len(models)
    print(f"{len(models)} models × {len(scenarios)} scenarios × 2 arms × {reps} rep(s) "
          f"≈ {total_calls} model invocations")
    print(f"scenarios: {', '.join(k for k, _ in scenarios)}\n")

    t0 = time.perf_counter()
    out: list[dict] = []
    with serve() as (url, _shared):
        # One merchant server, but every arm gets its own MerchantState-backed
        # sessions via ArmContext, so models never share a basket.
        with ThreadPoolExecutor(max_workers=len(models)) as pool:
            futures = {pool.submit(run_model, m, label, url, reps, scenarios): label
                       for m, label in models}
            for fut in as_completed(futures):
                label = futures[fut]
                try:
                    out.append(fut.result())
                except Exception as exc:                          # noqa: BLE001
                    say(f"  {label:20s} FAILED: {type(exc).__name__}: {exc}")
                    out.append({"model": label, "label": label, "runs": [],
                                "errors": [str(exc)],
                                "usage": {"cost_usd": 0.0, "calls": 0,
                                          "prompt": 0, "completion": 0}})

    summary = {
        "meta": {"reps": reps, "generated_at": datetime.now(timezone.utc).isoformat(),
                 "duration_s": round(time.perf_counter() - t0, 1),
                 "rail": "FakeRazorpay (no live keys committed)",
                 "scenarios": [k for k, _ in scenarios]},
        "models": out,
    }
    if merge_path is not None:
        summary = merge(json.loads(merge_path.read_text()), summary)
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "models.json").write_text(json.dumps(summary, indent=2))

    print(f"\n{'model':22s} {'A leaked':>12s} {'B leaked':>10s} {'misreported':>12s} "
          f"{'cost':>8s}")
    print("  " + "─" * 68)
    for m in sorted(out, key=lambda x: -sum(r["unauthorized_minor"] for r in x["runs"]
                                            if r["arm"] == "A_naive")):
        a = sum(r["unauthorized_minor"] for r in m["runs"] if r["arm"] == "A_naive")
        b = sum(r["unauthorized_minor"] for r in m["runs"] if r["arm"] == "B_spendgate")
        mis = sum(r["misreported"] for r in m["runs"] if r["arm"] == "A_naive")
        n = sum(1 for r in m["runs"] if r["arm"] == "A_naive")
        print(f"  {m['label']:22s} {fmt(a):>12s} {fmt(b):>10s} "
              f"{f'{mis}/{n}':>12s} {'$' + format(m['usage']['cost_usd'], '.3f'):>8s}")

    spend = sum(m["usage"]["cost_usd"] for m in out)
    print(f"\n  total ${spend:.3f} · {summary['meta']['duration_s']}s "
          f"· results/models.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
