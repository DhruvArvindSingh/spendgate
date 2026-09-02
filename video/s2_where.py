"""Scene 2 — where this sits. ~31s."""

from manim import *

from theme import *


class S2Where(Slide):
    PACE = 2.42

    def construct(self):
        e = self.eyebrow_in("02 · where it fits")
        h = self.heading("Three standards already describe agent payments.")

        # Two columns, not three: the captions that were here shrank to
        # illegibility inside a narrow middle column, and the narration says
        # them anyway.
        rows = [
            ("Discovery & checkout", "ACP", LINE, MUTED),
            ("Proof of authorisation", "AP2", LINE, MUTED),
            ("Keeping score — is it STILL within budget?", "nobody", BAD, BAD),
            ("Moving the money", "Razorpay", LINE, MUTED),
        ]
        cards = stack(*[table_row(name, "", owner, tint, width=9.6, height=0.8,
                                  stroke=stroke)
                        for name, owner, stroke, tint in rows],
                      buff=0.18, align=ORIGIN)
        place(cards)

        for i, c in enumerate(cards):
            self.play(FadeIn(c, shift=RIGHT * 0.2), run_time=0.5)
            if i == 1:
                self.beat(0.5)
        self.beat(1.0)

        gap = cards[2]
        self.play(Flash(gap[0], color=BAD, line_length=0.2, num_lines=16,
                        flash_radius=0.7), gap.animate.scale(1.03), run_time=0.8)
        self.beat(1.6)
        self.play(FadeOut(cards), FadeOut(h), run_time=0.55)

        # ---- the quote that justifies the project ---------------------
        h2 = self.heading("It is not that nobody thought of it.")
        quote = stack(
            body("\"Evaluating the budget requires tracking the total", 28, INK),
            body(" amount spent … the amount MUST be added to the", 28, INK),
            body(" accumulated total for future evaluation.\"", 28, INK),
            mono("— Google's AP2 specification", 21, MUTED),
            buff=0.24)
        bar = Line(quote.get_top(), quote.get_bottom(),
                   stroke_color=ACCENT, stroke_width=3).next_to(quote, LEFT, buff=0.4)
        block = VGroup(bar, quote)
        place(block)

        self.play(Create(bar), Write(quote), run_time=2.2)
        self.beat(1.4)
        self.play(FadeOut(block), FadeOut(h2), run_time=0.5)

        # ---- the turn -------------------------------------------------
        turn = stack(
            body("It says the budget must be tracked.", 34, INK),
            body("It does not say who tracks it.", 34, ACCENT),
            body("That is this project.", 34, INK),
            buff=0.5, align=ORIGIN)
        place(turn)
        for line in turn:
            self.play(FadeIn(line, shift=UP * 0.2), run_time=0.85)
            self.beat(0.5)
        self.beat(1.8)
        self.play(FadeOut(VGroup(e, turn)), run_time=0.7)
