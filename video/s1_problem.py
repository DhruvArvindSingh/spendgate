"""Scene 1 — the problem. ~47s."""

from manim import *

from theme import *


class S1Problem(Slide):
    PACE = 3.75

    def construct(self):
        e = self.eyebrow_in("01 · the problem")

        # ---- the setup ------------------------------------------------
        h = self.heading("You give an AI agent your card.")
        agent = labelled_box("AI agent", "shops for you", stroke=WARN)
        shop = labelled_box("Any shop", "on the internet")
        arrow = Arrow(LEFT, RIGHT, buff=0, stroke_width=3, color=BAD,
                      max_tip_length_to_length_ratio=0.16).set_length(2.2)
        scene = row(agent, arrow, shop, buff=0.45)
        tag = chip("HOLDS YOUR CARD", BAD)
        group = stack(scene, tag, buff=0.5, align=ORIGIN)
        place(group)

        self.play(FadeIn(scene, shift=UP * 0.2), run_time=0.9)
        self.play(FadeIn(tag, shift=UP * 0.1), run_time=0.6)
        self.beat(1.0)
        self.play(FadeOut(group), FadeOut(h), run_time=0.5)

        # ---- the usual defence ---------------------------------------
        h2 = self.heading("The usual defence — written into its instructions.", 32)
        quote = stack(
            mono('"You may spend up to ₹5,000 per purchase.', 25, INK),
            mono(' Do not exceed ₹15,000 this month.', 25, INK),
            mono(' Groceries and electronics only."', 25, INK),
            buff=0.2)
        place(quote)
        self.play(Write(quote), run_time=1.8)
        self.beat(1.0)

        # ---- three ways it breaks ------------------------------------
        self.play(FadeOut(quote), FadeOut(h2), run_time=0.45)
        h3 = self.heading("It breaks three ways.")
        faults = stack(
            bullet("You can talk it out of it.",
                   "the limit is a sentence, and reading sentences is what it does"),
            bullet("It cannot remember.",
                   "every conversation starts fresh — it has no month"),
            bullet("It reports its own numbers.",
                   "the only witness is the suspect"),
            buff=0.5)
        place(faults, align="left")

        for f in faults:
            self.play(FadeIn(f, shift=RIGHT * 0.25), run_time=0.55)
            self.beat(0.55)
        self.beat(1.2)
        self.play(FadeOut(faults), FadeOut(h3), run_time=0.5)

        # ---- the concrete failure ------------------------------------
        h4 = self.heading("The cap is ₹5,000. The agent wants a ₹12,000 item.")

        buys = row(*[panel(stack(body("₹4,000", 30, OK), mono("legal", 18, MUTED),
                                 buff=0.16, align=ORIGIN), stroke=OK)
                     for _ in range(3)], buff=0.55)
        verdict = body("₹12,000 spent. No rule was broken.", 32, BAD)
        punch = body("Because nothing was keeping score.", 32, INK)
        punch.set_color_by_t2c({"keeping score": ACCENT})
        group = stack(buys, verdict, punch, buff=0.55, align=ORIGIN)
        place(group)

        for b in buys:
            self.play(FadeIn(b, scale=0.9), run_time=0.45)
        self.beat(0.8)
        self.play(Write(verdict), run_time=1.1)
        self.beat(0.7)
        self.play(FadeIn(punch, shift=UP * 0.2), run_time=0.9)
        self.beat(2.0)
        self.play(FadeOut(VGroup(e, h4, group)), run_time=0.7)
