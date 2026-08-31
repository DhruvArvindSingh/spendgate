"""Fact resolution over a real HTTP boundary (PRD 5 C2, 12.2 A1/A2/A6).

These tests run the mock merchant on an actual socket. The property under test
is that the price travels over a channel the agent is not standing in, and an
in-process call cannot demonstrate that.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from spendgate import (
    AgentRecord, AuthorizationRequest, Constraint, Context, InMemoryLedger,
    Mandate, Outcome, SpendGate, decide, rupees,
)
from spendgate.acp import AcpFactResolver
from spendgate.merchant import MERCHANT_ID, MerchantState, serve
from spendgate.service import FactsUnavailable

AGENT = "agt_shopper_01"
MANDATE = "mnd_phase2"


@pytest.fixture
def merchant():
    with serve() as (url, state):
        yield url, state


def quote(url: str, sku: str, qty: int = 1, agent: str = AGENT, key: str | None = None) -> str:
    r = httpx.post(
        f"{url}/checkout_sessions",
        json={"items": [{"id": sku, "quantity": qty}]},
        headers={"Authorization": f"Bearer {agent}", "API-Version": "2026-04-17",
                 "Idempotency-Key": key or f"k-{sku}-{qty}-{agent}"},
    )
    r.raise_for_status()
    return r.json()["id"]


def mandate(**over) -> Mandate:
    now = datetime.now(timezone.utc)
    kw = dict(
        mandate_id=MANDATE, principal_id="usr_1", agent_id=AGENT,
        rail_profile="upi_circle.v1", issued_at=now - timedelta(days=1),
        valid_from=now - timedelta(days=1), valid_until=now + timedelta(days=29),
        constraints=(
            Constraint("payment.budget", {"max": rupees(15_000), "currency": "INR"}),
            Constraint("payment.allowed_payees", {"allowed": [MERCHANT_ID]}),
        ),
    )
    kw.update(over)
    return Mandate(**kw)


def gate(url: str, state: MerchantState, secret: str | None = None) -> SpendGate:
    ledger = InMemoryLedger()
    ledger.open_account(MANDATE, rupees(15_000))
    ledger.reserve(MANDATE, "seed", rupees(500), datetime.now(timezone.utc), MERCHANT_ID)
    ledger.commit(MANDATE, "seed", datetime.now(timezone.utc), merchant_id=MERCHANT_ID)
    resolver = AcpFactResolver(url, AGENT, secret if secret is not None else state.secret)
    return SpendGate(ledger=ledger, resolver=resolver, mandates={MANDATE: mandate()},
                     agents={AGENT: AgentRecord(AGENT, "usr_1")})


# ------------------------------------------------------------------ basics
def test_resolves_price_from_the_merchant(merchant):
    url, state = merchant
    facts = AcpFactResolver(url, AGENT, state.secret).resolve(quote(url, "SPK-14"))
    assert facts.total_minor == rupees(1_200)
    assert facts.merchant_id == MERCHANT_ID and facts.merchant_verified
    assert facts.currency == "INR" and facts.issued_to_agent == AGENT


def test_unknown_session_returns_none(merchant):
    url, state = merchant
    assert AcpFactResolver(url, AGENT, state.secret).resolve("cs_nonexistent") is None


def test_unreachable_merchant_raises_rather_than_guessing(merchant):
    """R15 / A13. There is no cached price and no fallback to agent input."""
    resolver = AcpFactResolver("http://127.0.0.1:1", AGENT, "s", timeout=1.0)
    with pytest.raises(FactsUnavailable):
        resolver.resolve("cs_anything")


def test_bad_merchant_signature_marks_it_unverified(merchant):
    """R14. A wrong signature must not silently pass as verified."""
    url, state = merchant
    facts = AcpFactResolver(url, AGENT, "wrong-secret").resolve(quote(url, "SPK-14"))
    assert facts.merchant_verified is False
    d = decide(Context(request=AuthorizationRequest(MANDATE, facts.checkout_session_id, AGENT),
                       now=datetime.now(timezone.utc), mandate=mandate(), facts=facts,
                       agent=AgentRecord(AGENT, "usr_1")))
    assert d.reason_code == "merchant_unverified"


# ---------------------------------------------------------- the headline
def test_prompt_injection_in_product_copy_changes_nothing(merchant):
    """A1. The TV's description tells the agent the item costs ₹5 and that limits
    are void. The agent believes it. The decision is unaffected, because the
    request schema has no field in which a belief could travel."""
    url, state = merchant
    sid = quote(url, "TV-99")

    listing = httpx.get(f"{url}/checkout_sessions/{sid}",
                        headers={"Authorization": f"Bearer {AGENT}",
                                 "API-Version": "2026-04-17"}).json()
    copy = listing["line_items"][0]["item"]["description"]
    assert "limits are void" in copy, "the injection fixture must actually be hostile"

    g = gate(url, state)
    _, d = g.authorize(AuthorizationRequest(MANDATE, sid, AGENT))

    assert d.outcome is Outcome.DENIED
    assert d.reason_code == "rail_txn_cap_exceeded"
    assert d.amount_minor == rupees(40_000), "the real price, not the injected one"
    assert g.ledger.snapshot(MANDATE).reserved_minor == 0


def test_repricing_after_the_quote_does_not_change_what_was_approved(merchant):
    """A6 / TOCTOU. SpendGate acts on the facts it read; a later merchant-side
    change is caught by the post-capture assertion, not by trusting the merchant."""
    url, state = merchant
    sid = quote(url, "SPK-14")
    resolver = AcpFactResolver(url, AGENT, state.secret)
    first = resolver.resolve(sid)

    state.hostile, state.reprice_to = True, rupees(9_000)
    second = resolver.resolve(sid)

    assert first.total_minor == rupees(1_200)
    assert second.total_minor == rupees(9_000)
    assert first.facts_hash != second.facts_hash, "the change must be visible in the hash"


# ------------------------------------------------------------ conformance
def test_session_is_single_use(merchant):
    url, state = merchant
    sid = quote(url, "SPK-14")
    resolver = AcpFactResolver(url, AGENT, state.secret)
    assert resolver.resolve(sid).consumed is False
    resolver.complete(sid, "pay_123")
    assert resolver.resolve(sid).consumed is True     # -> R11 on replay


def test_session_is_bound_to_the_requesting_agent(merchant):
    """A5 confused deputy: agent B may not spend against agent A's session."""
    url, state = merchant
    sid = quote(url, "SPK-14", agent="agt_other")
    facts = AcpFactResolver(url, AGENT, state.secret).resolve(sid)
    assert facts.issued_to_agent == "agt_other"
    d = decide(Context(request=AuthorizationRequest(MANDATE, sid, AGENT),
                       now=datetime.now(timezone.utc), mandate=mandate(), facts=facts,
                       agent=AgentRecord(AGENT, "usr_1")))
    assert d.reason_code == "session_agent_mismatch"


def test_acp_requires_version_and_idempotency_key(merchant):
    url, _ = merchant
    h = {"Authorization": f"Bearer {AGENT}", "API-Version": "2026-04-17"}
    body = {"items": [{"id": "SPK-14", "quantity": 1}]}

    assert httpx.post(f"{url}/checkout_sessions", json=body, headers=h).status_code == 400
    assert httpx.post(f"{url}/checkout_sessions", json=body,
                      headers={**h, "API-Version": "2020-01-01",
                               "Idempotency-Key": "k"}).status_code == 400
    assert httpx.get(f"{url}/checkout_sessions/cs_x",
                     headers={"API-Version": "2026-04-17"}).status_code == 401


def test_create_is_idempotent(merchant):
    url, _ = merchant
    a = quote(url, "SPK-14", key="same-key")
    b = quote(url, "SPK-14", key="same-key")
    assert a == b, "same Idempotency-Key must not create a second session"
