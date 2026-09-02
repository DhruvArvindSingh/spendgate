"""Scene 6 — limitations and close. ~36s."""

from manim import *

from theme import *


class S6Limits(Slide):
    PACE = 3.24

    def construct(self):
        e = self.eyebrow_in("06 · what it does not do")
        h = self.heading("Where this breaks.")

        limits = stack(
            bullet("The split-purchase check is a time window.",
                   "wait long enough between purchases and it misses", WARN),
            bullet("The shop declares its own category.",
                   "Razorpay assigns the real one — I did not have it", WARN),
            bullet("One AI model tested.",
                   "another may lie where this one did not", WARN),
            bullet("The final capture is not verified live.",
                   "orders and refusals are; completing a payment needs a human", WARN),
            buff=0.4)
        place(limits, align="left")

        for l in limits:
            self.play(FadeIn(l, shift=RIGHT * 0.2), run_time=0.55)
            self.beat(0.35)
        self.beat(1.4)
        self.play(FadeOut(limits), FadeOut(h), run_time=0.55)

        h2 = self.heading("And one it will never do.")
        never = stack(
            body("It checks whether a purchase was allowed.", 30, INK),
            body("Not whether it was a good idea.", 30, ACCENT),
            buff=0.34, align=ORIGIN)
        place(never)
        self.play(FadeIn(never[0], shift=UP * 0.15), run_time=0.8)
        self.play(FadeIn(never[1], shift=UP * 0.15), run_time=0.8)
        self.beat(2.0)
        self.play(FadeOut(never), FadeOut(h2), FadeOut(e), run_time=0.6)

        # ---- close ----------------------------------------------------
        name = Text("SpendGate", font=SANS, weight=BOLD, color=INK, font_size=62)
        tagline = mono("the agent proposes.  it decides, pays, and proves.", 24, ACCENT)
        facts = stack(
            mono("178 tests", 21, MUTED),
            mono("38 rules, every one with a test that trips it", 21, MUTED),
            mono("verified against live Razorpay test mode", 21, MUTED),
            buff=0.2, align=ORIGIN)
        close = stack(name, tagline, facts, buff=0.55, align=ORIGIN)
        place(close, top=SAFE_TOP, grow=False)

        self.play(FadeIn(name, scale=1.05), run_time=0.9)
        self.play(Write(tagline), run_time=1.3)
        self.play(LaggedStart(*[FadeIn(f, shift=UP * 0.1) for f in facts],
                              lag_ratio=0.3), run_time=1.2)
        self.beat(2.5)
        self.play(FadeOut(close), run_time=1.0)
