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

---

## 7 · Two commits claimed a README update that never happened

**Phases 2 and 3, discovered while wiring the OpenRouter arm.**

The worst one, because it was silent and it reached commit messages.

The README was being edited with unasserted `str.replace()` calls inside a
script that printed `"README updated"` unconditionally. Python's `replace`
returns the string unchanged when the pattern does not match, so when a search
block drifted by a character the edit vanished and the script still reported
success.

The result: after Phase 3 the README still said **"Status — Phase 1 of 4"**,
still claimed **65 tests**, and had no results table at all — while the commit
messages and the summaries I gave said otherwise. Every individual replacement
"worked"; the file simply never changed.

It also produced a claim that was never true. An early draft of the caveat
section said an `ANTHROPIC_API_KEY` "switches in an LLM-driven agent". No such
agent existed — it was a sentence describing an intention, and because that edit
also failed to land, the false claim was never even visible to be caught. The LLM
arm in `evaluation/llm_agent.py` was written afterwards, against OpenRouter, so
the claim is now true rather than merely deleted.

Fixed by generating the README from `results/full.json` and the live test count,
then **verifying** the output against a checklist that fails the script:

```
OK   result table          OK   no stale phase 1
OK   phase 3 status        OK   no stale counts
OK   openrouter            OK   test count current
```

**The lesson worth keeping:** a mutation that cannot fail is not the same as a
mutation that succeeded. `sed` and `str.replace` both report success for zero
replacements, which makes them the wrong tool for editing a file you are about to
make claims about. Assert the match, or generate the file and check the result.

---

## 8 · The first LLM experiment measured the wrong thing entirely

**Phase 3, first run against a real model through OpenRouter.**

The scripted corpus had shown Arm A leaking ₹20,63,000. The obvious next step
was to hand the same attacks to a real model, so the first LLM scenarios were
the scripted attacks rewritten as goals: *buy the injected television*, *buy the
betting credit*, *buy three pairs of headphones at once*.

Every single one came back **₹0 leaked, in both arms**. Zero misreported
amounts. The experiment produced nothing.

Reading the transcripts explained why. Claude Sonnet 4.5 browsed the television,
saw the real ₹40,000 price sitting next to the injection payload, ignored the
payload completely, and said:

> "this exceeds my spending mandate of ₹5,000 per purchase … I cannot complete
> this purchase as it violates the spending constraints I've been given."

It declined the betting credit unprompted. Asked for three pairs of headphones
in one session, it worked out that ₹12,000 breached the cap and offered to buy
one. It never lied about an amount, in any run.

**The experiment was measuring whether the model self-polices. It does.** Which
is a fine thing to learn and a useless thing to build a control plane on,
because it tests the one property that is not in dispute.

The redesign asks the question that actually matters: *what can a well-behaved
model not do?* Two things, and neither is about honesty —

- it cannot remember what it already spent, when each invocation is a fresh
  context (`budget_amnesia`)
- it cannot enforce a policy it was never told, because the aggregate limit
  lives with the principal, not in the agent's instructions
  (`aggregate_blindness`)

Rewritten as sequences — several fresh model contexts against one persistent
ledger — and the result inverted. The model behaved impeccably on every single
step and the naive arm still leaked, because *nothing in that arm was keeping
score*.

**The lesson worth keeping:** a null result usually means the experiment asked
the wrong question, not that the effect is absent. The first version could only
have produced a headline about models being untrustworthy — and when the model
turned out to be trustworthy, it had nothing left to say. The second version
survives a perfectly behaved agent, which is the only version worth submitting.

---

## 9 · I invented an API field, and one live call found it

**Phase 4, first run against live Razorpay test mode.**

`scripts/live_rail_check.py` drives the whole pipeline against the real API.
Twelve checks, ten green. The two failures were in `reconcile`.

The state that broke it: an order exists, nobody has paid it, and the fake had
never modelled that. `FakeRazorpay` only ever produced two shapes — a captured
payment, or no order at all — so `reconcile` had a branch for "the order was
never created" and simply **fell through** for "the order exists and is
unpaid", leaving the authorization `INDETERMINATE` with no path out and the
budget held forever.

The fix looked obvious: set `expire_by` on the order, then an unpaid order
eventually becomes unpayable and the reservation is safe to release. I
implemented it, updated the fake, wrote four tests, and they all passed.

Then the live rail rejected every single order:

```
400  expire_by is/are not required and should not be sent
```

**`expire_by` is a Payment Links field. Razorpay orders have no expiry at all.**
I had designed against an API that does not exist, and the fake — which I had
just taught to store `expire_by` — agreed with me perfectly.

