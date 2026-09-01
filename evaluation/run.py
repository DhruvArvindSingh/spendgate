#!/usr/bin/env python3
"""Run the corpus against both arms and write results/.

    python -m evaluation.run [--quick]

Raw output is committed so every number in the README is traceable to a file
anyone can re-run.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from evaluation.corpus import SEED, build_corpus  # noqa: E402
from evaluation.harness import run  # noqa: E402

RESULTS = Path(__file__).resolve().parent.parent / "results"


def fmt(minor: int) -> str:
    return f"₹{minor / 100:,.2f}"


def main(argv: list[str]) -> int:
    quick = "--quick" in argv
    cases = build_corpus()
    if quick:
        seen: dict[str, int] = {}
        picked = []
        for c in cases:
            if seen.get(c.klass, 0) < 3:
                picked.append(c)
                seen[c.klass] = seen.get(c.klass, 0) + 1
        cases = picked

    print(f"Running {len(cases)} cases × 2 arms (seed {SEED})…")
    t0 = time.perf_counter()
    summary = run(cases, verbose=True)
    summary["meta"] = {
        "seed": SEED,
        "cases": len(cases),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rail": "FakeRazorpay (no live keys committed)",
        "agent": "ScriptedAdversary (deterministic; see README)",
        "duration_s": round(time.perf_counter() - t0, 2),
    }

    RESULTS.mkdir(exist_ok=True)
    name = "quick" if quick else "full"
    (RESULTS / f"{name}.json").write_text(json.dumps(summary, indent=2, default=str))

    a, b = summary["arms"]["A_naive"], summary["arms"]["B_spendgate"]
    print(f"\n{'':22s} {'Arm A (naive)':>18s} {'Arm B (SpendGate)':>20s}")
    print("  " + "─" * 60)
    print(f"  {'unauthorized':20s} {fmt(a['unauthorized_minor']):>18s} "
          f"{fmt(b['unauthorized_minor']):>20s}")
    print(f"  {'hostile contained':20s} "
          f"{a['hostile_contained']}/{a['hostile_cases']:<16} "
          f"{b['hostile_contained']}/{b['hostile_cases']:<18}")
    print(f"  {'false refusal':20s} {a['false_refusal_rate']:>18.1%} "
          f"{b['false_refusal_rate']:>20.1%}")
    print(f"  {'p95 latency':20s} {str(a['latency_ms_p50']) + ' ms':>18s} "
          f"{str(b['latency_ms_p95']) + ' ms':>20s}")
    print(f"\n  escalations (Arm B): {summary['escalations_arm_b']}")
    print(f"  written: results/{name}.json  ({summary['meta']['duration_s']}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
