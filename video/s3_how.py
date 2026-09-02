"""Scene 3 — how it works. ~61s. The core of the video."""

from manim import *

from theme import *


class S3How(Slide):
    PACE = 4.36

    def construct(self):
        e = self.eyebrow_in("03 · how it works")

        self._request_shape()
        self._where_price_comes_from()
        self._pipeline()

        self.play(FadeOut(e), run_time=0.4)

    # ------------------------------------------------- the request shape
    def _request_shape(self):
        h = self.heading("The agent's entire vocabulary.")
        code = stack(
            mono("request_payment(", 28, INK),
            mono("    mandate_id          = \"mnd_01J9F2K7\"", 25, ACCENT),
            mono("    checkout_session_id = \"cs_8fK2mNp\"", 25, ACCENT),
            mono("    agent_id            = \"agt_shopper_01\"", 25, ACCENT),
            mono(")", 28, INK),
            buff=0.18)

        absent_label = mono("what is deliberately absent", 21, BAD)
        absent = row(*[mono(f, 25, MUTED) for f in
                       ("amount", "item", "merchant", "currency")], buff=0.85)
        absent_block = stack(absent_label, absent, buff=0.3)

        group = stack(code, absent_block, buff=0.7)
        place(group)

        self.play(Write(code), run_time=2.0)
        self.beat(1.0)
        self.play(FadeIn(absent_label), run_time=0.45)
        self.play(LaggedStart(*[FadeIn(a, shift=UP * 0.15) for a in absent],
                              lag_ratio=0.25), run_time=1.1)
        strikes = VGroup(*[Line(a.get_left() + LEFT * 0.1, a.get_right() + RIGHT * 0.1,
                                stroke_color=BAD, stroke_width=2.5) for a in absent])
        self.play(LaggedStart(*[Create(s) for s in strikes], lag_ratio=0.2), run_time=0.9)
        self.beat(1.0)

        self.play(FadeOut(VGroup(group, strikes)), FadeOut(h), run_time=0.5)
        punch = body("There is nowhere to put a lie.", 40, INK)
        punch.set_color_by_t2c({"nowhere": ACCENT})
        place(punch, top=SAFE_TOP)
        self.play(FadeIn(punch, scale=1.06), run_time=0.9)
        self.beat(1.8)
        self.play(FadeOut(punch), run_time=0.5)

    # -------------------------------------------- where the price is from
    def _where_price_comes_from(self):
        h = self.heading("So where does the price come from?")

        agent = labelled_box("Agent", "untrusted", stroke=WARN)
        gate = labelled_box("SpendGate", "plain code", stroke=ACCENT, label_color=ACCENT)
        shop = labelled_box("Merchant", "knows the price")
        boxes = row(agent, gate, shop, buff=1.9)

        a1 = Arrow(agent.get_right(), gate.get_left(), buff=0.18, stroke_width=3,
                   color=ACCENT, max_tip_length_to_length_ratio=0.2)
        a2 = Arrow(gate.get_right(), shop.get_left(), buff=0.18, stroke_width=3,
                   color=ACCENT, max_tip_length_to_length_ratio=0.2)
        # No labels on these two arrows: at this box spacing the text is wider
        # than the arrow and lands on the boxes. The return arrow carries the
        # only label that matters.

        back = CurvedArrow(shop.get_bottom() + DOWN * 0.1, gate.get_bottom() + DOWN * 0.1,
                           angle=-0.75, color=OK, stroke_width=3, tip_length=0.2)
        l3 = mono("₹1,200 — from the shop", 21, OK).next_to(back, DOWN, buff=0.14)

        diagram = VGroup(boxes, a1, a2, back, l3)
        note = mono("the agent is never on this connection", 20, BAD)
        group = stack(diagram, note, buff=0.5, align=ORIGIN)
        place(group)

        self.play(FadeIn(boxes), run_time=0.8)
        self.play(GrowArrow(a1), run_time=0.6)
        self.play(GrowArrow(a2), run_time=0.6)
        self.play(Create(back), FadeIn(l3), run_time=0.9)
        self.beat(1.0)
        self.play(FadeIn(note, shift=UP * 0.15), run_time=0.6)
        self.beat(1.6)
        self.play(FadeOut(group), FadeOut(h), run_time=0.6)

    # ------------------------------------------------------- the pipeline
    def _pipeline(self):
        h = self.heading("Then plain code decides. 38 rules, in order.")

        stages = [
            ("Is the permission slip real?", "R01–R08", "refuse", BAD),
            ("Is the basket real, and unpaid?", "R09–R16", "refuse", BAD),
            ("Is it inside the hard limits?", "R17–R24", "refuse", BAD),
            ("Is this a duplicate or a race?", "R25–R29, R38", "refuse", BAD),
            ("Is it something you'd want to see?", "R30–R37", "ask you", WARN),
        ]
        rows = stack(*[table_row(q, ids, outcome, tint, width=10.2, height=0.66)
                       for q, ids, outcome, tint in stages],
                     buff=0.13, align=ORIGIN)
        place(rows)

        for r in rows:
            self.play(FadeIn(r, shift=RIGHT * 0.2), run_time=0.42)
        self.beat(1.2)
        self.play(FadeOut(rows), FadeOut(h), run_time=0.5)

        # The rule that governs all of them gets its own moment rather than a
        # caption squeezed under a table that already fills the band.
        first = body("First objection wins.\nOne reason, never a list.", 34, ACCENT)
        place(first, top=SAFE_TOP)
        self.play(FadeIn(first, shift=UP * 0.2), run_time=0.9)
        self.beat(2.0)
        self.play(FadeOut(first), run_time=0.5)
