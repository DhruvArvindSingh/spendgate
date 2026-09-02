"""Escalation budget (PRD 5 C5, 7.7, attack A8).

Human attention is a finite resource, and an attacker who can generate
unlimited approval prompts has found a denial-of-service against it. Someone
shown thirty prompts in an hour stops reading them and starts tapping approve,
at which point every genuine escalation is worthless too.

So the escalation budget is a security control, not a UX preference — and like
the money budget, it is state. Two limits, because they fail differently:

  max_per_window   total prompts raised in a rolling window. Caps the total
                   attention an attacker can consume.
  max_pending      prompts outstanding at once. Caps how many decisions a
                   person is holding in their head, which is where reflexive
                   approval actually comes from.

When the budget is exhausted the request is REFUSED, never approved. A prompt
that cannot be shown is a decision the principal did not make.
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class EscalationBudget:
    max_per_window: int = 5
    window_seconds: int = 3600
    max_pending: int = 3

    #: principal -> timestamps of prompts raised, oldest first
    _raised: dict[str, deque] = field(default_factory=dict)
    #: principal -> authorization ids awaiting an answer
    _pending: dict[str, set] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _prune(self, principal_id: str, now: datetime) -> deque:
        raised = self._raised.setdefault(principal_id, deque())
        cutoff = now - timedelta(seconds=self.window_seconds)
        while raised and raised[0] <= cutoff:
            raised.popleft()
        return raised

    def check(self, principal_id: str, now: datetime) -> tuple[bool, str]:
        """Whether another prompt may be raised, and why not if it may not."""
        with self._lock:
            raised = self._prune(principal_id, now)
            pending = self._pending.setdefault(principal_id, set())
            if len(pending) >= self.max_pending:
                return False, (f"{len(pending)} approvals are already waiting on you; "
                               "answer one before this can be raised")
            if len(raised) >= self.max_per_window:
                minutes = self.window_seconds // 60
                return False, (f"{len(raised)} approvals already requested in the last "
                               f"{minutes} minutes")
            return True, ""

    def raise_prompt(self, principal_id: str, authorization_id: str,
                     now: datetime) -> None:
        with self._lock:
            self._prune(principal_id, now).append(now)
            self._pending.setdefault(principal_id, set()).add(authorization_id)

    def resolve(self, principal_id: str, authorization_id: str) -> None:
        """The principal answered.

        Frees a pending slot but NOT the window count: the attention was spent
        whichever way they answered, so answering fast must not become a way to
        buy unlimited prompts.
        """
        with self._lock:
            self._pending.setdefault(principal_id, set()).discard(authorization_id)

    def pending(self, principal_id: str) -> int:
        with self._lock:
            return len(self._pending.get(principal_id, ()))
