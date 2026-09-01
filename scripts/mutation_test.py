#!/usr/bin/env python3
"""Mutation testing: break each safety property, confirm the suite notices.

    python scripts/mutation_test.py

A mutation that SURVIVES — the suite still passes with the property broken —
means nothing actually checks it. Tests written by the same person who wrote the
design share its blind spots; this asks whether the suite can tell the
difference, which is a question the author cannot answer by reading.

This is how BUGS.md §10 was found: the README claimed the ledger detected log
tampering, and it did not.

KNOWN EQUIVALENT MUTANT. "fact resolver trusts a cached price" neuters the
`>= 500` branch in acp.resolve. It survives because the `!= 200` guard below it
raises anyway, so behaviour is unchanged — an equivalent mutant, not a hole. A
genuinely fail-open mutation (fabricating facts on error) is killed by
test_unreachable_merchant_raises_rather_than_guessing. It is kept in the list
because a future edit that removes the second guard would make it non-equivalent,
and then it should start failing.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (name, file, find, replace, what it breaks)
MUTATIONS = [
    ("release does not free budget", "src/spendgate/ledger.py",
     "            a.reserved -= amount\n            return self._append(a, mandate_id, auth_id, EntryKind.RELEASE, amount, at)",
     "            return self._append(a, mandate_id, auth_id, EntryKind.RELEASE, amount, at)",
     "failed payments silently eat budget"),

    ("reserve ignores available budget", "src/spendgate/ledger.py",
     "            if a.budget_max - a.settled - a.reserved < amount:\n                raise InsufficientBudget(mandate_id)",
     "            pass",
     "budget can be oversubscribed"),

    ("hash chain does not link", "src/spendgate/ledger.py",
     "        return \"sha256:\" + hashlib.sha256(\n            (self.prev_hash + self.canonical()).encode()\n        ).hexdigest()",
     "        return \"sha256:\" + hashlib.sha256(self.canonical().encode()).hexdigest()",
     "tampering becomes undetectable"),

    ("engine always approves", "src/spendgate/engine.py",
     "        if fired:",
     "        if False:",
     "every rule is bypassed"),

    ("fact resolver trusts a cached price", "src/spendgate/acp.py",
     "        if r.status_code >= 500:\n            raise FactsUnavailable(f\"merchant returned {r.status_code}\")",
     "        if r.status_code >= 500:\n            pass",
     "fails open instead of closed"),

    ("webhook signature always verifies", "src/spendgate/webhooks.py",
     "    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()\n    return hmac.compare_digest(expected, signature)",
     "    return True",
     "forged webhooks are accepted"),

    ("capture amount is not asserted", "src/spendgate/settlement.py",
     "        if captured != auth.approved_minor:",
     "        if False:",
     "a merchant can capture any amount"),

    ("late failure reopens a settled payment", "src/spendgate/settlement.py",
     "        if auth.state in TERMINAL:\n            # A late failure for a payment that settled must NOT release budget.\n            self._alert(f\"late payment.failed on {auth.state.value} {auth.auth_id}\")\n            return auth",
     "        if False:\n            return auth",
     "out-of-order webhooks corrupt the ledger"),

    ("indeterminate releases its budget", "src/spendgate/settlement.py",
     "                auth.to(AuthState.INDETERMINATE, f\"order timeout: {exc}\")\n                return auth",
     "                auth.to(AuthState.INDETERMINATE, f\"order timeout: {exc}\")\n                self.ledger.release(auth.mandate_id, auth.auth_id, self._now())\n                return auth",
     "unknown outcomes are treated as failures"),

    ("agent request gains an amount field", "src/spendgate/models.py",
     "    mandate_id: str\n    checkout_session_id: str\n    agent_id: str\n    idempotency_key: str | None = None",
     "    mandate_id: str\n    checkout_session_id: str\n    agent_id: str\n    amount: int | None = None\n    idempotency_key: str | None = None",
     "the containment property is gone"),

    ("mcp tool accepts an amount", "src/spendgate/mcp_server.py",
     '                "checkout_session_id": {\n                    "type": "string",\n                    "description": "The opaque session id the merchant issued.",\n                },\n            },\n            "required": ["checkout_session_id"],',
     '                "checkout_session_id": {\n                    "type": "string",\n                    "description": "The opaque session id the merchant issued.",\n                },\n                "amount_paise": {"type": "integer"},\n            },\n            "required": ["checkout_session_id"],',
     "an MCP agent can name a price"),

    ("aggregate rule never fires", "src/spendgate/rules.py",
     '    Rule("R34", "aggregate_pattern", "policy", Kind.POLICY, Outcome.ESCALATED, Layer.ENGINE,\n         lambda c, r: (c.facts is not None and _c(c, "spendgate.aggregate") is not None',
     '    Rule("R34", "aggregate_pattern", "policy", Kind.POLICY, Outcome.ESCALATED, Layer.ENGINE,\n         lambda c, r: (False and c.facts is not None and _c(c, "spendgate.aggregate") is not None',
     "structuring is undetected"),

    ("oracle ignores the aggregate constraint", "evaluation/oracle.py",
     "            if sum(c.amount_minor for c in recent) + ch.amount_minor > aggregate.get(\"max_amount\", 1 << 62):",
     "            if False:",
     "the adjudicator under-counts violations"),

    ("escalation budget never blocks", "src/spendgate/escalation.py",
     "            if len(pending) >= self.max_pending:",
     "            if False:",
     "the principal can be flooded with approval prompts"),

    ("exhausted escalation approves instead of refusing", "src/spendgate/service.py",
     "        allowed, why = self.escalation.check(mandate.principal_id, now)\n        if allowed:",
     "        allowed, why = self.escalation.check(mandate.principal_id, now)\n        if True:",
     "an unshowable prompt is treated as consent"),

    ("answering refunds the window count", "src/spendgate/escalation.py",
     "            self._pending.setdefault(principal_id, set()).discard(authorization_id)",
     "            self._pending.setdefault(principal_id, set()).discard(authorization_id)\n            r = self._raised.get(principal_id)\n            if r:\n                r.pop()",
     "answering fast buys unlimited prompts"),

    ("session single-use check removed", "src/spendgate/rules.py",
     '         lambda c, r: c.facts is not None and c.facts.consumed,',
     '         lambda c, r: False,',
     "replay attacks succeed"),
]


def run_tests():
    r = subprocess.run([sys.executable, "-m", "pytest", "-x", "-q", "--no-header",
                        "-p", "no:cacheprovider"],
                       cwd=ROOT, capture_output=True, text=True, timeout=300)
    return r.returncode == 0, r.stdout


def main():
    survived, killed, skipped = [], [], []
    for name, relpath, find, replace, breaks in MUTATIONS:
        path = ROOT / relpath
        original = path.read_text()
        if find not in original:
            skipped.append((name, "pattern not found"))
            print(f"  SKIP  {name}  (pattern drifted)")
            continue
        path.write_text(original.replace(find, replace, 1))
        try:
            passed, out = run_tests()
        finally:
            path.write_text(original)
        if passed:
            survived.append((name, breaks))
            print(f"  SURVIVED  {name}  -> {breaks}")
        else:
            m = re.search(r"(\d+) failed", out)
            killed.append(name)
            print(f"  killed    {name}  ({m.group(1) if m else '?'} test(s) failed)")

    print(f"\n  killed {len(killed)}/{len(MUTATIONS) - len(skipped)}   "
          f"survived {len(survived)}   skipped {len(skipped)}")
    known_equivalent = {"fact resolver trusts a cached price"}
    real = [(n, b) for n, b in survived if n not in known_equivalent]
    if survived:
        print("\n  survived:")
        for name, breaks in survived:
            tag = "known equivalent mutant" if name in known_equivalent else f"HOLE — {breaks}"
            print(f"    - {name}: {tag}")
    return 1 if real else 0


if __name__ == "__main__":
    sys.exit(main())
