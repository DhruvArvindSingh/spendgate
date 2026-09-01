#!/usr/bin/env python3
"""Drive the full SpendGate pipeline against LIVE Razorpay test mode.

    python scripts/live_rail_check.py

Everything except the customer's tap is real: a real mock-ACP merchant on a real
socket, a real decision, a real reservation, and a real order created at
api.razorpay.com under test credentials.

What this proves that the fake cannot: that the order Razorpay records carries
the amount SpendGate read from the merchant — not one the agent supplied — and
that a refused decision creates nothing at the rail at all.

Test mode only. No real money moves; the rail adapter refuses any key that is
not rzp_test_*. Nothing is emailed or texted to anyone.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import httpx  # noqa: E402

from spendgate import (  # noqa: E402
    AgentRecord, AuthorizationRequest, Constraint, InMemoryLedger, Mandate,
    Outcome, SpendGate, fmt, rupees,
)
from spendgate.acp import AcpFactResolver  # noqa: E402
from spendgate.dotenv import find_and_load  # noqa: E402
from spendgate.merchant import MERCHANT_ID, serve  # noqa: E402
from spendgate.rail import RailError, RazorpayRail  # noqa: E402
from spendgate.settlement import AuthState, Authorization, Settlement  # noqa: E402

AGENT, MANDATE = "agt_shopper_01", "mnd_live"
B, D, OK, BAD, WARN, END = "\033[1m", "\033[2m", "\033[32m", "\033[31m", "\033[33m", "\033[0m"


def step(n, title):
    print(f"\n{B}{n} · {title}{END}\n{D}{'─' * 72}{END}")


def check(passed, message):
    print(f"  {OK + '✓' if passed else BAD + '✗'}{END} {message}")
    return passed


def main() -> int:
    import os

    find_and_load(ROOT)
    kid, secret = os.environ.get("RAZORPAY_KEY_ID"), os.environ.get("RAZORPAY_KEY_SECRET")
    if not kid or not secret:
        print("RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET not set (see .env.example)",
              file=sys.stderr)
        return 2

    try:
        rail = RazorpayRail(key_id=kid, key_secret=secret)
    except ValueError as exc:
        print(f"{BAD}{exc}{END}", file=sys.stderr)
        return 2

    print(f"\n{B}SpendGate — live rail check{END}")
    print(f"{D}api.razorpay.com · test mode · {kid[:14]}…{END}")

    results: list[bool] = []
    now = datetime.now(timezone.utc)

    with serve() as (url, mstate):
        ledger = InMemoryLedger()
        ledger.open_account(MANDATE, rupees(15_000))
        earlier = now - timedelta(hours=3)
        ledger.reserve(MANDATE, "seed", rupees(500), earlier, MERCHANT_ID)
        ledger.commit(MANDATE, "seed", earlier, merchant_id=MERCHANT_ID)

        gate = SpendGate(
            ledger=ledger,
            resolver=AcpFactResolver(url, AGENT, mstate.secret),
            mandates={MANDATE: Mandate(
                mandate_id=MANDATE, principal_id="usr_live", agent_id=AGENT,
                rail_profile="upi_circle.v1", issued_at=earlier,
                valid_from=earlier, valid_until=now + timedelta(days=29),
                constraints=(
                    Constraint("payment.budget", {"max": rupees(15_000), "currency": "INR"}),
                    Constraint("payment.allowed_payees", {"allowed": [MERCHANT_ID]}),
                ))},
            agents={AGENT: AgentRecord(AGENT, "usr_live")},
        )
        settle = Settlement(ledger=ledger, rail=rail)

        def quote(sku):
            r = httpx.post(f"{url}/checkout_sessions",
                           json={"items": [{"id": sku, "quantity": 1}]},
                           headers={"Authorization": f"Bearer {AGENT}",
                                    "API-Version": "2026-04-17",
                                    "Idempotency-Key": f"live-{sku}-{now.timestamp()}"})
            r.raise_for_status()
            return r.json()["id"]

        # ---------------------------------------------------------------
        step(1, "A refused decision must not reach the rail")
        before = len(rail._call("GET", "/orders", params={"count": 100}).get("items", []))
        sid_big = quote("TV-99")                       # ₹40,000, over the ₹5,000 cap
        _, refused = gate.authorize(AuthorizationRequest(MANDATE, sid_big, AGENT))
        print(f"  decision: {refused.outcome.value} ({refused.rule_id}) — {refused.reason_text}")
        after = len(rail._call("GET", "/orders", params={"count": 100}).get("items", []))
        results.append(check(refused.outcome is Outcome.DENIED, "refused before the rail"))
        results.append(check(before == after,
                             f"no order created at Razorpay ({before} before, {after} after)"))

        # ---------------------------------------------------------------
        step(2, "An approved decision creates a real order")
        sid = quote("SPK-14")                          # ₹1,200
        _, decision = gate.authorize(AuthorizationRequest(MANDATE, sid, AGENT))
        print(f"  decision: {decision.outcome.value} for {fmt(decision.amount_minor)}")
        if decision.outcome is not Outcome.APPROVED:
            print(f"  {BAD}unexpected: {decision.reason_text}{END}")
            return 1

        auth = settle.execute(Authorization(f"{MANDATE}:{sid}", MANDATE, sid,
                                            decision.amount_minor, MERCHANT_ID, sku="SPK-14"))
        results.append(check(auth.state is AuthState.EXECUTING,
                             f"order created: {auth.order_id}"))

        # ---------------------------------------------------------------
        step(3, "Razorpay's record carries the amount SpendGate read")
        order = rail._call("GET", f"/orders/{auth.order_id}")
        print(f"  razorpay amount   {fmt(order['amount'])}   status {order['status']}")
        print(f"  merchant said     {fmt(decision.amount_minor)}")
        print(f"  receipt           {order['receipt']}")
        results.append(check(order["amount"] == decision.amount_minor,
                             "the amount at the rail is the merchant's, not the agent's"))
        results.append(check(order["receipt"] == auth.auth_id,
                             "the authorization id is the recovery handle (BUGS.md §2 path)"))
        results.append(check(order["notes"].get("checkout_session_id") == sid,
                             "the order is traceable back to the checkout session"))

        # ---------------------------------------------------------------
        step(4, "A payable link, so the capture path can be completed by hand")
        try:
            link = rail.create_payment_link(
                decision.amount_minor, "SpendGate live rail check — desk speaker",
                {"mandate_id": MANDATE, "authorization_id": auth.auth_id},
                reference_id=auth.auth_id)
            print(f"  {link['short_url']}")
            print(f"  {D}open it, pay with any test card / success@razorpay UPI,{END}")
            print(f"  {D}then re-run with the payment id to exercise settlement.{END}")
            results.append(check(link["amount"] == decision.amount_minor,
                                 "the link is bound to the approved amount"))
            results.append(check(link["notify"]["sms"] is False
                                 and link["notify"]["email"] is False,
                                 "no notification was sent to anyone"))
        except RailError as exc:
            print(f"  {WARN}payment link unavailable on this account: {exc}{END}")

        # ---------------------------------------------------------------
        step(5, "The ledger reflects a held, unspent reservation")
        snap = ledger.snapshot(MANDATE)
        print(f"  settled {fmt(snap.settled_minor)}   reserved {fmt(snap.reserved_minor)}"
              f"   available {fmt(ledger.available(MANDATE))}")
        results.append(check(snap.reserved_minor == decision.amount_minor,
                             "budget is held, not yet spent — nothing captured"))
        ledger.check_invariant(MANDATE)
        results.append(check(True, "ledger invariant holds against the live rail"))

        # ---------------------------------------------------------------
        step(6, "Reconciling an order nobody has paid")
        auth.to(AuthState.INDETERMINATE, "simulated lost webhook")
        auth = settle.reconcile(auth.auth_id)
        print(f"  inside the TTL -> {auth.state.value}")
        print(f"  {D}{auth.history[-1][1]}{END}")
        results.append(check(auth.state is AuthState.INDETERMINATE,
                             "held while the order is still payable"))
        results.append(check(ledger.snapshot(MANDATE).reserved_minor == decision.amount_minor,
                             "budget stays reserved, not released"))

        # Razorpay orders never expire, so the timeout is ours. Fast-forward it.
        settle.clock = lambda: datetime.now(timezone.utc) + timedelta(
            seconds=settle.reservation_ttl_seconds + 60)
        auth.to(AuthState.INDETERMINATE, "retry after the TTL")
        auth = settle.reconcile(auth.auth_id)
        print(f"  past the TTL   -> {auth.state.value}")
        results.append(check(auth.state is AuthState.ABANDONED,
                             "reservation released once the TTL passes"))
        results.append(check(ledger.available(MANDATE) == rupees(15_000) - rupees(500),
                             f"budget returned: {fmt(ledger.available(MANDATE))}"))
        results.append(check(any("remains payable" in a for a in settle.anomalies),
                             "and the still-live order is flagged, not forgotten"))
        ledger.check_invariant(MANDATE)

    passed = sum(results)
    print(f"\n{D}{'─' * 72}{END}")
    print(f"  {OK if passed == len(results) else BAD}{passed}/{len(results)} checks passed{END}"
          f"   {D}against live Razorpay test mode{END}\n")
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "live_rail.json").write_text(json.dumps({
        "checked_at": now.isoformat(), "mode": "test",
        "checks_passed": passed, "checks_total": len(results),
        "order_id": auth.order_id, "order_amount_minor": order["amount"],
        "approved_amount_minor": decision.amount_minor,
        "note": ("Live Razorpay test mode. Capture requires a human to open the "
                 "payment link, so settlement is exercised against the fake rail "
                 "in the test suite, not here."),
    }, indent=2))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
