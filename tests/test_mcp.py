"""MCP tool surface (PRD 10.4).

The point of these tests is the schema, not the plumbing: an agent connected
over MCP must have no way to name an amount.
"""

from __future__ import annotations

import io
import json

import pytest

from spendgate.mcp_server import TOOLS, SpendGateMCP


@pytest.fixture
def mcp(monkeypatch):
    from test_service import build          # reuse the Phase 1 service fixture

    gate = build()
    return SpendGateMCP(gate=gate, agent_id="agt_shopper_01", default_mandate="mnd_01J9F2K7")


def call(mcp, name, **args):
    r = mcp.dispatch({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                      "params": {"name": name, "arguments": args}})
    return json.loads(r["result"]["content"][0]["text"])


# --------------------------------------------------------- the boundary
def test_request_payment_has_no_amount_parameter():
    """The schema is the security boundary. If an amount field ever appears
    here, an agent can express a lie and this test is the tripwire."""
    tool = next(t for t in TOOLS if t["name"] == "request_payment")
    props = set(tool["inputSchema"]["properties"])
    assert props == {"checkout_session_id"}
    assert tool["inputSchema"]["additionalProperties"] is False, \
        "extra properties must be rejected, not ignored"


def test_extra_arguments_are_refused(mcp):
    r = mcp.dispatch({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                      "params": {"name": "request_payment",
                                 "arguments": {"checkout_session_id": "cs_8fK2mNp",
                                               "amount": 500}}})
    assert "error" in r and r["error"]["code"] == -32602


# ------------------------------------------------------------ behaviour
def test_request_payment_approves_within_mandate(mcp):
    out = call(mcp, "request_payment", checkout_session_id="cs_8fK2mNp")
    assert out["outcome"] == "APPROVED"
    assert out["amount"] == "₹1,200.00"


def test_refusal_tells_the_agent_not_to_retry(mcp):
    mcp.gate.resolver.sessions["cs_big"] = __import__(
        "test_service", fromlist=["make_facts"]).make_facts(
        checkout_session_id="cs_big", total_minor=620_000)
    out = call(mcp, "request_payment", checkout_session_id="cs_big")
    assert out["outcome"] == "DENIED"
    assert out["rule"] == "R17"
    assert "different purchase" in out["next"]


def test_check_budget_and_list_mandates(mcp):
    b = call(mcp, "check_budget", mandate_id="mnd_01J9F2K7")
    assert b["available"].startswith("₹")
    m = call(mcp, "list_mandates")
    assert m["mandates"] and m["mandates"][0]["mandate_id"] == "mnd_01J9F2K7"


# -------------------------------------------------------------- protocol
def test_initialize_and_tools_list(mcp):
    init = mcp.dispatch({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {}})
    assert init["result"]["serverInfo"]["name"] == "spendgate"
    assert init["result"]["protocolVersion"] == "2025-11-05"
    listed = mcp.dispatch({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert {t["name"] for t in listed["result"]["tools"]} == {
        "request_payment", "check_budget", "list_mandates"}


def test_notifications_get_no_reply(mcp):
    assert mcp.dispatch({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_serves_over_stdio(mcp):
    lines = [json.dumps({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {}}),
             json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
             json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})]
    out = io.StringIO()
    mcp.serve(stdin=io.StringIO("\n".join(lines) + "\n"), stdout=out)
    replies = [json.loads(x) for x in out.getvalue().strip().split("\n")]
    assert len(replies) == 2, "the notification must not produce a reply"
    assert replies[1]["result"]["tools"]
