"""Scene 2 — where this sits. ~45s.

Goal: show the viewer that the standards already exist, that they solve
different problems, and that the missing layer is a specific one.
"""

from manim import *

from theme import *


class S2Where(Slide):
    PACE = 2.58

    def construct(self):
        e = self.eyebrow_in("02 · where it fits")

        head = body("Three standards already describe agent payments.", 36).move_to(UP * 2.7)
        self.play(Write(head), run_time=1.4)

        rows = [
            ("Discovery & checkout", "what is in the cart, at what price", "ACP", INK, LINE),
            ("Proof of authorisation", "did a human allow this", "AP2", INK, LINE),
            ("Keeping score", "is it STILL within budget, right now", "—", BAD, BAD),
            ("Moving the money", "the actual payment", "Razorpay", INK, LINE),
        ]

        cards = VGroup()
        for name, sub, owner, tint, stroke in rows:
            box = card(9.4, 0.98, stroke=stroke)
            label = body(name, 26, tint).move_to(box.get_left() + RIGHT * 2.6)
            caption = mono(sub, 19, MUTED).next_to(label, DOWN, buff=0.1, aligned_edge=LEFT)
            who = mono(owner, 22, tint if owner != "—" else BAD)
            who.move_to(box.get_right() + LEFT * 1.1)
            cards.add(VGroup(box, VGroup(label, caption).move_to(
                box.get_left() + RIGHT * 3.2), who))

        cards.arrange(DOWN, buff=0.22).move_to(UP * 0.35)

        for i, c in enumerate(cards):
            self.play(FadeIn(c, shift=RIGHT * 0.2), run_time=0.5)
            if i == 1:
                self.beat(0.5)
        self.beat(1.0)

        # ---- the gap --------------------------------------------------
        gap = cards[2]
        self.play(gap.animate.scale(1.04), Flash(gap[0], color=BAD, line_length=0.2,
                                                 num_lines=16, flash_radius=0.6),
                  run_time=0.8)
        nobody = chip("NOBODY BUILDS THIS", BAD).next_to(gap, DOWN, buff=0.35).shift(LEFT * 2.0)
        self.play(FadeIn(nobody, shift=UP * 0.15), run_time=0.6)
        self.beat(1.6)

        self.play(FadeOut(VGroup(head, cards, nobody)), run_time=0.6)

        # ---- the quote that justifies the whole project ---------------
        q = VGroup(
            mono("Google's AP2 specification says:", 22, MUTED),
            body("\"Evaluating the budget requires tracking the", 30, INK),
            body(" total amount spent … the amount MUST be added", 30, INK),
            body(" to the accumulated total for future evaluation.\"", 30, INK),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.24).move_to(UP * 1.4 + LEFT * 0.6)
        bar = Line(q.get_top() + LEFT * 0.45, q.get_bottom() + LEFT * 0.45,
                   stroke_color=ACCENT, stroke_width=3)

        self.play(FadeIn(q[0]), run_time=0.4)
        self.play(Create(bar), Write(VGroup(*q[1:])), run_time=2.2)
        self.beat(1.2)

        note = body("It says the budget must be tracked.\nIt does not say who tracks it.",
                    32, ACCENT).move_to(DOWN * 1.5 + LEFT * 1.8)
        self.play(FadeIn(note, shift=UP * 0.2), run_time=1.0)
        self.beat(1.8)

        final = body("That is this project.", 36, INK).move_to(DOWN * 2.9 + LEFT * 3.2)
        self.play(Write(final), run_time=0.9)
        self.beat(1.5)
        self.play(FadeOut(VGroup(e, q, bar, note, final)), run_time=0.7)
