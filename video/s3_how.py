"""Scene 3 — how it works. ~85s. The core of the video.

Three beats: the shape of the request, where the price comes from, and the
rule pipeline. Everything else in the project follows from these.
"""

from manim import *

from theme import *


class S3How(Slide):
    PACE = 4.48

    def construct(self):
        e = self.eyebrow_in("03 · how it works")

        # ================= beat 1: the request shape ==================
        head = body("The agent's entire vocabulary.", 36).move_to(UP * 2.9)
        self.play(Write(head), run_time=1.1)

        req = VGroup(
            mono("request_payment(", 30, INK),
            mono("    mandate_id          = \"mnd_01J9F2K7\"", 26, ACCENT),
            mono("    checkout_session_id = \"cs_8fK2mNp\"", 26, ACCENT),
            mono("    agent_id            = \"agt_shopper_01\"", 26, ACCENT),
            mono(")", 30, INK),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.2).move_to(UP * 1.35 + LEFT * 1.4)
        self.play(Write(req), run_time=2.0)
        self.beat(1.0)

        absent_head = mono("what is deliberately absent", 22, BAD).move_to(DOWN * 0.55 + LEFT * 3.4)
        self.play(FadeIn(absent_head), run_time=0.5)

        absent = VGroup(*[mono(f, 26, MUTED) for f in
                          ("amount", "item", "merchant", "currency")])
        absent.arrange(RIGHT, buff=0.9).next_to(absent_head, DOWN, buff=0.35, aligned_edge=LEFT)
        self.play(LaggedStart(*[FadeIn(a, shift=UP * 0.15) for a in absent],
                              lag_ratio=0.25), run_time=1.2)
        strikes = VGroup(*[Line(a.get_left() + LEFT * 0.12, a.get_right() + RIGHT * 0.12,
                                stroke_color=BAD, stroke_width=2.5) for a in absent])
        self.play(LaggedStart(*[Create(s) for s in strikes], lag_ratio=0.2), run_time=0.9)
        self.beat(0.8)

        punch = body("There is nowhere to put a lie.", 34, INK).move_to(DOWN * 2.35 + LEFT * 2.2)
        punch.set_color_by_t2c({"nowhere": ACCENT})
        self.play(FadeIn(punch, shift=UP * 0.2), run_time=0.9)
        self.beat(1.8)
        self.play(FadeOut(VGroup(head, req, absent_head, absent, strikes, punch)), run_time=0.6)

        # ================= beat 2: where the price comes from =========
        head2 = body("So where does the price come from?", 36).move_to(UP * 2.9)
        self.play(Write(head2), run_time=1.1)

        agent = labelled_box("Agent", "untrusted", 2.7, 1.1, stroke=WARN)
        agent.move_to(LEFT * 4.6 + UP * 1.5)
        gate = labelled_box("SpendGate", "plain code", 3.0, 1.1, stroke=ACCENT, label_color=ACCENT)
        gate.move_to(UP * 1.5)
        shop = labelled_box("Merchant", "knows the price", 2.9, 1.1)
        shop.move_to(RIGHT * 4.6 + UP * 1.5)

        self.play(FadeIn(agent), FadeIn(gate), FadeIn(shop), run_time=0.8)

        a1 = Arrow(agent.get_right(), gate.get_left(), buff=0.2, stroke_width=3,
                   color=ACCENT, max_tip_length_to_length_ratio=0.18)
        l1 = mono('"cs_8fK2mNp"', 20, MUTED).next_to(a1, UP, buff=0.14)
        self.play(GrowArrow(a1), FadeIn(l1), run_time=0.7)

        a2 = Arrow(gate.get_right(), shop.get_left(), buff=0.2, stroke_width=3,
                   color=ACCENT, max_tip_length_to_length_ratio=0.18)
        l2 = mono("what is this?", 20, MUTED).next_to(a2, UP, buff=0.14)
        self.play(GrowArrow(a2), FadeIn(l2), run_time=0.7)

        a3 = CurvedArrow(shop.get_bottom() + DOWN * 0.05, gate.get_bottom() + DOWN * 0.05,
                         angle=-0.7, color=OK, stroke_width=3, tip_length=0.2)
        l3 = mono("₹1,200 — from the shop", 22, OK).next_to(a3, DOWN, buff=0.12)
        self.play(Create(a3), FadeIn(l3), run_time=0.9)
        self.beat(1.0)

        # the agent is not on that path
        block = Cross(scale_factor=0.28, stroke_color=BAD, stroke_width=6)
        block.move_to((agent.get_center() + shop.get_center()) / 2 + DOWN * 1.75)
        blocked = DashedLine(agent.get_bottom() + DOWN * 0.15,
                             shop.get_bottom() + DOWN * 0.15,
                             stroke_color=BAD, stroke_width=2).set_opacity(0.5)
        note = mono("the agent is not on this connection", 20, BAD)
        note.next_to(block, DOWN, buff=0.22).shift(LEFT * 1.6)
        self.play(Create(blocked), run_time=0.5)
        self.play(FadeIn(block, scale=1.3), FadeIn(note), run_time=0.6)
        self.beat(1.8)

        self.play(FadeOut(VGroup(head2, agent, gate, shop, a1, l1, a2, l2, a3, l3,
                                 block, blocked, note)), run_time=0.6)

        # ================= beat 3: the pipeline =======================
        head3 = body("Then plain code decides. 38 rules, in order.", 36).move_to(UP * 2.9)
        self.play(Write(head3), run_time=1.3)

        stages = [
            ("Is the permission slip real?", "R01–R08", BAD, "refuse"),
            ("Is the basket real, and unpaid?", "R09–R16", BAD, "refuse"),
            ("Is it inside the hard limits?", "R17–R24", BAD, "refuse"),
            ("Is this a duplicate or a race?", "R25–R29, R38", BAD, "refuse"),
            ("Is it something you'd want to see?", "R30–R37", WARN, "ask you"),
        ]
        rows = VGroup()
        for q, ids, tint, outcome in stages:
            box = card(8.6, 0.82, stroke=LINE)
            qt = body(q, 24, INK).move_to(box.get_left() + RIGHT * 3.15)
            code = mono(ids, 18, MUTED).move_to(box.get_right() + LEFT * 2.3)
            res = mono(outcome, 19, tint).move_to(box.get_right() + LEFT * 0.85)
            rows.add(VGroup(box, qt, code, res))
        rows.arrange(DOWN, buff=0.2).move_to(UP * 0.45 + LEFT * 1.2)

        for r in rows:
            self.play(FadeIn(r, shift=RIGHT * 0.2), run_time=0.42)
        self.beat(0.9)

        first = body("First objection wins. One reason, never a list.", 28, ACCENT)
        first.move_to(DOWN * 2.55 + LEFT * 2.2)
        self.play(FadeIn(first, shift=UP * 0.2), run_time=0.9)
        self.beat(2.0)
        self.play(FadeOut(VGroup(e, head3, rows, first)), run_time=0.7)
