"""Scene 1 — the problem. ~55s.

Goal: by the end the viewer should feel that the normal design is broken for
reasons that have nothing to do with the agent being badly behaved.
"""

from manim import *

from theme import *


class S1Problem(Slide):
    PACE = 4.17

    def construct(self):
        e = self.eyebrow_in("01 · the problem")

        # ---- the setup ------------------------------------------------
        line = body("You give an AI agent your card.", 38).move_to(UP * 1.9)
        self.play(Write(line), run_time=1.2)

        agent = labelled_box("AI agent", "shops for you", 3.2, 1.3,
                             stroke=WARN, label_color=INK).move_to(LEFT * 4.2 + UP * 0.1)
        shop = labelled_box("Any shop", "on the internet", 3.2, 1.3).move_to(RIGHT * 4.2 + UP * 0.1)
        arrow = Arrow(agent.get_right(), shop.get_left(), buff=0.25,
                      stroke_width=3, color=BAD, max_tip_length_to_length_ratio=0.12)
        card_tag = chip("HOLDS YOUR CARD", BAD).next_to(agent, DOWN, buff=0.3)

        self.play(FadeIn(agent, shift=UP * 0.2), FadeIn(shop, shift=UP * 0.2), run_time=0.9)
        self.play(GrowArrow(arrow), FadeIn(card_tag, shift=UP * 0.1), run_time=0.8)
        self.beat(1.0)

        # ---- the usual defence ---------------------------------------
        self.play(FadeOut(VGroup(line, agent, shop, arrow, card_tag)), run_time=0.5)

        prompt_title = mono("the usual defence — written in its instructions", 22, MUTED)
        prompt = VGroup(
            mono('"You may spend up to ₹5,000 per purchase.', 26, INK),
            mono(' Do not exceed ₹15,000 this month.', 26, INK),
            mono(' Groceries and electronics only."', 26, INK),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.22)
        block = VGroup(prompt_title, prompt).arrange(DOWN, aligned_edge=LEFT, buff=0.45)
        block.move_to(UP * 1.2)
        self.play(FadeIn(prompt_title), run_time=0.4)
        self.play(Write(prompt), run_time=1.8)
        self.beat(0.8)

        # ---- three ways it breaks ------------------------------------
        faults = VGroup(
            self._fault("You can talk it out of it.",
                        "the limit is a sentence, and it reads sentences"),
            self._fault("It cannot remember.",
                        "every chat starts fresh — it has no month"),
            self._fault("It reports its own numbers.",
                        "the only witness is the suspect"),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.42).move_to(DOWN * 1.4 + LEFT * 2.2)

        for f in faults:
            self.play(FadeIn(f, shift=RIGHT * 0.25), run_time=0.55)
            self.beat(0.5)
        self.beat(1.2)

        self.play(FadeOut(VGroup(block, faults)), run_time=0.6)

        # ---- the concrete failure ------------------------------------
        head = body("The cap is ₹5,000. The agent wants a ₹12,000 item.", 34).move_to(UP * 2.4)
        self.play(Write(head), run_time=1.3)

        buys = VGroup(*[
            VGroup(card(2.6, 1.1, stroke=OK),
                   body("₹4,000", 30, OK).move_to(ORIGIN),
                   mono("legal", 18, MUTED).shift(DOWN * 0.32))
            for _ in range(3)
        ])
        for g in buys:
            g[1].move_to(g[0].get_center()).shift(UP * 0.14)
            g[2].move_to(g[0].get_center()).shift(DOWN * 0.3)
        buys.arrange(RIGHT, buff=0.55).move_to(UP * 0.75)

        for g in buys:
            self.play(FadeIn(g, scale=0.9), run_time=0.45)
        self.beat(0.7)

        total = body("₹12,000 spent. No rule was broken.", 34, BAD).move_to(DOWN * 0.75)
        self.play(Write(total), run_time=1.2)
        self.beat(0.6)

        punch = body("Because nothing was keeping score.", 34, INK).move_to(DOWN * 1.75)
        punch.set_color_by_t2c({"keeping score": ACCENT})
        self.play(FadeIn(punch, shift=UP * 0.2), run_time=0.9)
        self.beat(2.0)
        self.play(FadeOut(VGroup(e, head, buys, total, punch)), run_time=0.7)

    def _fault(self, headline: str, sub: str) -> VGroup:
        dot = Dot(radius=0.07, color=BAD)
        h = body(headline, 28, INK)
        s = mono(sub, 20, MUTED)
        txt = VGroup(h, s).arrange(DOWN, aligned_edge=LEFT, buff=0.12)
        return VGroup(dot, txt).arrange(RIGHT, buff=0.35, aligned_edge=UP)
