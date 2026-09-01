"""The budget ledger (PRD 5 C4, 6.5, 8).

This is the component AP2 specifies but does not provide. Its budget constraint
says the spent amount "MUST be added to the accumulated total for future
evaluation" - one sentence that is really durable accumulation, serialisation,
reservation versus commitment, release on failure, and credit-back on refund.

Phase 1 keeps the state in memory behind a per-mandate lock. Phase 2 swaps in
Postgres with SELECT ... FOR UPDATE; the interface and the invariant are the
same, which is the point of putting them behind one.
"""

from __future__ import annotations

import hashlib
import json
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Protocol

from .models import LedgerSnapshot, SettledTxn
from .money import Paise

GENESIS = "sha256:" + "0" * 64


class Anchor(Protocol):
    """Somewhere outside the ledger that remembers the head hash.

    A hash chain on its own is NOT tamper-evident. An attacker who can rewrite
    the log can recompute every entry's hash and repair every prev_hash link,
    leaving a chain that verifies perfectly. Detection requires a head hash held
    somewhere the attacker cannot edit — that is what this is for. Without an
    anchor, verify_chain proves internal consistency and nothing more.
    """

    def record(self, mandate_id: str, seq: int, head: str) -> None: ...
    def head(self, mandate_id: str) -> tuple[int, str] | None: ...


class InMemoryAnchor:
    """Same-process anchor. Useful in tests; NOT a security boundary in
    production, where the sink has to be genuinely out of reach."""

    def __init__(self) -> None:
        self._heads: dict[str, tuple[int, str]] = {}

    def record(self, mandate_id: str, seq: int, head: str) -> None:
        self._heads[mandate_id] = (seq, head)

    def head(self, mandate_id: str) -> tuple[int, str] | None:
        return self._heads.get(mandate_id)


