"""Rail profiles: the limits a regulator or rail operator imposes.

These are hard rails (see PRD 7.2). They are never overridable, not even by the
principal, which is why a rule that trips one denies rather than escalates.

Kept as data, not code, because NPCI's Unified Agent Protocol is not published.
When it is, it becomes a new profile in this dict and nothing else changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .money import Paise, rupees


@dataclass(frozen=True)
class RailProfile:
    name: str
    txn_cap: Paise
    period_cap: Paise
    period: str
    max_delegates: int
    currencies: frozenset[str]
    prohibited_categories: frozenset[str]
    source: str = ""


UPI_CIRCLE_V1 = RailProfile(
    name="upi_circle.v1",
    txn_cap=rupees(5_000),
    period_cap=rupees(15_000),
    period="calendar_month",
    max_delegates=5,
    currencies=frozenset({"INR"}),
    prohibited_categories=frozenset({"gambling", "crypto", "adult", "tobacco"}),
    source="NPCI UPI Circle, full delegation. Published limits.",
)

# Deliberately absent: a `uap.v1` profile. UAP is unpublished; a profile here
# would be an invention presented as a rail. The slot stays empty until there
# is a specification to encode.
PROFILES: dict[str, RailProfile] = {UPI_CIRCLE_V1.name: UPI_CIRCLE_V1}


def get(name: str) -> RailProfile:
    try:
        return PROFILES[name]
    except KeyError:
        raise ValueError(f"unknown rail profile: {name!r}") from None
