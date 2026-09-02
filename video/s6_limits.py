"""Scene 6 — limitations and close. ~35s.

The section most submissions skip. Stating the edges of what was built is the
cheapest credibility available, and it is one of the four things being graded.
"""

from manim import *

from theme import *


class S6Limits(Slide):
    PACE = 3.43

    def construct(self):
        e = self.eyebrow_in("06 · what it does not do")

        head = body("Where this breaks.", 36).move_to(UP * 2.9)
        self.play(Write(head), run_time=0.9)

        limits = VGroup(
            self._limit("The split-purchase check is a time window.",
                        "wait long enough between purchases and it misses"),
            self._limit("The shop declares its own category.",
                        "Razorpay assigns the real one — I did not have it"),
            self._limit("One AI model tested.",
                        "another may lie where this one did not"),
            self._limit("The final capture is not verified live.",
                        "orders and refusals are; completing a payment needs a human"),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.38).move_to(UP * 0.85 + LEFT * 1.5)

        for l in limits:
            self.play(FadeIn(l, shift=RIGHT * 0.2), run_time=0.55)
            self.beat(0.35)
        self.beat(1.4)

        boundary = body("And one it will never do:", 28, MUTED).move_to(DOWN * 1.75 + LEFT * 3.6)
        self.play(FadeIn(boundary), run_time=0.5)

        never = body("It checks whether a purchase was allowed —\nnot whether it was a good idea.",
                     30, INK).move_to(DOWN * 2.6 + LEFT * 2.0)
        self.play(FadeIn(never, shift=UP * 0.15), run_time=1.0)
        self.beat(2.2)

        self.play(FadeOut(VGroup(head, limits, boundary, never)), run_time=0.6)

        # ---- close ----------------------------------------------------
        final = VGroup(
            Text("SpendGate", font=SANS, weight=BOLD, color=INK, font_size=64),
            mono("the agent proposes.  it decides, pays, and proves.", 26, ACCENT),
        ).arrange(DOWN, buff=0.4).move_to(UP * 0.9)
        self.play(FadeIn(final[0], scale=1.05), run_time=0.9)
        self.play(Write(final[1]), run_time=1.3)

        facts = VGroup(
            mono("178 tests", 22, MUTED),
            mono("38 rules, every one with a test that trips it", 22, MUTED),
            mono("verified against live Razorpay test mode", 22, MUTED),
        ).arrange(DOWN, buff=0.22).move_to(DOWN * 1.35 + LEFT * 1.2)
        self.play(LaggedStart(*[FadeIn(f, shift=UP * 0.1) for f in facts],
                              lag_ratio=0.3), run_time=1.2)
        self.beat(2.5)
        self.play(FadeOut(VGroup(e, final, facts)), run_time=1.0)

    def _limit(self, headline, sub):
        dot = Dot(radius=0.06, color=WARN)
        h = body(headline, 27, INK)
        s = mono(sub, 19, MUTED)
        return VGroup(dot, VGroup(h, s).arrange(DOWN, aligned_edge=LEFT, buff=0.1)
                      ).arrange(RIGHT, buff=0.35, aligned_edge=UP)
