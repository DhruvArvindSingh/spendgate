"""MCP server (PRD 10.4).

Exposes SpendGate as tools so any MCP-capable agent is governed without
modification. The tool schema IS the security boundary: `request_payment` takes
one opaque session id and has no amount parameter, so an agent physically
cannot express what it would need to express in order to lie.

Implemented as a minimal JSON-RPC 2.0 server over stdio rather than through the
`mcp` SDK, to keep the runtime dependency-free. The wire format is the same;
swapping in the official SDK is a drop-in if that becomes preferable.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any, Callable, TextIO

from .models import AuthorizationRequest, Outcome
from .money import fmt

PROTOCOL_VERSION = "2025-11-05"

TOOLS = [
    {
        "name": "request_payment",
        "description": (
            "Request authorization to pay for a merchant checkout session. "
            "You cannot specify an amount: the amount is resolved directly from "
            "the merchant. Returns APPROVED, ESCALATED (a human must approve) "
            "or DENIED with the single rule that refused it."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "checkout_session_id": {
                    "type": "string",
                    "description": "The opaque session id the merchant issued.",
                },
            },
            "required": ["checkout_session_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "check_budget",
        "description": "Remaining spendable budget on a mandate for the current period.",
        "inputSchema": {
            "type": "object",
            "properties": {"mandate_id": {"type": "string"}},
            "required": ["mandate_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_mandates",
        "description": "Mandates available to this agent, with their constraints.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
]


@dataclass
class SpendGateMCP:
    gate: Any                      # spendgate.service.SpendGate
    agent_id: str
    default_mandate: str | None = None

    # ------------------------------------------------------------- tools
    def request_payment(self, checkout_session_id: str) -> dict:
        mandate_id = self.default_mandate or next(iter(self.gate.mandates), None)
        if mandate_id is None:
            return {"outcome": "DENIED", "reason": "no mandate is available to this agent"}
        _, d = self.gate.authorize(
            AuthorizationRequest(mandate_id, checkout_session_id, self.agent_id))
        out: dict[str, Any] = {
            "outcome": d.outcome.value,
            "amount": fmt(d.amount_minor),
            "reason": d.reason_text,
            "rule": d.rule_id,
            "overridable": d.overridable,
        }
        if d.outcome is Outcome.ESCALATED:
            out["next"] = "A human has been asked. Do not retry; wait for their answer."
        elif d.outcome is Outcome.DENIED:
            out["next"] = "This will not succeed on retry. Choose a different purchase."
        return out

    def check_budget(self, mandate_id: str) -> dict:
        try:
            available = self.gate.ledger.available(mandate_id)
            snap = self.gate.ledger.snapshot(mandate_id)
        except KeyError:
            return {"error": f"unknown mandate {mandate_id!r}"}
        return {"available": fmt(available), "settled": fmt(snap.settled_minor),
                "held": fmt(snap.reserved_minor)}

    def list_mandates(self) -> dict:
        return {"mandates": [
            {"mandate_id": m.mandate_id, "rail_profile": m.rail_profile,
             "valid_until": str(m.valid_until),
             "constraints": [{"type": c.type, **c.params} for c in m.constraints]}
            for m in self.gate.mandates.values() if m.agent_id == self.agent_id
        ]}

    # -------------------------------------------------------------- wire
    def handlers(self) -> dict[str, Callable[..., dict]]:
        return {"request_payment": self.request_payment,
                "check_budget": self.check_budget,
                "list_mandates": self.list_mandates}

    def dispatch(self, message: dict) -> dict | None:
        mid, method, params = message.get("id"), message.get("method"), message.get("params", {})

        def ok(result):
            return {"jsonrpc": "2.0", "id": mid, "result": result}

        def err(code, msg):
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": msg}}

        if method == "initialize":
            return ok({"protocolVersion": PROTOCOL_VERSION,
                       "capabilities": {"tools": {}},
                       "serverInfo": {"name": "spendgate", "version": "0.3.0"}})
        if method in ("notifications/initialized", "initialized"):
            return None                                   # notification: no reply
        if method == "tools/list":
            return ok({"tools": TOOLS})
        if method == "tools/call":
            name = params.get("name")
            fn = self.handlers().get(name)
            if fn is None:
                return err(-32601, f"unknown tool {name!r}")
            try:
                result = fn(**params.get("arguments", {}))
            except TypeError as exc:
                return err(-32602, f"invalid arguments for {name}: {exc}")
            except Exception as exc:                       # noqa: BLE001
                return err(-32603, f"{name} failed: {exc}")
            return ok({"content": [{"type": "text",
                                    "text": json.dumps(result, indent=2)}],
                       "isError": False})
        if method == "ping":
            return ok({})
        return err(-32601, f"unknown method {method!r}")

    def serve(self, stdin: TextIO | None = None, stdout: TextIO | None = None) -> None:
        stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
        for line in stdin:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            response = self.dispatch(message)
            if response is not None:
                stdout.write(json.dumps(response) + "\n")
                stdout.flush()
