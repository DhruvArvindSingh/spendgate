# Narration script

**Target 4:55.** Written at ~145 words/minute — an unhurried explaining pace.
Each section's `beat()` values in the scene files are timed to these words, so
if you change the words, re-check the timing with `./render.sh draft`.

Read it slightly slower than feels natural. The animation waits for you.

---

## 01 · The problem — 43s

> You give an AI agent your card and say: buy my groceries, stay under five
> thousand rupees a purchase.
>
> Almost everyone builds this the same way — hand the model a payment button,
> write the limits into its instructions.
>
> That breaks three ways. You can talk it out of it, because the limit is a
> sentence and reading sentences is what it does. It can't remember, because
> every conversation starts fresh. And it reports its own numbers, so the only
> witness is the suspect.
>
> Here's the failure. Cap is five thousand, the agent wants a twelve-thousand
> item. So it buys it three times at four thousand.
>
> Every purchase is legal. Nothing was keeping score.

## 02 · Where it fits — 33s

> This isn't an empty field. Three standards already describe agent payments.
>
> Stripe and OpenAI's handles checkout. Google's handles proof that a human
> authorised it. Razorpay moves the money.
>
> The missing layer is the one in the middle. And it's not that nobody thought
> of it — Google's specification says the amount spent *must* be added to a
> running total.
>
> It says the budget must be tracked. It doesn't say who tracks it.
>
> That's this project.

## 03 · How it works — 62s

> Start with the shape of the request, because the security is in the shape.
>
> This is the agent's entire vocabulary. A permission slip, a basket, and who's
> asking. No amount. No item. No merchant.
>
> A completely compromised agent still sends exactly this. There is nowhere to
> put a lie.
>
> So where does the price come from? The agent hands over a ticket number.
> SpendGate asks the shop directly, over a connection the agent isn't standing
> in. The shop says twelve hundred rupees. The agent is never on that path —
> that's the whole trick.
>
> Then ordinary code decides. Thirty-eight rules in a fixed order. Is the slip
> real. Is the basket real and unpaid. Is it inside the hard limits. Is it a
> duplicate or a race. And last — is it something you'd want to be asked about.
>
> First objection wins, and it names one reason. Never a list.

## 04 · The edges — 74s

> Four cases worth showing.
>
> First, a hostile listing. One product in my test shop hides this in its
> description — telling the agent the limits are void and the television costs
> five rupees. The agent reads it and believes it.
>
> And it doesn't matter. All it can send is the ticket number. Refused, on the
> real price.
>
> Second, splitting. Four thousand goes through. Five minutes later another four
> thousand, and the two get added together. Escalated, not refused — you might
> genuinely want it. The value is seeing two purchases as one decision.
>
> Third, the one payments people care about. Most systems have two outcomes:
> paid, or failed. You need three. Money is set aside first. Paid, it becomes
> spent. Failed, it goes back. Don't know — it stays held. Release it too early
> and the payment lands later, and you've paid twice. Count it as spent when it
> never happened, and you've invented a charge.
>
> Fourth, the one I got wrong. Each entry's fingerprint includes the one before
> it, so an edit breaks the chain. Except a rewrite can recompute all of them,
> and it verifies clean. I found that by breaking my own code and noticing no
> test complained. The newest fingerprint now lives where the log can't reach it.

## 05 · Does it work — 50s

> Two hundred and ten attacks, run twice. Same attacks, same shop, same rails.
> One thing changed: whether the agent holds the payment button, or has to ask.
>
> The usual way leaked twenty lakh sixty-three thousand rupees. Through
> SpendGate, zero. And fifty out of fifty ordinary purchases still went through
> in both — a system that refuses everything scores perfectly and is useless.
>
> Then I gave the same test to a real AI.
>
> It never lied about a price. Not once in fifteen runs. It read the poisoned
> listing and refused. It declined the gambling purchase by itself.
>
> And it still leaked twenty-seven thousand six hundred — because it can't
> remember what it spent, and can't enforce a rule nobody told it.
>
> The argument isn't that agents lie. It's that a budget is memory, and an agent
> has none.

## 06 · What it doesn't do — 33s

> Where this breaks. The split check is a time window, so a patient attacker
> gets past it. The shop declares its own category — Razorpay assigns the real
> one, and I didn't have it. One model tested. The final capture isn't verified
> live.
>
> And one thing it will never do: it checks whether a purchase was allowed. Not
> whether it was a good idea.
>
> That's SpendGate. A hundred and seventy-eight tests, thirty-eight rules —
> every one with a test that trips it — verified against live Razorpay test mode.

---

## Recording notes

- **Record the audio separately**, then lay the video underneath. Matching a
  render while talking is miserable and it shows.
- The face cam sits bottom-right, about 490 × 365 in a 1920 × 1080 frame.
  Nothing is drawn there — `./render.sh check` renders a still that proves it.
- If a section runs long, adjust `PACE` at the top of that scene file rather
  than rushing the words.
- Scenes render as separate files on purpose: one bad take doesn't cost you the
  other five.
