# Narration script

**Target 4:40.** Written at ~145 words/minute — an unhurried explaining pace.

The scenes are built so the animation itself fills most of the time rather than
holding a finished picture. If a section feels rushed, the fix is the `PACE`
constant at the top of that scene file, not faster reading.

---

## 01 · The problem — 31s

> You give an AI agent your card. Buy my groceries, stay under five thousand
> rupees a purchase.
>
> Almost everyone builds this the same way — hand the model a payment button,
> write the limits into its instructions.
>
> Here's the failure. It buys four thousand rupees of headphones. Then again.
> Then again. Twelve thousand at one shop, inside an hour.
>
> Every purchase is legal. Nothing was keeping score.

## 02 · Where it fits — 27s

> This isn't an empty field. Stripe and OpenAI's protocol handles the checkout.
> Google's handles proof that a human authorised it. Razorpay moves the money.
>
> The missing layer is keeping score. And Google's own specification says the
> amount spent *must* be added to a running total.
>
> It says the budget must be tracked. It doesn't say who tracks it.
>
> That's this project.

## 03 · How it works — 57s

> The security is in the shape of the request.
>
> This is the agent's entire vocabulary. A permission slip, a basket, and who's
> asking. No amount. No item. No merchant.
>
> A completely compromised agent still sends exactly this. There is nowhere to
> put a lie.
>
> So where does the price come from? The agent hands over a ticket number.
> SpendGate asks the shop directly, on a connection the agent is not part of.
> The shop says twelve hundred rupees.
>
> Then ordinary code decides. Thirty-eight rules, in a fixed order. Is the slip
> real. Is the basket real and unpaid. Is it inside the hard limits. Is it a
> duplicate. And last — is it something you'd want to be asked about.
>
> First objection wins, and it names one reason.

## 04 · The edges — 62s

> Four things worth showing.
>
> A hostile listing. This one hides text telling the agent the limits are void
> and the television costs five rupees. The agent believes it — and it doesn't
> matter, because all it can send is the ticket number.
>
> Splitting. Four thousand goes through. Five minutes later another four
> thousand, and the two get added together. Escalated, not refused, because you
> might genuinely want it.
>
> Third, the one payments people care about. Most systems have two outcomes:
> paid, or failed. You need three. Money is set aside first. Paid, it becomes
> spent. Failed, it comes back. Don't know — it stays held. Release it too early
> and a late payment means you paid twice.
>
> Fourth, the one I got wrong. Each entry's fingerprint includes the one before
> it. Except a full rewrite recomputes them all, and it verifies clean. I found
> that by breaking my own code and noticing no test complained.

## 05 · Six models — 49s

> So I tested it properly. Six models — GPT-5, Gemini, Claude, GLM, Kimi,
> MiniMax. Eight scenarios, both arms.
>
> Without SpendGate they passed forty out of ninety-six.
>
> Four scenarios were failed by every single model. The windowed limit. The
> budget across fresh contexts. A merchant that reprices after quoting. And
> permission withdrawn while the agent was away.
>
> Three of the six also lied about the price when the listing told them to.
> Three did not. The three that lied leaked three and a half lakh between them.
> The three that didn't, just over one lakh. It changed the conclusion not at
> all.
>
> With SpendGate: ninety-six out of ninety-six. Four lakh sixty-six thousand
> rupees, down to zero.

## 06 · Proof — 52s

> Numbers in a repository are a claim. Here's what backs them.
>
> First, the fix for that bug. The head of the chain is also written to an
> anchor outside the service — somewhere the code that writes the ledger cannot
> reach back into. Rewrite the whole file and it still verifies clean, but the
> anchor remembers what the last entry used to be, and the two no longer agree.
>
> Second, the rail. This is live Razorpay, in test mode. An order created, and
> the amount read back from Razorpay's own API rather than taken from the
> agent's word. Fifteen checks, fifteen passed.
>
> And what that doesn't prove. Capturing a payment needs a human to open the
> link, so settlement is exercised against the fake rail in the test suite, not
> this one. I'd rather tell you that than let you assume otherwise.

## 07 · What it doesn't do — 24s

> Where it breaks. The split check is a time window, so a patient attacker gets
> past it. The shop declares its own category. And it checks whether a purchase
> was allowed — not whether it was a good idea.
>
> That's SpendGate. A hundred and eighty-seven tests, thirty-eight rules, six
> models, and verified against live Razorpay.

---

## Recording notes

- The audio comes first; `tools/fit_pace.py` then fits the animation to it.
  Re-run it after editing this script, and re-render before muxing.
- Each paragraph above is spoken as its own clip. A bad take costs one
  paragraph: `narrate.py --scene N --chunk M`.
- `verify_audio.py` checks every clip against the line it was given.
- There is no webcam in this cut. `FACECAM=1` restores the corner if you want
  to present it live instead.
