"""Money is integer paise. No float ever touches an amount in this system.

A float rupee amount is a rounding bug waiting for a batch job to find it, so
the type system here only knows minor units. Formatting is for humans at the
edge; arithmetic is always on ints.
"""

from __future__ import annotations

Paise = int


def rupees(amount: float | int | str) -> Paise:
    """Convert a rupee amount to paise. Accepts str to avoid float literals."""
    from decimal import Decimal

    return int((Decimal(str(amount)) * 100).to_integral_value())


def fmt(paise: Paise) -> str:
    """Render paise as ₹ with Indian digit grouping (1,23,456.00)."""
    sign = "-" if paise < 0 else ""
    whole, frac = divmod(abs(paise), 100)
    s = str(whole)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups + [tail])
    return f"{sign}₹{s}.{frac:02d}"
