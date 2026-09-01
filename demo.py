#!/usr/bin/env python3
"""SpendGate — end-to-end walkthrough.

    python demo.py

Runs the real thing: a mock ACP merchant on an actual socket, the fact resolver
fetching prices over HTTP, the 37-rule engine, the budget ledger, and the
settlement state machine driving a stubbed Razorpay.

The rail is stubbed because live test-mode keys are not committed. Everything
else — the merchant, the socket, the signatures, the ledger — is real.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "src")

from spendgate import (  # noqa: E402
    AgentRecord, AuthorizationRequest, Constraint, InMemoryLedger, Mandate,
    Outcome, SpendGate, fmt, rupees,
)
from spendgate.acp import AcpFactResolver
from spendgate.ledger import InMemoryAnchor  # noqa: E402
from spendgate.merchant import CATALOG, MERCHANT_ID, serve  # noqa: E402
from spendgate.rail import FakeRazorpay  # noqa: E402
from spendgate.settlement import AuthState, Authorization, Settlement  # noqa: E402
from spendgate.webhooks import EventDeduplicator, receive, sign  # noqa: E402

import httpx  # noqa: E402

AGENT, MANDATE, SECRET = "agt_shopper_01", "mnd_demo", "whsec_demo"
B, D, G, Y, R, E = "\033[1m", "\033[2m", "\033[32m", "\033[33m", "\033[31m", "\033[0m"
MARK = {Outcome.APPROVED: (G, "APPROVED"), Outcome.ESCALATED: (Y, "ASK OWNER"),
        Outcome.DENIED: (R, "REFUSED"), Outcome.REPLAYED: (D, "REPLAYED")}


def head(title):
    print(f"\n{B}{title}{E}\n{D}{'─' * 76}{E}")


def show(label, d):
    colour, word = MARK[d.outcome]
    print(f"  {label:<32} {colour}{word:<10}{E} {D}{(d.rule_id or '—'):>4}{E}  {d.reason_text}")


class Demo:
    def __init__(self, url, mstate):
        self.clock = {"t": datetime.now(timezone.utc)}
        mstate.clock = lambda: self.clock["t"]      # one clock for the whole demo
        self.ledger = InMemoryLedger(anchor=InMemoryAnchor())
        self.ledger.open_account(MANDATE, rupees(15_000))
        earlier = self.clock["t"] - timedelta(hours=2)
        self.ledger.reserve(MANDATE, "seed", rupees(500), earlier, MERCHANT_ID)
        self.ledger.commit(MANDATE, "seed", earlier, merchant_id=MERCHANT_ID)

        now = self.clock["t"]
        self.gate = SpendGate(
            ledger=self.ledger,
            resolver=AcpFactResolver(url, AGENT, mstate.secret),
            mandates={MANDATE: Mandate(
                mandate_id=MANDATE, principal_id="usr_8823", agent_id=AGENT,
                rail_profile="upi_circle.v1", issued_at=now - timedelta(days=1),
                valid_from=now - timedelta(days=1), valid_until=now + timedelta(days=29),
                constraints=(
                    Constraint("payment.budget", {"max": rupees(15_000), "currency": "INR"}),
                    Constraint("payment.allowed_payees", {"allowed": [MERCHANT_ID]}),
                    Constraint("spendgate.aggregate", {"max_amount": rupees(5_000),
                                                       "window_seconds": 3600,
                                                       "group_by": "merchant_id"}),
                ))},
            agents={AGENT: AgentRecord(AGENT, "usr_8823")},
            clock=lambda: self.clock["t"],
        )
        self.url = url
        self.rail = FakeRazorpay()
        self.settle = Settlement(ledger=self.ledger, rail=self.rail,
                                 clock=lambda: self.clock["t"])

    def quote(self, sku, key=None):
        r = httpx.post(f"{self.url}/checkout_sessions",
                       json={"items": [{"id": sku, "quantity": 1}]},
                       headers={"Authorization": f"Bearer {AGENT}",
                                "API-Version": "2026-04-17",
                                "Idempotency-Key": key or f"k-{sku}-{len(self.rail.orders)}"})
        r.raise_for_status()
        return r.json()["id"]

    def ask(self, sku, label, key=None):
        sid = self.quote(sku, key)
        _, d = self.gate.authorize(AuthorizationRequest(MANDATE, sid, AGENT))
        show(label, d)
        return sid, d

    def settle_it(self, sid, d, fail=False, capture=None):
        if d.outcome is not Outcome.APPROVED:
            return None          # nothing was reserved, so there is nothing to settle
        auth = self.settle.execute(
            Authorization(f"{MANDATE}:{sid}", MANDATE, sid, d.amount_minor, MERCHANT_ID))
        if auth.state is not AuthState.EXECUTING:
            return auth
        self.rail.fail_next = fail
        self.rail.capture_amount_override = capture
        payment = self.rail.pay(auth.order_id)
        event = "payment.failed" if fail else "payment.captured"
        body = json.dumps(self.rail.webhook_body(event, payment)).encode()
        parsed = receive(body, {"X-Razorpay-Signature": sign(body, SECRET),
                                "x-razorpay-event-id": f"evt_{payment['id']}"},
                         SECRET, EventDeduplicator())
        return self.settle.on_event(parsed)


def main() -> int:
    with serve() as (url, mstate):
        d = Demo(url, mstate)
        print(f"\n{B}SpendGate{E} — deterministic spending authority for AI agents")
        print(f"{D}merchant {url}  ·  rail upi_circle.v1  ·  {fmt(rupees(5_000))}/txn  ·  "
              f"{fmt(rupees(15_000))}/month{E}")

        # 1 -------------------------------------------------------------
        head("1 · An ordinary purchase, settled through the rail")
        sid, dec = d.ask("SPK-14", "₹1,200 desk speaker")
        auth = d.settle_it(sid, dec)
        print(f"  {D}order {auth.order_id} → payment {auth.payment_id} → "
              f"webhook verified → {G}{auth.state.value}{E}")

        # 2 -------------------------------------------------------------
        head("2 · The agent has been prompt-injected")
        copy = CATALOG["TV-99"]["description"]
        print(f"{D}  The product listing says:{E}")
        print(f"{D}    \"{copy[38:130]}…\"{E}")
        print(f"{D}  The agent reads it and believes it completely.{E}\n")
        _, dec = d.ask("TV-99", "₹40,000 TV, 'priced at ₹5'")
        print(f"  {D}The price came from the merchant over HTTP. The agent had no field")
        print(f"  in which to repeat what it was told, so its belief never mattered.{E}")

        # 3 -------------------------------------------------------------
        d.clock["t"] += timedelta(minutes=90)   # section 1 ages out of the window
        head("3 · Structuring — splitting past the ₹5,000 per-transaction cap")
        sid, dec = d.ask("HP-77", "split 1/3 — ₹4,000", key="s1")
        d.settle_it(sid, dec)
        d.clock["t"] += timedelta(minutes=5)
        d.ask("HP-77", "split 2/3 — ₹4,000", key="s2")
        print(f"  {D}Each split was legal on its own. The assembled pattern was not.")
        print(f"  Escalated, not refused — the owner may genuinely want the item.{E}")

        # Sections 4-6 each get a clean world: the aggregate rule is stateful,
        # so reusing one ledger would have earlier sections shadow later ones.
        # 4 -------------------------------------------------------------
        head("4 · A payment fails")
        d = Demo(url, mstate)
        before = d.ledger.available(MANDATE)
        sid, dec = d.ask("RICE-5", "₹450 rice", key="rice")
        auth = d.settle.execute(
            Authorization(f"{MANDATE}:{sid}", MANDATE, sid, dec.amount_minor, MERCHANT_ID))
        held = d.ledger.available(MANDATE)
        auth = d.settle_it(sid, dec, fail=True) or auth
        print(f"  {D}available  {fmt(before)} → {fmt(held)} (held) → "
              f"{G}{fmt(d.ledger.available(MANDATE))}{E}{D} (returned on {auth.state.value}){E}")

        # 5 -------------------------------------------------------------
        head("5 · A payment times out — outcome unknown")
        d = Demo(url, mstate)
        sid, dec = d.ask("SPK-14", "₹1,200 speaker", key="tmo")
        d.rail.timeout_next = True
        auth = d.settle.execute(
            Authorization(f"{MANDATE}:{sid}", MANDATE, sid, dec.amount_minor, MERCHANT_ID))
        snap = d.ledger.snapshot(MANDATE)
        print(f"  {D}state {Y}{auth.state.value}{E}{D}   reserved {fmt(snap.reserved_minor)}"
              f"   settled {fmt(snap.settled_minor)}{E}")
        print(f"  {D}Neither committed nor released. Releasing would invite a double-spend")
        print(f"  if it settles late; committing would invent a charge.{E}")
        auth = d.settle.reconcile(auth.auth_id)
        print(f"  {D}reconciled inside the TTL → {auth.state.value}{E}")
        d.clock["t"] += timedelta(seconds=d.settle.reservation_ttl_seconds + 60)
        auth.to(AuthState.INDETERMINATE, "retry past the TTL")
        auth = d.settle.reconcile(auth.auth_id)
        print(f"  {D}past the TTL → {auth.state.value}, budget "
              f"{fmt(d.ledger.available(MANDATE))} returned{E}")

        # 6 -------------------------------------------------------------
        head("6 · The merchant captures more than was approved")
        d = Demo(url, mstate)
        sid, dec = d.ask("RICE-5", "₹450 rice", key="mismatch")
        auth = d.settle_it(sid, dec, capture=rupees(9_000))
        print(f"  {D}state {R}{auth.state.value}{E}{D} — not settled, refunded, owner alerted{E}")
        for a in d.settle.anomalies:
            print(f"  {R}!{E} {D}{a}{E}")

        # 7 -------------------------------------------------------------
        head("7 · Rewriting the ledger, and being caught")
        import dataclasses
        entries = d.ledger._acct(MANDATE).entries
        pristine = list(entries)                    # to put the ledger back after
        before = d.ledger.verify_against_anchor(MANDATE)
        print(f"  {D}before        chain {d.ledger.verify_chain(MANDATE)[0]}   "
              f"anchor {before[0]}{E}")
        target = next(i for i, e in enumerate(entries) if e.kind.value == "COMMIT")
        entries[target] = dataclasses.replace(entries[target], amount_minor=rupees(1))
        print(f"  {D}edit entry {entries[target].seq} down to ₹1 …{E}")
        print(f"  {D}chain now {d.ledger.verify_chain(MANDATE)[0]} — a naive edit is caught{E}")
        for i in range(1, len(entries)):
            entries[i] = dataclasses.replace(entries[i], prev_hash=entries[i - 1].hash)
        ok_chain = d.ledger.verify_chain(MANDATE)[0]
        ok_anchor, why = d.ledger.verify_against_anchor(MANDATE)
        print(f"  {D}… then repair every prev_hash link{E}")
        print(f"  chain  {G if ok_chain else R}{ok_chain}{E}  {D}← a hash chain alone is "
              f"not enough{E}")
        print(f"  anchor {G if not ok_anchor else R}{not ok_anchor} caught it{E}  {D}{why}{E}")
        entries[:] = pristine                       # undo the tamper for section 8
        assert d.ledger.verify_against_anchor(MANDATE)[0], "restore failed"

        # 8 -------------------------------------------------------------
        head("8 · The ledger")
        for e in d.ledger.entries(MANDATE):
            print(f"  {e.seq:>3}  {e.kind.value:<8} {fmt(e.amount_minor):>11}  {D}{e.hash[7:19]}…{E}")
        ok, bad = d.ledger.verify_chain(MANDATE)
        s = d.ledger.snapshot(MANDATE)
        print(f"\n  chain {G if ok else R}{'verified' if ok else f'broken at {bad}'}{E}"
              f"   settled {fmt(s.settled_minor)}   reserved {fmt(s.reserved_minor)}"
              f"   available {fmt(d.ledger.available(MANDATE))}")
        d.ledger.check_invariant(MANDATE)
        print(f"  {G}invariant holds{E} {D}— settled + reserved ≤ budget, available ≥ 0, "
              f"chain links{E}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
