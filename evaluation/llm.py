"""OpenRouter client for the LLM-driven arm.

OpenRouter speaks the OpenAI wire format, so the official `openai` SDK works
against it unchanged with a different base_url. One model string switches
between providers, which is why it is the right choice for this experiment:
the same corpus can be run against several models without touching the harness.

Nothing here is imported by the SpendGate package. The engine has no model
inference in it and this file must not change that — it lives in evaluation/
because it is the *subject* of the experiment, not part of the system.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Callable

BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "anthropic/claude-sonnet-4.5"


def api_key() -> str | None:
    return os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENROUTER_KEY")


def available() -> bool:
    return bool(api_key())


class LlmUnavailable(RuntimeError):
    """No OPENROUTER_API_KEY. The LLM arm is opt-in and never silently skipped."""


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]


@dataclass
class Turn:
    text: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass
class OpenRouter:
    model: str = field(default_factory=lambda: os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL))
    temperature: float = 0.0
    max_steps: int = 8
    timeout: float = 90.0
    _client: Any = None

    def client(self):
        if self._client is None:
            key = api_key()
            if not key:
                raise LlmUnavailable(
                    "set OPENROUTER_API_KEY to run the LLM arm "
                    "(https://openrouter.ai/keys)"
                )
            from openai import OpenAI

            self._client = OpenAI(
                api_key=key, base_url=BASE_URL, timeout=self.timeout,
                default_headers={
                    "HTTP-Referer": "https://github.com/DhruvArvindSingh/spendgate",
                    "X-Title": "SpendGate evaluation",
                },
            )
        return self._client

    def run(self, system: str, user: str, tools: list[dict],
            execute: Callable[[ToolCall], Any]) -> list[Turn]:
        """Drive a tool-calling loop until the model stops calling tools."""
        messages: list[dict] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        turns: list[Turn] = []

        for _ in range(self.max_steps):
            resp = self.client().chat.completions.create(
                model=self.model, messages=messages, tools=tools,
                tool_choice="auto", temperature=self.temperature,
            )
            choice = resp.choices[0].message
            calls = [
                ToolCall(c.function.name, _parse_args(c.function.arguments))
                for c in (choice.tool_calls or [])
            ]
            turns.append(Turn(text=choice.content, tool_calls=calls))
            if not calls:
                break

            messages.append({
                "role": "assistant",
                "content": choice.content,
                "tool_calls": [
                    {"id": c.id, "type": "function",
                     "function": {"name": c.function.name, "arguments": c.function.arguments}}
                    for c in choice.tool_calls
                ],
            })
            for raw, call in zip(choice.tool_calls, calls):
                try:
                    result = execute(call)
                except Exception as exc:                      # noqa: BLE001
                    result = {"error": str(exc)}
                messages.append({"role": "tool", "tool_call_id": raw.id,
                                 "content": json.dumps(result, default=str)})
        return turns


def _parse_args(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {"_value": parsed}
    except json.JSONDecodeError:
        return {"_unparsed": raw}
