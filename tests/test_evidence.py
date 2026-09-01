"""Evidence bundle (PRD 13.2)."""

from __future__ import annotations

import json

from conftest import ctx as build_ctx, make_facts, make_mandate
from spendgate import InMemoryLedger, decide, rupees
from spendgate.evidence import build

SECRET = "evidence-key"


def _bundle(**over):
    c = build_ctx(**over)
    ledger = InMemoryLedger()
    ledger.open_account(c.mandate.mandate_id, rupees(15_000))
    d = decide(c)
    return build(authorization_id="aut_1", mandate=c.mandate, facts=c.facts,
                 decision=d, context=c, ledger=ledger, secret=SECRET,
                 agent_transcript="user: buy a speaker\nagent: found one for ₹1,200"), d


def test_bundle_answers_the_three_questions():
    b, d = _bundle()
    p = b.payload
    assert p["mandate"]["mandate_id"], "authorization: what the human signed"
    assert p["resolved_facts"]["facts_hash"], "authenticity: what the merchant asserted"
    assert p["decision"]["outcome"] == d.outcome.value, "accountability: what was decided"


def test_bundle_verifies_offline():
    b, _ = _bundle()
    assert b.verify(SECRET)
    assert not b.verify("wrong-key")


def test_tampering_with_the_payload_breaks_the_signature():
    b, _ = _bundle()
    b.payload["resolved_facts"]["total_minor"] = rupees(1)
    assert not b.verify(SECRET), "an edited bundle must not verify"


def test_rule_trace_covers_every_engine_rule():
    """The decisive rule explains the refusal; the trace proves it was computed."""
    from spendgate import ENGINE_RULES

    b, _ = _bundle(facts=make_facts(total_minor=rupees(9_000)))
    tr = b.payload["decision"]["rule_trace"]
    assert len(tr) == len(ENGINE_RULES)
    assert b.payload["decision"]["reason_code"] == "rail_txn_cap_exceeded"
    assert any(e["rule"] == "R17" and e["fired"] for e in tr)


def test_transcript_is_hashed_not_embedded():
    """A dispute needs proof the transcript has not changed, not its contents."""
    b, _ = _bundle()
    blob = json.dumps(b.payload, default=str)
    assert "buy a speaker" not in blob
    assert len(b.payload["agent_context"]["transcript_sha256"]) == 64