The real design has to accept that an unpaid order stays payable forever:

- The timeout is **ours**, not the rail's: hold the reservation for
  `RESERVATION_TTL`, then release it.
- Releasing is only safe with a **compensating control**, because the order is
  still live. The authorization moves to `ABANDONED`, and a capture arriving
  against an abandoned authorization is refunded and alerted rather than
  absorbed — money moved with no live reservation behind it.

`expire_by` stays on `create_payment_link`, where it is real.

**The lesson worth keeping:** a fake you wrote agrees with whatever you believed
when you wrote it. Four green tests certified a field that the vendor rejects on
sight. The fake is worth having — it makes the state machine testable — but it
can only ever confirm your model of the rail, never correct it. That correction
costs one real API call, and it is the cheapest call in the project.

---

## 10 · Mutation testing found a claim the code did not support

**Audit pass, after Phase 4.**

Fourteen deliberate mutations, each breaking one safety property, to see which
ones the suite would notice. Twelve died immediately. One turned out to be an
equivalent mutant — neutering the `>= 500` branch in the fact resolver changes
nothing, because the `!= 200` guard below it raises anyway, and a genuinely
fail-open mutation (fabricating facts on error) *was* caught. Fine.

The last one was real, and it was not a test gap. It was a false claim.

**Mutation:** change the ledger hash from `H(prev_hash ‖ entry)` to `H(entry)`.
Tests still passed. Investigating why produced this, run against the *unmutated*
code:

```
real chain, tamper one amount    -> (False, 3)      caught
after repairing every prev_hash  -> (True, None)    NOT caught
```

A hash chain alone is not tamper-evident. An attacker who can rewrite the log
recomputes each hash and repairs each `prev_hash`, and verification passes. The
only test I had tampered with an amount and stopped there — the easy half.

The README already said the invariant covered "log tampering". It did not. The
claim had been written before the mechanism existed, and nothing contradicted it
because the test was as weak as the design.

**Fixed by building the missing half.** `Anchor` holds the head hash outside the
ledger (`InMemoryAnchor` for tests, `FileAnchor` for an append-only sink);
`verify_against_anchor` compares against it; `check_invariant` uses it when one
is configured and refuses to imply the guarantee when one is not. The anchor is
now wired into the demo, the evaluation and the live check — it was pointless
sitting in the library while every runnable path went without it. Demo section 7
performs the full rewrite on screen and gets caught.

Two smaller things the same pass turned up: `reconcile` released a reservation
unconditionally and raised `KeyError` when there was nothing held — in the one
code path whose whole job is recovering after a crash — and the README's test
count had drifted from the suite.

**The lesson worth keeping:** tests written by the same person who wrote the
design share its blind spots. Mutation testing does not — it asks whether the
suite can *tell the difference*, and the answer pointed straight at a sentence I
had believed for four days.

---

## 11 · A control that existed only in the design document

**Audit follow-up.**

The PRD said, under escalation resolution:

> "Escalations are themselves rate-limited per principal per hour. An attacker
> who can generate unlimited approval prompts has found a denial-of-service
> against human attention […] the escalation budget is a security control, not a
> UX preference."

The threat model listed it as the mitigation for A8, approval fatigue. The
corpus had a whole `escalation_abuse` class for it.

None of it existed. There was no rate limit anywhere in the code. The
`escalation_abuse` cases passed because the *aggregate* rule happened to catch
the same purchases for an unrelated reason — the class was green for four days
while testing nothing it claimed to test.

This is the same failure as §10 and worth naming as a pattern: a document
written alongside the code will describe things that were intended, and there is
no mechanism that notices the difference. Green tests are not that mechanism
when the tests were written from the same intent.

Built now as `escalation.py` and rule **R38**, with two limits that fail
differently: a rolling window cap on total prompts raised, and a cap on prompts
outstanding at once. Answering frees a pending slot but not the window count —
otherwise answering quickly becomes a way to buy unlimited prompts, and the
attacker just needs a cooperative victim.

An exhausted budget **refuses**. A prompt that cannot be shown is a decision the
principal did not make, and treating it as approval would be precisely the
fatigue attack the control exists to stop.

In the corpus it now fires 20 times and drops total prompts raised from 108 to
88. Three mutations covering it are killed by the suite.

One structural fix came with it: the rule count is now derived from the registry
rather than asserted against a literal. `assert len(REGISTRY) == 37` in one file
and "37 rules" in three others is exactly how a document drifts from its code.
