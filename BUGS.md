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

---

## 4 · Three components, three clocks — and structuring silently stopped being detected

**Phase 2, wiring the settlement machine to the live demo.**

The best bug of the build, because nothing looked broken.

`SpendGate` takes an injected clock so decisions replay deterministically. I
gave the mock merchant and `Settlement` no such thing — both read
`datetime.now()` directly. Every component was individually correct.

The demo advanced SpendGate's clock forward to age a purchase out of the
aggregate window. Two things then went wrong at once:

- The merchant kept stamping session expiries from the wall clock, so sessions
  created after the jump looked **already expired** to the engine (R10) for
  reasons that had nothing to do with the code under test.
- Worse: `Settlement` wrote ledger entries at wall-clock time. Those entries are
  exactly what the windowed rules read. A payment that settled at demo-time
  T+90m was recorded at real time T, so when the next decision looked back one
  hour from T+95m, **the payment it was supposed to see had fallen out of its
  own window.**

The visible symptom was the structuring demo approving a second ₹4,000 split
that should have escalated. No exception, no failing assertion — the rule ran,
read an empty window, and correctly concluded there was nothing to aggregate.

Fixed by injecting the clock into `MerchantState` and `Settlement` too, so the
whole system shares one notion of time. Two regression tests now assert that a
settled payment is stamped at the injected time and is visible to the window
the next decision reads.

**The lesson worth keeping:** injecting a clock into *some* components is worse
than injecting it into none. A partial injection does not fail loudly — it
produces a system where each part is right and the composition is wrong, and
the failure surfaces as a security rule quietly not firing.

---

## 5 · The duplicate rule shadows the structuring rule

**Phase 2, first end-to-end structuring test.**

Two ₹4,000 splits fired seconds apart were refused as `suspected_duplicate`
(R28) rather than escalated as `aggregate_pattern` (R34). R28 sits in an earlier
stage, so it wins.

Not a bug — both are correct refusals, and for a same-amount repeat inside 60
seconds R28's reading (a non-idempotent retry) is the more likely explanation
and the safer answer. But the two are not interchangeable: R28 **denies**, while
R34 **escalates and shows the assembled pattern**, which is the more useful
outcome for a real purchase.

So the reason a structuring attempt gets refused depends on its timing, which is
worth knowing before a reviewer discovers it. Left the ordering alone and added
`test_rapid_identical_splits_are_denied_as_duplicates_not_escalated` to pin both
paths, so the difference is a documented decision rather than a surprise.

---

## 6 · The evaluation was crediting Arm A for a test it never sat

**Phase 3, first full run of the corpus.**

The `expiry_revocation` class attacks a signed mandate: spend against one that
has expired or been revoked. The first full run scored it **Arm A 15/15
contained, ₹0 leaked** — a perfect score, better than SpendGate managed on
several other classes.

Arm A has no mandate. It has limits written in a prompt. There is nothing there
to expire and nothing to revoke, so the attack was only ever applied to Arm B,
and Arm A collected fifteen free passes for a test it was never subjected to.

The direction is worth noting: this flattered the *control* arm, not the system
under test. It still had to go. A comparison that hands one side points for
absent tests is not a comparison, and it inflated Arm A's containment from a
true 17/145 to a false 32/160.

Fixed by giving each case an `applies_to` field. Inapplicable arms are skipped
and reported as **not applicable** rather than as a pass, in the JSON and in the
HTML report.

**A second thing surfaced in the same pass.** `NaiveArm` was charging
`CATALOG[sku]["amount"]` — a constant — while Arm B charged whatever the
merchant's checkout session said. That quietly exempted Arm A from the
merchant-repricing attack, since a repriced session never reached it. Both arms
now read the amount from the merchant, which is what a real implementation would
do; only the *guard's* input differs, which is the actual variable under test.

**The lesson worth keeping:** when you build both sides of your own comparison,
the failure mode is not writing a strawman on purpose. It is the accounting
quietly diverging between the two — and it can just as easily favour the side
you were hoping to beat.
