"""Scene 5 — the measurement. ~56s."""

from manim import *

from theme import *


class S5Results(Slide):
    PACE = 3.37

    def construct(self):
        e = self.eyebrow_in("05 · does it work")

        h = self.heading("210 attacks. Run twice.")
        sub = mono("same attacks, same shop, same rails — one thing changed", 21, MUTED)
        arms = row(
            self._arm("the usual way", "agent holds the payment button",
                      "₹20,63,000", "leaked", BAD),
            self._arm("through SpendGate", "agent has to ask", "₹0", "leaked", OK),
            buff=0.8)
        group = stack(sub, arms, buff=0.45, align=ORIGIN)
        place(group)

        self.play(FadeIn(sub), run_time=0.6)
        self.play(FadeIn(arms[0], shift=UP * 0.2), run_time=0.8)
        self.beat(1.0)
        self.play(FadeIn(arms[1], shift=UP * 0.2), run_time=0.8)
        self.beat(1.6)
        self.play(FadeOut(group), FadeOut(h), run_time=0.55)

        # the control that makes the number honest
        h2 = self.heading("And the control that makes it honest.")
        control = stack(
            body("50 out of 50 ordinary purchases went through — in both.", 28, INK),
            mono("a system that refuses everything scores perfectly and is useless", 21, MUTED),
            buff=0.32, align=ORIGIN)
        place(control)
        self.play(FadeIn(control[0], shift=UP * 0.15), run_time=0.8)
        self.play(FadeIn(control[1]), run_time=0.6)
        self.beat(1.8)
        self.play(FadeOut(control), FadeOut(h2), run_time=0.55)

        # ---- the LLM finding ------------------------------------------
        h3 = self.heading("Then I gave the same test to a real AI.")
        good = stack(
            tick("It never lied about a price.", "0 times out of 15"),
            tick("It read the poisoned listing and refused.", "on price, unprompted"),
            tick("It declined the gambling purchase itself.", "nobody asked it to"),
            buff=0.42)
        place(good, align="left")
        for g in good:
            self.play(FadeIn(g, shift=RIGHT * 0.2), run_time=0.6)
            self.beat(0.45)
        self.beat(1.2)
        self.play(FadeOut(good), FadeOut(h3), run_time=0.55)

        h4 = self.heading("And it still leaked ₹27,600.", 40)
        why = stack(
            body("It cannot remember what it already spent.", 28, INK),
            body("It cannot enforce a rule nobody told it.", 28, INK),
            buff=0.3, align=ORIGIN)
        place(why)
        self.beat(1.0)
        for w in why:
            self.play(FadeIn(w, shift=UP * 0.15), run_time=0.7)
        self.beat(1.2)
        self.play(FadeOut(why), FadeOut(h4), run_time=0.55)

        thesis = stack(
            body("The argument isn't that agents lie.", 32, INK),
            body("It's that a budget is memory —", 32, ACCENT),
            body("and an agent has none.", 32, ACCENT),
            buff=0.34, align=ORIGIN)
        place(thesis, top=SAFE_TOP)
        self.play(FadeIn(thesis[0], shift=UP * 0.2), run_time=0.8)
        self.play(FadeIn(thesis[1], shift=UP * 0.2), run_time=0.7)
        self.play(FadeIn(thesis[2], shift=UP * 0.2), run_time=0.7)
        self.beat(2.4)
        self.play(FadeOut(VGroup(e, thesis)), run_time=0.7)

    def _arm(self, name, sub, number, unit, tint):
        big = Text(number, font=MONO, weight=BOLD, color=tint, font_size=46)
        inner = stack(body(name, 25, INK), mono(sub, 17, MUTED), big,
                      mono(unit, 19, MUTED), buff=0.26, align=ORIGIN)
        return panel(inner, stroke=tint, pad_x=0.6, pad_y=0.4)
