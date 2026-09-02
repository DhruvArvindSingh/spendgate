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


#: Keys are tried in order. OpenRouter reserves credit against `max_tokens`
#: rather than actual usage, so a nearly-spent key fails with 402 long before it
#: is really empty; rotating lets a run finish on the next one.
KEY_VARS = ("OPENROUTER_API_KEY_1", "OPENROUTER_API_KEY", "OPENROUTER_KEY")


def api_keys() -> list[str]:
    seen: list[str] = []
    for name in KEY_VARS:
        k = os.environ.get(name)
        if k and k not in seen:
            seen.append(k)
    return seen


def api_key() -> str | None:
    keys = api_keys()
    return keys[0] if keys else None


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
class Usage:
    """Token counts and cost, as reported by OpenRouter itself.

    Taken from the response rather than estimated: different providers count
    reasoning and cached tokens differently, and a guess would make the cost
    column in the results table fiction.
    """

    prompt: int = 0
    completion: int = 0
    cost_usd: float = 0.0
    calls: int = 0

    def add(self, other: "Usage") -> None:
        self.prompt += other.prompt
        self.completion += other.completion
        self.cost_usd += other.cost_usd
        self.calls += other.calls


@dataclass
class OpenRouter:
    model: str = field(default_factory=lambda: os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL))
    temperature: float = 0.0
    max_steps: int = 8
    timeout: float = 120.0
    #: Capped deliberately. Without it the SDK asks for the model's full output
    #: window, and OpenRouter reserves credit against that number — which is how
    #: a run with real money left fails with "requested up to 64000 tokens".
    max_tokens: int = 1200
    usage: Usage = field(default_factory=Usage)
    _key_index: int = 0
    _client: Any = None

    def client(self):
        if self._client is None:
            keys = api_keys()
            key = keys[self._key_index] if self._key_index < len(keys) else None
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
            resp = self._complete(messages, tools)
            self._record(resp)
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


    def _record(self, resp: Any) -> None:
        u = getattr(resp, "usage", None)
        if u is None:
            return
        cost = 0.0
        # OpenRouter returns the real charge under usage.cost when asked.
        raw = getattr(u, "model_extra", None) or {}
        for key in ("cost", "total_cost"):
            if raw.get(key) is not None:
                cost = float(raw[key])
                break
        self.usage.add(Usage(prompt=getattr(u, "prompt_tokens", 0) or 0,
                             completion=getattr(u, "completion_tokens", 0) or 0,
                             cost_usd=cost, calls=1))


    def _complete(self, messages: list[dict], tools: list[dict]) -> Any:
        """One completion, rotating to the next key if this one is out of credit."""
        last: Exception | None = None
        for _ in range(max(1, len(api_keys()))):
            try:
                return self.client().chat.completions.create(
                    model=self.model, messages=messages, tools=tools,
                    tool_choice="auto", temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    extra_body={"usage": {"include": True}},
                )
            except Exception as exc:                              # noqa: BLE001
                if "402" not in str(exc) and "credit" not in str(exc).lower():
                    raise
                last = exc
                self._key_index += 1
                self._client = None
                if self._key_index >= len(api_keys()):
                    break
        raise last if last else RuntimeError("no completion and no error")


def _parse_args(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {"_value": parsed}
    except json.JSONDecodeError:
        return {"_unparsed": raw}
