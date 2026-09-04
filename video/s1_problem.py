"""Scene 1 — the problem. ~30s.

Paced so the motion carries the time: nothing sits finished for long.
"""

from manim import *

from theme import *


class S1Problem(Slide):
    VOICE = "s1"
    SPEED = 1.65
    SEGMENTS = (1.21, 1.24, 2.46, 1.70,)
    HOLDS = (1.00, 1.00, 1.00, 1.00,)
    TAIL = 0.00

    def construct(self):
        e = self.eyebrow_in("01 · the problem")

        # ---- setup ----------------------------------------------------
        h = self.heading("You give an AI agent your card.", run_time=1.0)
        agent = labelled_box("AI agent", "shops for you", stroke=WARN)
        shop = labelled_box("Any shop", "on the internet")
        track = Line(LEFT * 1.1, RIGHT * 1.1, stroke_color=FAINT, stroke_width=2)
        scene = row(agent, track, shop, buff=0.45)
        tag = chip("HOLDS YOUR CARD", BAD)
        group = stack(scene, tag, buff=0.5, align=ORIGIN)
        place(group)

        self.play(FadeIn(agent, shift=RIGHT * 0.3), FadeIn(shop, shift=LEFT * 0.3),
                  run_time=0.8)
        self.play(Create(track), run_time=0.4)
        # A card slides down the wire — the agent can reach any shop it likes.
        card_dot = Dot(color=BAD, radius=0.09).move_to(track.get_left())
        self.play(FadeIn(tag, shift=UP * 0.15), FadeIn(card_dot), run_time=0.5)
        self.play(card_dot.animate.move_to(track.get_right()), run_time=1.1)
        self.play(FadeOut(card_dot), run_time=0.25)
        self.beat(0.5)
        self.play(FadeOut(group), FadeOut(h), run_time=0.4)

        # ---- three ways it breaks -------------------------------------
        self.cue(2)
        h2 = self.heading("Written into its instructions, it breaks three ways.",
                          32, run_time=1.2)
        faults = stack(
            bullet("You can talk it out of it.",
                   "the limit is a sentence, and reading sentences is what it does"),
            bullet("It cannot remember.",
                   "every conversation starts fresh — it has no month"),
            bullet("It reports its own numbers.",
                   "the only witness is the suspect"),
            buff=0.48)
        place(faults, align="left")
        self.play(LaggedStart(*[FadeIn(f, shift=RIGHT * 0.3) for f in faults],
                              lag_ratio=0.55), run_time=2.6)
        self.beat(0.9)
        self.play(FadeOut(faults), FadeOut(h2), run_time=0.4)

        # ---- the concrete failure ------------------------------------
        self.cue(3)
        # Not "a ₹12,000 item bought in three parts" — a checkout session cannot
        # be paid in thirds, and under Arm B the agent cannot state an amount at
        # all. Three real ₹4,000 purchases against a ₹5,000/merchant/hour
        # aggregate is what the corpus actually runs, and it needs no lie.
        h3 = self.heading("Three ₹4,000 purchases. Not one breaks the cap.",
                          run_time=1.2)
        buys = row(*[panel(stack(body("₹4,000", 30, OK), mono("legal", 18, MUTED),
                                 buff=0.16, align=ORIGIN), stroke=OK)
                     for _ in range(3)], buff=0.55)
        total = counter(0, 44, BAD)
        punch = body("Nothing was keeping score.", 32, INK)
        punch.set_color_by_t2c({"keeping score": ACCENT})
        group = stack(buys, total, punch, buff=0.5, align=ORIGIN)
        place(group)

        # Each purchase lands and the running total climbs — the number the
        # agent never sees.
        running = ValueTracker(0)
        total.add_updater(lambda m: m.become(
            counter(int(running.get_value()), 44, BAD).move_to(total)))
        self.add(total)
        for b in buys:
            self.play(FadeIn(b, scale=0.88), run_time=0.35)
            self.play(running.animate.set_value(running.get_value() + 4000),
                      run_time=0.5)
        total.clear_updaters()
        self.beat(0.5)
        self.cue(4)
        self.play(FadeIn(punch, shift=UP * 0.2), run_time=0.8)
        self.beat(1.0)
        self.tail(0.6)
        self.play(FadeOut(VGroup(e, h3, group)), run_time=0.6)
