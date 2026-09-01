"""Rule coverage (PRD 14.3: "37 / 37 rules with >=1 test that trips them").

This is a manifest, not a heuristic. Adding a rule without adding a test that
trips it fails the suite, which is the whole reason the registry is data.
"""

from __future__ import annotations

from test_rules import CASES

from spendgate import ENGINE_RULES, REGISTRY
from pathlib import Path

from spendgate.models import Layer

#: Rules enforced outside the pure engine, mapped to the test that trips each.
OUT_OF_ENGINE = {
    "R25": "test_service.py::test_replay_returns_the_stored_result",
    "R26": "test_service.py::test_same_key_different_body_conflicts",
    "R27": "test_service.py::test_in_flight_key_is_rejected_with_retry",
    "R29": "test_service.py::test_lock_contention_maps_to_a_retryable_refusal",
    "R38": "test_escalation.py::test_flooding_the_principal_is_refused_not_approved",
}


def test_every_rule_in_the_registry_has_a_test():
    covered = {c[0] for c in CASES} | set(OUT_OF_ENGINE)
    missing = {r.id for r in REGISTRY} - covered
    assert not missing, f"rules with no test that trips them: {sorted(missing)}"
    assert len(covered) == len(REGISTRY)


def test_the_manifest_matches_the_registry_layers():
    """Nothing may claim engine enforcement while being tested elsewhere."""
    declared = {r.id for r in REGISTRY if r.layer is not Layer.ENGINE}
    assert declared == set(OUT_OF_ENGINE), (
        f"layer drift: registry says {sorted(declared)}, manifest says {sorted(OUT_OF_ENGINE)}"
    )
    assert {c[0] for c in CASES} == {r.id for r in ENGINE_RULES}


def test_no_duplicate_reason_codes():
    codes = [r.reason_code for r in REGISTRY]
    assert len(codes) == len(set(codes))


def test_registry_order_is_evaluation_order():
    """Stages must not interleave: a fact check can never run before identity."""
    order = ["identity", "facts", "rails", "concurrency", "policy"]
    seen = [r.stage for r in REGISTRY]
    assert seen == sorted(seen, key=order.index), "registry order drifted from stage order"


def test_the_rule_count_is_derived_not_hardcoded():
    """A literal count in three files is how documentation drifts from code."""
    from spendgate.rules import RULE_COUNT

    assert RULE_COUNT == len(REGISTRY)
    src = (Path(__file__).resolve().parent.parent / "src" / "spendgate" / "rules.py").read_text()
    assert "== 37" not in src and "== 38" not in src, "count must not be asserted against a literal"
