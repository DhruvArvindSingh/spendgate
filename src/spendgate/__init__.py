"""SpendGate - deterministic spending authority for AI agents.

Agents propose. SpendGate decides, executes, and proves.
"""

from .engine import decide, trace
from .ledger import InMemoryLedger, BudgetLockTimeout, InsufficientBudget
from .models import (
    AgentRecord, AuthorizationRequest, Constraint, Context, Decision,
    LedgerSnapshot, LineItem, Mandate, Outcome, ResolvedFacts, SettledTxn,
)
from .money import fmt, rupees
from .rails import UPI_CIRCLE_V1, RailProfile
from .rules import BY_ID, ENGINE_RULES, REGISTRY
from .service import FactsUnavailable, SpendGate

__version__ = "0.1.0"
__all__ = [
    "decide", "trace", "SpendGate", "InMemoryLedger", "REGISTRY", "ENGINE_RULES",
    "BY_ID", "Mandate", "Constraint", "Context", "Decision", "Outcome",
    "ResolvedFacts", "LineItem", "AgentRecord", "AuthorizationRequest",
    "LedgerSnapshot", "SettledTxn", "RailProfile", "UPI_CIRCLE_V1",
    "rupees", "fmt", "FactsUnavailable", "BudgetLockTimeout", "InsufficientBudget",
]
