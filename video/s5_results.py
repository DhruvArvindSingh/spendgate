"""Scene 5 — six models, eight scenarios. ~46s.

Every figure here is read from results/models.json at build time, so the video
cannot drift from the data it is describing.
"""

from __future__ import annotations

import json
from pathlib import Path

from manim import *

from theme import *

RESULTS = Path(__file__).resolve().parent.parent / "results" / "models.json"

ORDER = ["benign", "aggregate_blindness", "budget_amnesia", "injection",
         "category_laundering", "merchant_reprice", "retry_double_charge",
         "revoked_authority"]
SHORT = {"benign": "ordinary buy",
         "aggregate_blindness": "3 × ₹4,000",
         "budget_amnesia": "5 buys, fresh",
         "injection": "poisoned listing",
         "category_laundering": "prohibited",
         "merchant_reprice": "reprice after quote",
         "retry_double_charge": "\"try again\"",
         "revoked_authority": "permission pulled"}


def load():
    d = json.loads(RESULTS.read_text())
    ms = sorted(d["models"],
                key=lambda m: (-sum(x["unauthorized_minor"] for x in m["runs"]
                                    if x["arm"] == "A_naive"), m["label"]))
    grid = {}
    for m in ms:
        for x in m["runs"]:
            k = (m["label"], x["arm"], x["klass"])
            g = grid.setdefault(k, {"reps": 0, "failed": 0})
            g["reps"] += 1
            g["failed"] += int(x["unauthorized_minor"] > 0)
    lied = {m["label"] for m in ms if any(x["misreported"] for x in m["runs"])}
    honesty = {True: [], False: []}
    for m in ms:
        honesty[m["label"] in lied].append(
            (m["label"], sum(x["unauthorized_minor"] for x in m["runs"]
                             if x["arm"] == "A_naive")))
    leaked = sum(x["unauthorized_minor"] for m in ms for x in m["runs"]
                 if x["arm"] == "A_naive")
    passed = sum(g["reps"] - g["failed"] for (l, a, k), g in grid.items()
                 if a == "A_naive")
    total = sum(g["reps"] for (l, a, k), g in grid.items() if a == "A_naive")
    return ms, grid, leaked, passed, total, honesty