class FileAnchor:
    """Append-only file anchor. Models the real thing: a sink the writing
    process can append to but is not expected to be able to rewrite."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, mandate_id: str, seq: int, head: str) -> None:
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"mandate_id": mandate_id, "seq": seq, "head": head}) + "\n")

    def head(self, mandate_id: str) -> tuple[int, str] | None:
        if not self.path.is_file():
            return None
        latest = None
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            if rec["mandate_id"] == mandate_id:
                latest = (rec["seq"], rec["head"])
        return latest


class EntryKind(str, Enum):
    RESERVE = "RESERVE"
    COMMIT = "COMMIT"
    RELEASE = "RELEASE"
    CREDIT = "CREDIT"


class BudgetLockTimeout(RuntimeError):
    """Another payment on this mandate holds the lock (maps to R29)."""


class InsufficientBudget(RuntimeError):
    """Reserve attempted beyond available budget. The engine should have caught
    this first; reaching it means the decision and the ledger disagree."""


@dataclass(frozen=True)
class LedgerEntry:
    seq: int
    mandate_id: str
    authorization_id: str
    kind: EntryKind
    amount_minor: Paise
    at: datetime
    prev_hash: str
    settled_after: Paise
    reserved_after: Paise
    merchant_id: str | None = None
    sku: str | None = None
    razorpay_ref: str | None = None

    def canonical(self) -> str:
        """Stable serialisation for hashing.

        Approximates RFC 8785 (sorted keys, no whitespace). Full JCS - number
        canonicalisation in particular - is Phase 2; every value hashed here is
        an int or a string, so the two agree on this data today.
        """
        return json.dumps(
            {
                "seq": self.seq,
                "mandate_id": self.mandate_id,
                "authorization_id": self.authorization_id,
                "kind": self.kind.value,
                "amount_minor": self.amount_minor,
                "at": self.at.isoformat(),
                "settled_after": self.settled_after,
                "reserved_after": self.reserved_after,
                "merchant_id": self.merchant_id,
                "sku": self.sku,
                "razorpay_ref": self.razorpay_ref,
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    @property
    def hash(self) -> str:
        return "sha256:" + hashlib.sha256(
            (self.prev_hash + self.canonical()).encode()
        ).hexdigest()


@dataclass
class _Account:
    budget_max: Paise
    settled: Paise = 0
    reserved: Paise = 0
    occurrences: int = 0
    entries: list[LedgerEntry] = field(default_factory=list)
    open_reservations: dict[str, Paise] = field(default_factory=dict)
    settled_txns: list[SettledTxn] = field(default_factory=list)
    merchants_seen: set[str] = field(default_factory=set)
    price_history: dict[str, list[Paise]] = field(default_factory=dict)
    active_delegates: int = 1
    lock: threading.RLock = field(default_factory=threading.RLock)

    @property
    def last_hash(self) -> str:
        return self.entries[-1].hash if self.entries else GENESIS


class InMemoryLedger:
    def __init__(self, anchor: Anchor | None = None) -> None:
        self._accounts: dict[str, _Account] = {}
        self._guard = threading.Lock()
        #: Optional. Without it, verify_chain can only prove internal
        #: consistency — see the Anchor docstring.
        self.anchor = anchor

    # ---------------------------------------------------------------- setup
    def open_account(self, mandate_id: str, budget_max: Paise, *, active_delegates: int = 1) -> None:
        with self._guard:
            self._accounts[mandate_id] = _Account(
                budget_max=budget_max, active_delegates=active_delegates
            )

    def _acct(self, mandate_id: str) -> _Account:
        with self._guard:
            if mandate_id not in self._accounts:
                raise KeyError(f"no ledger account for {mandate_id!r}")
            return self._accounts[mandate_id]

    # ----------------------------------------------------------- read model
    def snapshot(self, mandate_id: str) -> LedgerSnapshot:
        a = self._acct(mandate_id)
        with a.lock:
            return LedgerSnapshot(
                settled_minor=a.settled,
                reserved_minor=a.reserved,
                occurrences=a.occurrences,
                recent=tuple(a.settled_txns),
                merchants_seen=frozenset(a.merchants_seen),
                price_history={k: tuple(v) for k, v in a.price_history.items()},
                active_delegates=a.active_delegates,
            )

    def available(self, mandate_id: str) -> Paise:
        a = self._acct(mandate_id)
        with a.lock:
            return a.budget_max - a.settled - a.reserved

    # -------------------------------------------------------- serialisation
    @contextmanager
    def begin(self, mandate_id: str, timeout: float = 5.0):
        """Hold the per-mandate lock across decide-then-reserve.

        Decision and reservation must share one critical section: two requests
        that each fit the budget alone but not together would otherwise both
        read the same available balance and both be approved.

        The lock is never held across a network call - that would turn
        contention into an outage. Timeout maps to R29.
        """
        a = self._acct(mandate_id)
        if not a.lock.acquire(timeout=timeout):
            raise BudgetLockTimeout(mandate_id)
        try:
            yield self
        finally:
            a.lock.release()

    # ------------------------------------------------------------ mutations
    def _append(self, a: _Account, mandate_id: str, auth_id: str, kind: EntryKind,
                amount: Paise, at: datetime, merchant_id: str | None = None,
                sku: str | None = None, ref: str | None = None) -> LedgerEntry:
        entry = LedgerEntry(
            seq=len(a.entries) + 1,
            mandate_id=mandate_id,
            authorization_id=auth_id,
            kind=kind,
            amount_minor=amount,
            at=at,
            prev_hash=a.last_hash,
            settled_after=a.settled,
            reserved_after=a.reserved,
            merchant_id=merchant_id,
            sku=sku,
            razorpay_ref=ref,
        )
        a.entries.append(entry)
        if self.anchor is not None:
            self.anchor.record(mandate_id, entry.seq, entry.hash)
        return entry

    def reserve(self, mandate_id: str, auth_id: str, amount: Paise, at: datetime,
                merchant_id: str | None = None) -> LedgerEntry:
        a = self._acct(mandate_id)
        with a.lock:
            if auth_id in a.open_reservations:
                return a.entries[-1]  # idempotent within a retry
            if a.budget_max - a.settled - a.reserved < amount:
                raise InsufficientBudget(mandate_id)
            a.reserved += amount
            a.open_reservations[auth_id] = amount
            return self._append(a, mandate_id, auth_id, EntryKind.RESERVE, amount, at, merchant_id)

    def commit(self, mandate_id: str, auth_id: str, at: datetime, *,
               merchant_id: str | None = None, sku: str | None = None,
               unit_minor: Paise | None = None, ref: str | None = None) -> LedgerEntry:
        """Payment captured and verified. The reservation becomes spend."""
        a = self._acct(mandate_id)
        with a.lock:
            amount = a.open_reservations.pop(auth_id, None)
            if amount is None:
                raise KeyError(f"no open reservation {auth_id!r}")
            a.reserved -= amount
            a.settled += amount
            a.occurrences += 1
            if merchant_id:
                a.merchants_seen.add(merchant_id)
                a.settled_txns.append(SettledTxn(merchant_id, amount, at, sku))
            if sku and unit_minor is not None:
                a.price_history.setdefault(sku, []).append(unit_minor)
            return self._append(a, mandate_id, auth_id, EntryKind.COMMIT, amount, at, merchant_id, sku, ref)

    def release(self, mandate_id: str, auth_id: str, at: datetime) -> LedgerEntry:
        """Payment failed, or the reservation expired. The budget comes back.

        Only ever called for a KNOWN failure. A payment whose outcome is unknown
        holds its reservation until the reconciler resolves it - releasing an
        INDETERMINATE payment invites a double-spend when it settles late.
        """
        a = self._acct(mandate_id)
        with a.lock:
            amount = a.open_reservations.pop(auth_id, None)
            if amount is None:
                raise KeyError(f"no open reservation {auth_id!r}")
            a.reserved -= amount
            return self._append(a, mandate_id, auth_id, EntryKind.RELEASE, amount, at)

    def credit(self, mandate_id: str, auth_id: str, amount: Paise, at: datetime) -> LedgerEntry:
        """Refund received. Restores available budget."""
        a = self._acct(mandate_id)
        with a.lock:
            a.settled -= amount
            return self._append(a, mandate_id, auth_id, EntryKind.CREDIT, amount, at)

    # ------------------------------------------------------------ integrity
    def has_open_reservation(self, mandate_id: str, auth_id: str) -> bool:
        """Whether a reservation is still outstanding.

        The reconciler runs after crashes, so it must be able to ask rather than
        assume: releasing twice, or releasing something already committed, would
        otherwise raise from the one code path that exists to recover.
        """
        a = self._acct(mandate_id)
        with a.lock:
            return auth_id in a.open_reservations

    def entries(self, mandate_id: str) -> list[LedgerEntry]:
        return list(self._acct(mandate_id).entries)

    def verify_chain(self, mandate_id: str) -> tuple[bool, int | None]:
        """Recompute the chain. Returns (ok, first_bad_seq).

        Internal consistency only. A rewrite that repairs every prev_hash passes
        this — which is why an anchor exists. Use verify_against_anchor for the
        property people mean when they say "tamper-evident".
        """
        prev = GENESIS
        for e in self._acct(mandate_id).entries:
            if e.prev_hash != prev:
                return False, e.seq
            prev = e.hash
        return True, None

    def verify_against_anchor(self, mandate_id: str) -> tuple[bool, str]:
        """Compare the chain head to the externally recorded one.

        This is the check that survives a competent attacker: rewriting the log
        changes the head, and the head is not in the log.
        """
        if self.anchor is None:
            return False, "no anchor configured; tampering cannot be ruled out"
        ok, bad = self.verify_chain(mandate_id)
        if not ok:
            return False, f"chain broken at seq {bad}"
        recorded = self.anchor.head(mandate_id)
        entries = self._acct(mandate_id).entries
        if recorded is None:
            return (True, "empty ledger, nothing to anchor yet") if not entries else (
                False, "entries exist but the anchor recorded no head")
        seq, head = recorded
        if not entries:
            return False, "anchor has a head but the ledger is empty"
        if entries[-1].seq != seq or entries[-1].hash != head:
            return False, (f"head mismatch: ledger {entries[-1].seq}/"
                           f"{entries[-1].hash[:16]}… vs anchor {seq}/{head[:16]}…")
        return True, "head matches the anchor"

    def check_invariant(self, mandate_id: str) -> None:
        """PRD 6.6. Asserted after every transition and every test.

        One assertion covering double-spend, budget leakage from failed
        payments, refund accounting and log tampering.
        """
        a = self._acct(mandate_id)
        with a.lock:
            assert a.reserved == sum(a.open_reservations.values()), (
                f"reserved {a.reserved} != open reservations {sum(a.open_reservations.values())}"
            )
            assert a.settled + a.reserved <= a.budget_max, (
                f"settled {a.settled} + reserved {a.reserved} > budget {a.budget_max}"
            )
            assert a.budget_max - a.settled - a.reserved >= 0, "available went negative"
            ok, bad = self.verify_chain(mandate_id)
            assert ok, f"hash chain broken at seq {bad}"
            # When an anchor exists, use it: verify_chain alone passes a
            # rewrite that repaired every prev_hash (see its docstring).
            if self.anchor is not None:
                anchored, why = self.verify_against_anchor(mandate_id)
                assert anchored, f"ledger diverged from its anchor: {why}"
