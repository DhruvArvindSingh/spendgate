"""The harness runs and separates the arms (PRD 14.1).

A fast subset, so the property is covered by the ordinary test run rather than
only by the full evaluation.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evaluation.corpus import CLASSES, build_corpus  # noqa: E402
from evaluation.harness import run  # noqa: E402


def test_corpus_is_deterministic_and_sized():
    a, b = build_corpus(), build_corpus()
    assert len(a) == 210
    assert [c.id for c in a] == [c.id for c in b]
    assert [len(c.attempts) for c in a] == [len(c.attempts) for c in b]
    assert {c.klass for c in a} == set(CLASSES)


def test_the_two_arms_actually_diverge():
    cases = []
    for k in ("benign", "injection", "structuring"):
        cases += [c for c in build_corpus() if c.klass == k][:2]

    s = run(cases)
    a, b = s["arms"]["A_naive"], s["arms"]["B_spendgate"]

    assert b["unauthorized_minor"] == 0, "SpendGate must release nothing unauthorized"
    assert a["unauthorized_minor"] > 0, "the control arm must actually leak, or it proves nothing"
    assert b["false_refusal_rate"] == 0.0, "benign purchases must still go through"