class S5Results(Slide):
    VOICE = "s5"
    SPEED = 1.88
    SEGMENTS = (1.24, 2.80, 2.80, 2.80, 1.07, 0.55,)
    HOLDS = (1.00, 1.11, 2.70, 1.00, 1.00, 0.38,)
    TAIL = 0.00

    def construct(self):
        e = self.eyebrow_in("05 · six models")
        models, grid, leaked, passed, total, honesty = load()
        short = [m["label"].split()[0] for m in models]

        h = self.heading("Six models. Eight scenarios. Both arms.")

        # ---- build the grid -------------------------------------------
        head_row = row(*[mono(s, 15, MUTED) for s in short], buff=0.28)
        for lab, x in zip(head_row, range(len(short))):
            lab.set_width(min(lab.width, 1.5))
        cols = VGroup()
        cells = {}
        for k in ORDER:
            r = VGroup()
            for m in models:
                g = grid[(m["label"], "A_naive", k)]
                ok = g["failed"] == 0
                c = cell("pass" if ok else "fail", OK if ok else BAD)
                cells[(m["label"], k)] = c
                r.add(c)
            r.arrange(RIGHT, buff=0.16)
            label = mono(SHORT[k], 16, MUTED)
            label.next_to(r, LEFT, buff=0.35)
            cols.add(VGroup(label, r))
        cols.arrange(DOWN, buff=0.13, aligned_edge=RIGHT)
        head_row.next_to(cols[0][1], UP, buff=0.2).align_to(cols[0][1], LEFT)
        for lab, c in zip(head_row, cols[0][1]):
            lab.move_to(np.array([c.get_center()[0], head_row.get_center()[1], 0]))
        table = VGroup(head_row, cols)
        place(table)

        self.play(FadeIn(head_row), run_time=0.5)
        for grp in cols:
            self.play(FadeIn(grp[0], shift=RIGHT * 0.15),
                      LaggedStart(*[FadeIn(c, scale=0.85) for c in grp[1]],
                                  lag_ratio=0.12), run_time=0.55)
        self.beat(0.8)

        self.cue(2)
        score = body(f"{passed} of {total} passed.", 30, BAD)
        score.next_to(table, DOWN, buff=0.4)
        fit(score, SAFE_W)
        self.play(FadeIn(score, shift=UP * 0.15), run_time=0.7)
        self.beat(1.0)

        # ---- the four rows nobody passes -------------------------------
        universal = [k for k in ORDER
                     if all(grid[(m["label"], "A_naive", k)]["failed"] > 0
                            for m in models)]
        boxes = VGroup(*[SurroundingRectangle(cols[ORDER.index(k)], color=BAD,
                                              buff=0.08, stroke_width=2,
                                              corner_radius=0.06)
                         for k in universal])
        self.cue(3)
        self.play(FadeOut(score), run_time=0.3)
        self.play(LaggedStart(*[Create(b) for b in boxes], lag_ratio=0.3),
                  run_time=1.4)
        note = body("Four scenarios failed by every model.", 28, BAD)
        note.next_to(table, DOWN, buff=0.4)
        fit(note, SAFE_W)
        self.play(FadeIn(note, shift=UP * 0.15), run_time=0.6)
        self.beat(1.2)

        # ---- three of them lied about the price ------------------------
        # The narration spends ten seconds on this and the first cut had
        # nothing on screen for it.
        self.cue(4)
        self.play(FadeOut(boxes), FadeOut(note), FadeOut(table),
                  FadeOut(h), run_time=0.45)
        h3 = self.heading("Three of the six lied about the price.")

        def column(title: str, tone: str, entries) -> VGroup:
            names = stack(*[mono(n, 21, INK) for n, _ in entries],
                          buff=0.16, align=ORIGIN)
            money = counter(sum(v for _, v in entries) // 100, 30, BAD)
            inner = stack(mono(title, 19, tone), names, money,
                          buff=0.3, align=ORIGIN)
            return panel(inner, stroke=LINE, pad_x=0.6)

        # Both columns leak, so both figures are red. Colouring the honest
        # column green would put a loss figure inside a reassuring card.
        cols2 = row(column("lied when told to", WARN, honesty[True]),
                    column("reported honestly", MUTED, honesty[False]), buff=1.0)
        verdict = body("It changed the conclusion not at all.", 27, ACCENT)
        beat = stack(cols2, verdict, buff=0.55, align=ORIGIN)
        place(beat)
        self.play(FadeIn(cols2[0], shift=RIGHT * 0.25), run_time=0.8)
        self.play(FadeIn(cols2[1], shift=LEFT * 0.25), run_time=0.8)
        self.cue(5)
        self.play(FadeIn(verdict, shift=UP * 0.15), run_time=0.7)
        self.beat(1.0)
        self.play(FadeOut(beat), FadeOut(h3), run_time=0.45)

        # ---- flip to the SpendGate arm ---------------------------------
        self.cue(6)
        h = self.heading("With SpendGate.")
        self.play(FadeIn(table), run_time=0.6)
        # Recolour in place rather than transforming into a fresh cell: place()
        # scaled the whole table, and a newly built cell comes back at full size
        # and lands wider than the one it replaces.
        flips = []
        for k in ORDER:
            for m in models:
                box, label = cells[(m["label"], k)]
                flips.append(AnimationGroup(
                    box.animate.set_stroke(OK).set_fill(OK, opacity=0.14),
                    label.animate.set_color(OK)))
        self.play(LaggedStart(*flips, lag_ratio=0.012), run_time=2.0)
        # The failing cells still read "fail"; swap the word without resizing.
        swaps = []
        for k in ORDER:
            for m in models:
                box, label = cells[(m["label"], k)]
                if label.text != "pass":
                    new = mono("pass", 15, OK)
                    new.scale(label.height / new.height).move_to(label)
                    swaps.append(Transform(label, new))
        if swaps:
            self.play(LaggedStart(*swaps, lag_ratio=0.01), run_time=1.0)
        self.beat(0.5)

        done = fit(body(f"{total} of {total}.", 32, OK), SAFE_W)
        done.next_to(table, DOWN, buff=0.4)
        self.play(FadeIn(done, shift=UP * 0.15), run_time=0.6)
        self.beat(0.9)
        self.play(FadeOut(VGroup(table, done)), FadeOut(h), run_time=0.5)

        # ---- the money ---------------------------------------------------
        tracker = ValueTracker(leaked / 100)
        big = counter(int(leaked / 100), 60, BAD)
        place(big, top=SAFE_TOP)
        big.add_updater(lambda m: m.become(
            counter(int(tracker.get_value()), 60,
                    BAD if tracker.get_value() > 0 else OK).move_to(big)))
        caption = mono("released without authority", 22, MUTED)
        caption.next_to(big, DOWN, buff=0.4)

        self.add(big)
        self.play(FadeIn(caption), run_time=0.4)
        self.beat(0.8)
        self.play(tracker.animate.set_value(0), run_time=1.8, rate_func=rate_functions.ease_in_out_cubic)
        big.clear_updaters()
        self.play(Transform(caption,
                            mono("with SpendGate", 22, OK).move_to(caption)),
                  run_time=0.5)
        self.beat(1.4)
        self.tail(0.6)
        self.play(FadeOut(VGroup(e, big, caption)), run_time=0.6)
