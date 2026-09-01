#!/usr/bin/env python3
"""Check that the credentials in .env actually work, without printing them.

    python scripts/verify_credentials.py

Read-only: it lists models on OpenRouter and reads (never creates) on Razorpay.
Nothing here moves money.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from spendgate.dotenv import find_and_load  # noqa: E402

OK, BAD, DIM, END = "\033[32m", "\033[31m", "\033[2m", "\033[0m"


def mask(value: str) -> str:
    """Show enough to identify a key, never enough to use it."""
    if len(value) < 12:
        return "…"
    return f"{value[:10]}…{value[-4:]} ({len(value)} chars)"


def check_openrouter() -> bool:
    key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENROUTER_KEY")
    if not key:
        print(f"  {BAD}✗{END} OPENROUTER_API_KEY not set")
        return False
    print(f"  {DIM}OPENROUTER_API_KEY  {mask(key)}{END}")
    try:
        import httpx

        r = httpx.get("https://openrouter.ai/api/v1/key",
                      headers={"Authorization": f"Bearer {key}"}, timeout=20)
        if r.status_code != 200:
            print(f"  {BAD}✗{END} OpenRouter rejected the key ({r.status_code})")
            return False
        data = r.json().get("data", {})
        limit, usage = data.get("limit"), data.get("usage")
        budget = "unlimited" if limit is None else f"limit {limit}"
        print(f"  {OK}✓{END} OpenRouter accepted the key — usage {usage}, {budget}")
        return True
    except Exception as exc:                                   # noqa: BLE001
        print(f"  {BAD}✗{END} OpenRouter check failed: {exc}")
        return False


def check_razorpay() -> bool:
    kid = os.environ.get("RAZORPAY_KEY_ID", "")
    secret = os.environ.get("RAZORPAY_KEY_SECRET", "")
    if not kid or not secret:
        print(f"  {BAD}✗{END} RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET not set")
        return False
    print(f"  {DIM}RAZORPAY_KEY_ID     {mask(kid)}{END}")
    if not kid.startswith("rzp_test"):
        print(f"  {BAD}✗{END} not a test key. SpendGate refuses live credentials.")
        return False
    try:
        import httpx

        r = httpx.get("https://api.razorpay.com/v1/payments",
                      params={"count": 1}, auth=(kid, secret), timeout=20)
        if r.status_code == 401:
            print(f"  {BAD}✗{END} Razorpay rejected the credentials (401)")
            return False
        if r.status_code != 200:
            print(f"  {BAD}✗{END} Razorpay returned {r.status_code}: {r.text[:120]}")
            return False
        print(f"  {OK}✓{END} Razorpay test mode accepted — "
              f"{r.json().get('count', 0)} existing payment(s) visible")
        return True
    except Exception as exc:                                   # noqa: BLE001
        print(f"  {BAD}✗{END} Razorpay check failed: {exc}")
        return False


def main() -> int:
    names = find_and_load(ROOT)
    print(f"\nLoaded {len(names)} variable(s) from .env: {', '.join(sorted(names)) or '—'}\n")
    results = [check_openrouter(), check_razorpay()]
    webhook = os.environ.get("RAZORPAY_WEBHOOK_SECRET", "")
    print(f"  {DIM}RAZORPAY_WEBHOOK_SECRET {'set' if webhook else 'empty — only needed for live webhook delivery'}{END}")
    print()
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
