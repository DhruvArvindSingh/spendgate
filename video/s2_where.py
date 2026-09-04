"""Scene 2 — where this sits. ~26s."""

from manim import *

from theme import *


class S2Where(Slide):
    VOICE = "s2"
    SPEED = 1.76
    SEGMENTS = (2.80, 0.91, 2.80, 0.55,)
    HOLDS = (1.00, 1.00, 1.00, 0.89,)
    TAIL = 0.00

    def construct(self):
        e = self.eyebrow_in("02 · where it fits")
        h = self.heading("This is not an empty field.")

        rows = [("Discovery & checkout", "ACP", LINE, MUTED),
                ("Proof of authorisation", "AP2", LINE, MUTED),
                ("Keeping score — is it STILL within budget?", "nobody", BAD, BAD),
                ("Moving the money", "Razorpay", LINE, MUTED)]
        cards = stack(*[table_row(n, "", o, t, width=9.6, height=0.78, stroke=st)
                        for n, o, st, t in rows], buff=0.18, align=ORIGIN)
        place(cards)

        self.play(LaggedStart(*[FadeIn(c, shift=RIGHT * 0.3) for c in cards],
                              lag_ratio=0.5), run_time=2.2)
        gap = cards[2]
        self.cue(2)
        self.play(Flash(gap[0], color=BAD, line_length=0.22, num_lines=18,
                        flash_radius=0.8), gap.animate.scale(1.04), run_time=0.8)
        self.beat(0.7)
        self.play(FadeOut(cards), FadeOut(h), run_time=0.45)

        # ---- the spec quote -------------------------------------------
        h2 = self.heading("Google's own specification says:")
        quote = stack(
            body("\"the amount spent MUST be added to the", 30, INK),
            body(" accumulated total for future evaluation.\"", 30, INK),
            buff=0.24, align=ORIGIN)
        bar = Line(quote.get_top(), quote.get_bottom(), stroke_color=ACCENT,
                   stroke_width=3).next_to(quote, LEFT, buff=0.42)
        block = VGroup(bar, quote)
        place(block)
        self.play(Create(bar), run_time=0.4)
        self.play(Write(quote), run_time=1.8)
        self.beat(0.7)
        self.play(FadeOut(block), FadeOut(h2), run_time=0.45)

        # ---- the turn -------------------------------------------------
        turn = stack(
            body("It says the budget must be tracked.", 34, INK),
            body("It does not say who tracks it.", 34, ACCENT),
            body("That is this project.", 34, INK),
            buff=0.5, align=ORIGIN)
        place(turn, top=SAFE_TOP)
        self.cue(3)
        for i, line in enumerate(turn):
            if i == 2:
                self.cue(4)            # "that's this project" lands on its own
            self.play(FadeIn(line, shift=UP * 0.25), run_time=0.75)
        self.beat(1.0)
        self.tail(0.55)
        self.play(FadeOut(VGroup(e, turn)), run_time=0.55)
