"""Scene 7 — limitations and close. ~23s."""

from manim import *

from theme import *


class S7Limits(Slide):
    VOICE = "s7"
    SPEED = 2.04
    SEGMENTS = (2.41, 1.67,)
    HOLDS = (1.00, 1.00,)
    TAIL = 0.00

    def construct(self):
        e = self.eyebrow_in("07 · what it does not do")
        h = self.heading("Where this breaks.")
        limits = stack(
            bullet("The split check is a time window.",
                   "a patient attacker waits it out", WARN),
            bullet("The shop declares its own category.",
                   "Razorpay assigns the real one — I did not have it", WARN),
            bullet("It checks whether a purchase was allowed.",
                   "not whether it was a good idea", WARN),
            buff=0.45)
        place(limits, align="left")
        self.play(LaggedStart(*[FadeIn(l, shift=RIGHT * 0.3) for l in limits],
                              lag_ratio=0.5), run_time=2.2)
        self.beat(1.0)
        self.play(FadeOut(limits), FadeOut(h), FadeOut(e), run_time=0.5)

        # ---- close ----------------------------------------------------
        self.cue(2)
        name = Text("SpendGate", font=SANS, weight=BOLD, color=INK, font_size=62)
        tagline = mono("the agent proposes.  it decides, pays, and proves.", 24, ACCENT)
        facts = row(mono("187 tests", 20, MUTED), mono("·", 20, FAINT),
                    mono("38 rules", 20, MUTED), mono("·", 20, FAINT),
                    mono("6 models", 20, MUTED), mono("·", 20, FAINT),
                    mono("live Razorpay", 20, MUTED), buff=0.35)
        close = stack(name, tagline, facts, buff=0.55, align=ORIGIN)
        place(close, top=SAFE_TOP, grow=False)

        self.play(FadeIn(name, scale=1.06), run_time=0.8)
        self.play(Write(tagline), run_time=1.2)
        self.play(LaggedStart(*[FadeIn(f, shift=UP * 0.1) for f in facts],
                              lag_ratio=0.2), run_time=1.0)
        self.beat(1.4)
        self.tail(0.9)
        self.play(FadeOut(close), run_time=0.9)
