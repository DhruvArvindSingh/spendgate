# What broke

A running log. Kept honestly — including the ones that were my own test being
wrong rather than the code, since those are the ones that teach you something
about the model you were carrying in your head.

---

## 1 · The concurrency test was asserting a false property

**Phase 1, `test_budget_never_oversubscribed_under_load`.**

Wrote a race test: ₹15,000 budget, N threads each reserving ₹1,000, assert
exactly 15 succeed. It failed at N=8 with 8 winners.

The code was right and the test was wrong. With 8 threads only ₹8,000 is
requested, so the budget is not the binding constraint and all 8 *should*
succeed. I had written the assertion for the contended case and applied it to
every parametrisation.

Fixed to `expected = min(threads, 15)`, asserted exactly in both directions.
The stronger form matters: a guard that refused legitimate concurrent requests
would have passed a naive "never oversubscribe" assertion while being useless.
Testing only the failure direction would have hidden that.

---

## 2 · The unit tests were pre-warming state the real ledger does not have

**Phase 1, first integration of `SpendGate` with `InMemoryLedger`.**

Every rule test passed against a hand-built `LedgerSnapshot`. The moment the
service ran against a real ledger, two tests failed on `merchant_first_seen`
(R31) instead of the rule under test.

Not a bug in the engine — R31 firing on a genuinely new payee is correct, and
arguably the most useful rule in the set. The bug was in my fixtures: the
snapshot builder seeded `merchants_seen` with the merchant, so the unit tests
had been silently running against a warm ledger while a real one starts cold.

Fixed by seeding an explicit prior settled purchase in the service fixture, and
adding `test_first_purchase_from_a_new_merchant_asks_the_principal` to cover
the cold path that the seeding now hides.

**The lesson worth keeping:** a fixture that constructs a state snapshot
directly can drift from any state the system can actually reach. The rule tests
were correct about the predicate and wrong about the world.

---

## 3 · The demo told a true story with misleading numbers

**Phase 1, `demo.py` structuring scenario.**

The structuring demo seeded a ₹500 prior purchase so the merchant would not be
first-seen. With a 24-hour aggregate window that seed fell *inside* the window,
so the escalation read "3 purchases totalling ₹8,500" during a demo captioned
"three ₹4,000 purchases".

The message was arithmetically correct — the ₹500 genuinely was in the window
and genuinely should be aggregated. But a viewer counting ₹4,000 splits sees
numbers that do not add up and stops trusting the demo.

Narrowed the window to one hour and moved the seed to three hours earlier, so
the demo now reads "2 purchases totalling ₹8,000".

Worth recording because the fix was to the *presentation*, not the logic — and
because the instinct to "adjust" a correct number until it looks tidier is
exactly how a demo starts lying. The seed moved; the arithmetic did not.
