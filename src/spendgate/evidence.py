"""Dispute evidence bundle (PRD 13.2).

The artifact that does not exist today when a person says "I never agreed to
that" about something their agent bought — which is why merchants currently
absorb that loss.

Answers AP2's three questions in one signed object: authorization (what the
principal signed), authenticity (what the merchant asserted, independently
fetched), and accountability (what was decided, by which rule, and what the
rail actually captured).
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .engine import trace
from .models import Context, Decision, Mandate, Outcome, ResolvedFacts
from .money import fmt


def canonical(obj: Any) -> str:
    """Sorted-key, whitespace-free JSON. Approximates RFC 8785; see ledger.py."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _mandate_json(m: Mandate) -> dict:
    return {
        "mandate_id": m.mandate_id,
        "vct": m.vct,
        "principal_id": m.principal_id,
        "agent_id": m.agent_id,
        "rail_profile": m.rail_profile,
        "issued_at": m.issued_at,
        "valid_from": m.valid_from,
        "valid_until": m.valid_until,
        "revoked_at": m.revoked_at,
        "constraints": [{"type": c.type, **c.params} for c in m.constraints],
    }


@dataclass
class EvidenceBundle:
    payload: dict
    signature: str

    def to_json(self, indent: int = 2) -> str:
        return json.dumps({"payload": self.payload, "bundle_signature": {
            "alg": "HS256", "kid": "spendgate-key-1", "value": self.signature}},
            indent=indent, default=str)

    def verify(self, secret: str) -> bool:
        expected = hmac.new(secret.encode(), canonical(self.payload).encode(),
                            hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, self.signature)


def build(
    *,
    authorization_id: str,
    mandate: Mandate,
    facts: ResolvedFacts,
    decision: Decision,
    context: Context,
    ledger,
    secret: str,
    settlement: dict | None = None,
    escalation: dict | None = None,
    agent_transcript: str | None = None,
) -> EvidenceBundle:
    anchored, anchor_note = (ledger.verify_against_anchor(mandate.mandate_id)
                             if hasattr(ledger, "verify_against_anchor") else (False, "n/a"))
    entries = [e for e in ledger.entries(mandate.mandate_id)
               if e.authorization_id in (authorization_id, f"{mandate.mandate_id}:{facts.checkout_session_id}")]
    chain_ok, bad = ledger.verify_chain(mandate.mandate_id)

    payload = {
        "authorization_id": authorization_id,
        "generated_at": datetime.now(timezone.utc),

        # What the human authorised.
        "mandate": _mandate_json(mandate),

        # What the agent did. The transcript is hashed rather than embedded:
        # a dispute needs proof it has not changed, not the contents.
        "agent_context": {
            "agent_id": context.request.agent_id,
            "requested_at": context.now,
            "transcript_sha256": (
                hashlib.sha256(agent_transcript.encode()).hexdigest()
                if agent_transcript else None),
        },

        # What the merchant asserted, fetched server-to-server.
        "resolved_facts": {
            "checkout_session_id": facts.checkout_session_id,
            "merchant_id": facts.merchant_id,
            "merchant_verified": facts.merchant_verified,
            "total_minor": facts.total_minor,
            "total_display": fmt(facts.total_minor),
            "currency": facts.currency,
            "category": facts.category,
            "line_items": [{"sku": i.sku, "qty": i.qty, "unit_minor": i.unit_minor}
                           for i in facts.line_items],
            "resolved_at": facts.resolved_at,
            "facts_hash": facts.facts_hash,
        },

        # What was decided, and — crucially — every rule that was evaluated.
        # The decisive rule explains the outcome; the full trace proves the
        # decision was computed rather than reconstructed afterwards.
        "decision": {
            "outcome": decision.outcome.value,
            "reason_code": decision.reason_code,
            "reason_text": decision.reason_text,
            "rule_id": decision.rule_id,
            "rules_evaluated": decision.rules_evaluated,
            "overridable": decision.overridable,
            "decided_at": decision.decided_at,
            "rule_trace": [{"rule": r, "fired": f} for r, f in trace(context)],
        },
        "escalation": escalation,
        "settlement": settlement,

        # Where this sits in the ledger. chain_valid alone is internal
        # consistency; a rewrite that repaired every prev_hash would still pass
        # it. `anchored` is the claim that survives a competent attacker.
        "ledger": {
            "entries": [{"seq": e.seq, "kind": e.kind.value, "amount_minor": e.amount_minor,
                         "at": e.at, "hash": e.hash, "prev_hash": e.prev_hash}
                        for e in entries],
            "chain_valid": chain_ok,
            "first_bad_seq": bad,
            "anchored": anchored,
            "anchor_note": anchor_note,
        },
    }
    signature = hmac.new(secret.encode(), canonical(payload).encode(),
                         hashlib.sha256).hexdigest()
    return EvidenceBundle(payload=payload, signature=signature)
