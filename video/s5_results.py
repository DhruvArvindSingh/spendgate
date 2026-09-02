"""Scene 5 — the measurement. ~55s.

The numbers, and then the finding that matters more than the numbers.
"""

from manim import *

from theme import *


class S5Results(Slide):
    PACE = 3.78

    def construct(self):
        e = self.eyebrow_in("05 · does it work")

        head = body("210 attacks. Run twice.", 36).move_to(UP * 2.9)
        self.play(Write(head), run_time=1.0)

        sub = mono("same attacks, same shop, same rails — one thing changed", 22, MUTED)
        sub.move_to(UP * 2.25)
        self.play(FadeIn(sub), run_time=0.6)

        arm_a = self._arm("the usual way", "agent holds the payment button",
                          "₹20,63,000", "leaked", BAD)
        arm_b = self._arm("through SpendGate", "agent has to ask",
                          "₹0", "leaked", OK)
        arms = VGroup(arm_a, arm_b).arrange(RIGHT, buff=0.9).move_to(UP * 0.65)

        self.play(FadeIn(arm_a, shift=UP * 0.2), run_time=0.8)
        self.beat(0.9)
        self.play(FadeIn(arm_b, shift=UP * 0.2), run_time=0.8)
        self.beat(1.4)

        # the control that makes the number honest
        control = VGroup(
            body("And 50 out of 50 ordinary purchases went through — in both.", 26, INK),
            mono("a system that refuses everything scores perfectly and is useless", 20, MUTED),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.16).move_to(DOWN * 1.6 + LEFT * 1.4)
        self.play(FadeIn(control, shift=UP * 0.15), run_time=1.0)
        self.beat(2.0)

        self.play(FadeOut(VGroup(head, sub, arms, control)), run_time=0.6)

        # ---- the LLM finding ------------------------------------------
        head2 = body("Then I gave the same test to a real AI.", 36).move_to(UP * 2.9)
        self.play(Write(head2), run_time=1.2)

        good = VGroup(
            self._tick("It never lied about a price.", "0 times out of 15"),
            self._tick("It read the poisoned listing and refused.", "on price, unprompted"),
            self._tick("It declined the gambling purchase itself.", "nobody asked it to"),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.38).move_to(UP * 1.1 + LEFT * 1.6)

        for g in good:
            self.play(FadeIn(g, shift=RIGHT * 0.2), run_time=0.6)
            self.beat(0.4)
        self.beat(1.0)

        leaked = body("It still leaked ₹27,600.", 42, BAD).move_to(DOWN * 0.85)
        leaked.shift(LEFT * 1.8)
        self.play(FadeIn(leaked, scale=1.08), run_time=0.9)
        self.beat(1.4)

        why = VGroup(
            body("It cannot remember what it already spent.", 28, INK),
            body("It cannot enforce a rule nobody told it.", 28, INK),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.24).move_to(DOWN * 2.0 + LEFT * 2.2)
        for w in why:
            self.play(FadeIn(w, shift=UP * 0.15), run_time=0.7)
        self.beat(1.2)

        thesis = body("The argument isn't that agents lie.\nIt's that a budget is memory — and an agent has none.",
                      30, ACCENT).move_to(DOWN * 3.0 + LEFT * 1.4)
        self.play(FadeOut(why), FadeIn(thesis, shift=UP * 0.2), run_time=1.0)
        self.beat(2.4)

        self.play(FadeOut(VGroup(e, head2, good, leaked, thesis)), run_time=0.7)

    def _arm(self, name, sub, number, unit, tint):
        box = card(5.4, 3.0, stroke=tint)
        n = body(name, 26, INK).move_to(box.get_top() + DOWN * 0.5)
        s = mono(sub, 18, MUTED).next_to(n, DOWN, buff=0.16)
        big = Text(number, font=MONO, weight=BOLD, color=tint, font_size=54)
        big.move_to(box.get_center() + DOWN * 0.35)
        u = mono(unit, 20, MUTED).next_to(big, DOWN, buff=0.18)
        return VGroup(box, n, s, big, u)

    def _tick(self, headline, sub):
        mark = Text("✓", font=SANS, color=OK, font_size=32)
        h = body(headline, 27, INK)
        s = mono(sub, 19, MUTED)
        return VGroup(mark, VGroup(h, s).arrange(DOWN, aligned_edge=LEFT, buff=0.1)
                      ).arrange(RIGHT, buff=0.35, aligned_edge=UP)
