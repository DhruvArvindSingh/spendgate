"""Core records. The shapes carry the security properties (PRD 6).

The most important shape here is AuthorizationRequest: it has no amount field,
no item, no merchant. An agent cannot misreport what it is buying because the
schema gives it nowhere to do so.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from enum import Enum
from typing import Any

from .money import Paise


class Outcome(str, Enum):
    APPROVED = "APPROVED"
    ESCALATED = "ESCALATED"
    DENIED = "DENIED"
    REPLAYED = "REPLAYED"


class Kind(str, Enum):
    """Why a rule exists, which decides deny-vs-escalate."""

    INTEGRITY = "integrity"   # something is forged, missing or unverifiable
    RAIL = "rail"             # regulator or rail operator; nobody may override
    POLICY = "policy"         # the principal's own preference; they may override
    PROTOCOL = "protocol"     # HTTP-level idempotency semantics


class Layer(str, Enum):
    """Where a rule is enforced.

    Not every rule can live in the pure engine: idempotency needs a request
    store and budget serialisation needs a lock. Recording the layer keeps the
    reason-code vocabulary complete without pretending the engine does
    something it does not.
    """

    ENGINE = "engine"
    SERVICE = "service"
    LEDGER = "ledger"


@dataclass(frozen=True)
class Constraint:
    type: str
    params: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.params.get(key, default)


@dataclass(frozen=True)
class AgentRecord:
    agent_id: str
    principal_id: str
    registered: bool = True
    revoked_at: datetime | None = None


@dataclass(frozen=True)
class Mandate:
    mandate_id: str
    principal_id: str
    agent_id: str
    rail_profile: str
    constraints: tuple[Constraint, ...]
    issued_at: datetime
    vct: str = "mandate.payment.open.1"
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    revoked_at: datetime | None = None
    signature_valid: bool = True   # Phase 2 replaces this with real ES256 verification
    version: int = 1

    def constraint(self, type_: str) -> Constraint | None:
        for c in self.constraints:
            if c.type == type_:
                return c
        return None


@dataclass(frozen=True)
class LineItem:
    sku: str
    qty: int
    unit_minor: Paise


@dataclass(frozen=True)
class ResolvedFacts:
    """What the MERCHANT says, fetched server-to-server. Never agent input."""

    checkout_session_id: str
    merchant_id: str
    merchant_verified: bool
    status: str
    currency: str
    total_minor: Paise
    category: str
    issued_to_agent: str
    expires_at: datetime
    resolved_at: datetime
    line_items: tuple[LineItem, ...] = ()
    consumed: bool = False
    instrument: str = "upi"

    @property
    def facts_hash(self) -> str:
        import hashlib
        import json

        payload = json.dumps(
            {
                "cs": self.checkout_session_id,
                "m": self.merchant_id,
                "cur": self.currency,
                "total": self.total_minor,
                "cat": self.category,
                "items": [[i.sku, i.qty, i.unit_minor] for i in self.line_items],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


@dataclass(frozen=True)
class AuthorizationRequest:
    """The complete agent-facing input surface.

    No amount. No item. No merchant. No currency. A fully prompt-injected agent
    still emits exactly this.
    """

    mandate_id: str
    checkout_session_id: str
    agent_id: str
    idempotency_key: str | None = None


@dataclass(frozen=True)
class SettledTxn:
    merchant_id: str
    amount_minor: Paise
    at: datetime
    sku: str | None = None


@dataclass(frozen=True)
class LedgerSnapshot:
    """Read-only view of spend state, taken under lock before a decision."""

    settled_minor: Paise = 0
    reserved_minor: Paise = 0
    occurrences: int = 0
    recent: tuple[SettledTxn, ...] = ()
    merchants_seen: frozenset[str] = frozenset()
    price_history: dict[str, tuple[Paise, ...]] = field(default_factory=dict)
    active_delegates: int = 1

    @property
    def committed_minor(self) -> Paise:
        return self.settled_minor + self.reserved_minor


@dataclass(frozen=True)
class Decision:
    outcome: Outcome
    reason_code: str | None = None
    reason_text: str = ""
    rule_id: str | None = None
    rules_evaluated: int = 0
    overridable: bool = False
    amount_minor: Paise = 0
    facts_hash: str | None = None
    decided_at: datetime | None = None

    @property
    def approved(self) -> bool:
        return self.outcome is Outcome.APPROVED


@dataclass(frozen=True)
class Context:
    """Everything the engine is allowed to see. Note the injected clock:
    no rule may call datetime.now(), so every decision replays bit-identically.
    """

    request: AuthorizationRequest
    now: datetime
    mandate: Mandate | None = None
    facts: ResolvedFacts | None = None
    agent: AgentRecord | None = None
    ledger: LedgerSnapshot = field(default_factory=LedgerSnapshot)
    facts_available: bool = True
    session_found: bool = True

    @property
    def amount(self) -> Paise:
        return self.facts.total_minor if self.facts else 0
