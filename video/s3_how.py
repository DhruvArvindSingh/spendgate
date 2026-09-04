"""Scene 3 — how it works. ~56s. The core of the video."""

from manim import *

from theme import *


class S3How(Slide):
    VOICE = "s3"
    SPEED = 1.88
    SEGMENTS = (2.16, 1.16, 2.80, 1.51, 2.54, 1.47, 1.50,)
    HOLDS = (1.00, 1.00, 1.59, 1.00, 1.00, 1.00, 1.00,)
    TAIL = 0.00

    def construct(self):
        e = self.eyebrow_in("03 · how it works")
        self._request_shape()
        self._where_price_comes_from()
        self._pipeline()
        self.play(FadeOut(e), run_time=0.4)

    def _request_shape(self):
        h = self.heading("The agent's entire vocabulary.")
        code = stack(
            mono("request_payment(", 28, INK),
            mono("    mandate_id          = \"mnd_01J9F2K7\"", 25, ACCENT),
            mono("    checkout_session_id = \"cs_8fK2mNp\"", 25, ACCENT),
            mono("    agent_id            = \"agt_shopper_01\"", 25, ACCENT),
            mono(")", 28, INK),
            buff=0.18)
        absent = row(*[mono(f, 25, MUTED) for f in
                       ("amount", "item", "merchant", "currency")], buff=0.85)
        label = mono("what is deliberately absent", 21, BAD)
        group = stack(code, stack(label, absent, buff=0.3), buff=0.65)
        place(group)

        self.cue(2)
        self.play(LaggedStart(*[FadeIn(l, shift=RIGHT * 0.2) for l in code],
                              lag_ratio=0.35), run_time=1.9)
        self.beat(0.6)
        self.play(FadeIn(label), run_time=0.4)
        self.play(LaggedStart(*[FadeIn(a, shift=UP * 0.2) for a in absent],
                              lag_ratio=0.3), run_time=1.2)
        strikes = VGroup(*[Line(a.get_left() + LEFT * 0.1, a.get_right() + RIGHT * 0.1,
                                stroke_color=BAD, stroke_width=2.5) for a in absent])
        self.play(LaggedStart(*[Create(s) for s in strikes], lag_ratio=0.25),
                  run_time=1.1)
        self.beat(0.6)

        self.play(FadeOut(VGroup(group, strikes)), FadeOut(h), run_time=0.45)
        punch = body("There is nowhere to put a lie.", 40, INK)
        punch.set_color_by_t2c({"nowhere": ACCENT})
        place(punch, top=SAFE_TOP)
        self.cue(3)
        self.play(FadeIn(punch, scale=1.08), run_time=0.9)
        self.beat(1.1)
        self.play(FadeOut(punch), run_time=0.45)

    def _where_price_comes_from(self):
        self.cue(4)
        h = self.heading("So where does the price come from?")
        agent = labelled_box("Agent", "untrusted", stroke=WARN)
        gate = labelled_box("SpendGate", "plain code", stroke=ACCENT, label_color=ACCENT)
        shop = labelled_box("Merchant", "knows the price")
        boxes = row(agent, gate, shop, buff=1.9)
        a1 = Arrow(agent.get_right(), gate.get_left(), buff=0.18, stroke_width=3,
                   color=ACCENT, max_tip_length_to_length_ratio=0.2)
        a2 = Arrow(gate.get_right(), shop.get_left(), buff=0.18, stroke_width=3,
                   color=ACCENT, max_tip_length_to_length_ratio=0.2)
        back = CurvedArrow(shop.get_bottom() + DOWN * 0.1, gate.get_bottom() + DOWN * 0.1,
                           angle=-0.75, color=OK, stroke_width=3, tip_length=0.2)
        price = mono("₹1,200 — from the shop", 21, OK).next_to(back, DOWN, buff=0.14)
        note = mono("the agent is never on this connection", 20, BAD)
        group = stack(VGroup(boxes, a1, a2, back, price), note, buff=0.5, align=ORIGIN)
        place(group)

        self.play(FadeIn(boxes), run_time=0.7)
        # A ticket travels agent -> gate, then the gate goes and asks the shop.
        ticket = mono('"cs_8fK2mNp"', 17, MUTED).move_to(a1.get_start())
        self.play(GrowArrow(a1), FadeIn(ticket), run_time=0.5)
        self.play(ticket.animate.move_to(a1.get_end()), run_time=0.7)
        self.play(FadeOut(ticket), GrowArrow(a2), run_time=0.5)
        self.play(Create(back), run_time=0.7)
        self.play(FadeIn(price, shift=UP * 0.1), run_time=0.5)
        self.beat(0.7)
        self.play(FadeIn(note, shift=UP * 0.15), run_time=0.6)
        self.beat(0.9)
        self.play(FadeOut(group), FadeOut(h), run_time=0.5)

    def _pipeline(self):
        self.cue(5)
        h = self.heading("Then plain code decides. 38 rules, in order.")
        stages = [("Is the permission slip real?", "R01–R08", "refuse", BAD),
                  ("Is the basket real, and unpaid?", "R09–R16", "refuse", BAD),
                  ("Is it inside the hard limits?", "R17–R24", "refuse", BAD),
                  ("Is this a duplicate or a race?", "R25–R29, R38", "refuse", BAD),
                  ("Is it something you'd want to see?", "R30–R37", "ask you", WARN)]
        rows = stack(*[table_row(q, i, o, t, width=10.2, height=0.64)
                       for q, i, o, t in stages], buff=0.13, align=ORIGIN)
        place(rows)
        self.play(LaggedStart(*[FadeIn(r, shift=RIGHT * 0.25) for r in rows],
                              lag_ratio=0.45), run_time=2.6)
        self.beat(0.9)
        # "and last — is it something you'd want to be asked about"
        self.cue(6)
        self.play(Indicate(rows[-1], color=WARN, scale_factor=1.03), run_time=1.0)
        self.beat(0.6)
        self.play(FadeOut(rows), FadeOut(h), run_time=0.45)

        first = body("First objection wins.\nOne reason, never a list.", 34, ACCENT)
        place(first, top=SAFE_TOP)
        self.cue(7)
        self.play(FadeIn(first, shift=UP * 0.2), run_time=0.9)
        self.beat(1.1)
        self.tail(0.45)
        self.play(FadeOut(first), run_time=0.45)
