"""Scene 6 — the anchor, and the live rail. ~50s.

Scene 4 admits the tamper bug. This scene closes it, and it closes it with the
real thing: the chain below is built by the project's own ledger at render
time, rewritten the way an attacker would rewrite it, and the verdicts are
whatever `verify_chain` and `verify_against_anchor` actually return. If the
fix regresses, this scene stops saying it works.

The Razorpay panel reads results/live_rail.json for the same reason.
"""

from __future__ import annotations

import dataclasses
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from manim import *

from theme import *

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
RAIL = ROOT / "results" / "live_rail.json"


def ledger_demo():
    """Run the real ledger: three entries, then a full rewrite that drops one.

    Returns (before, after, chain_verdict, anchor_verdict) — the hashes and the
    verdict strings are the library's, not a reconstruction of them.
    """
    from spendgate.ledger import GENESIS, InMemoryAnchor, InMemoryLedger

    led = InMemoryLedger(anchor=InMemoryAnchor())
    led.open_account("mnd_demo", 500000)
    at = datetime(2026, 9, 2, 10, 0, tzinfo=timezone.utc)
    led.reserve("mnd_demo", "auth_1", 120000, at, "mrc_kirana")
    led.commit("mnd_demo", "auth_1", at, ref="pay_TXG9Qo")
    led.reserve("mnd_demo", "auth_2", 45000, at, "mrc_kirana")
    before = list(led.entries("mnd_demo"))

    # The attack: not an edit, a rewrite. Drop the commit and renumber, so
    # every prev_hash is recomputed and nothing is left dangling.
    account = led._acct("mnd_demo")
    rebuilt, prev = [], GENESIS
    for i, e in enumerate([before[0], before[2]], 1):
        n = dataclasses.replace(e, seq=i, prev_hash=prev)
        rebuilt.append(n)
        prev = n.hash
    account.entries = rebuilt

    chain_ok, _ = led.verify_chain("mnd_demo")
    anchor_ok, why = led.verify_against_anchor("mnd_demo")
    return before, rebuilt, chain_ok, (anchor_ok, why), led.anchor.head("mnd_demo")


def entry_card(e, stroke: str = LINE) -> VGroup:
    kind = e.kind.value if hasattr(e.kind, "value") else str(e.kind)
    head_line = mono(f"{e.seq}  {kind.lower()}", 20, INK)
    amount = mono(f"₹{e.amount_minor // 100:,}", 22, ACCENT)
    digest = mono(e.hash.split(":")[-1][:10] + "…", 16, MUTED)
    inner = stack(head_line, amount, digest, buff=0.12, align=ORIGIN)
    return panel(inner, stroke=stroke, pad_x=0.36, pad_y=0.26)


def chain_of(entries, stroke: str = LINE) -> VGroup:
    """Cards left to right, with the links drawn after they are arranged."""
    cards = VGroup(*[entry_card(e, stroke) for e in entries]).arrange(RIGHT, buff=0.8)
    links = VGroup(*[
        Arrow(cards[i].get_right(), cards[i + 1].get_left(), buff=0.1,
              stroke_width=3, color=FAINT, max_tip_length_to_length_ratio=0.22)
        for i in range(len(cards) - 1)])
    return VGroup(cards, links)


class S6Proof(Slide):
    VOICE = "s6"
    SPEED = 1.90
    SEGMENTS = (0.65, 2.80, 0.65, 2.62, 2.80,)
    HOLDS = (1.00, 3.00, 1.00, 1.00, 2.87,)
    TAIL = 0.00

    def construct(self):
        e = self.eyebrow_in("06 · proof")
        before, after, chain_ok, (anchor_ok, why), head = ledger_demo()

        # ---- the anchor -----------------------------------------------
        # Everything this beat will ever show is laid out and scaled once, and
        # then revealed a piece at a time. Placing a growing group twice made
        # the chain jump and shrink the moment the verdicts appeared.
        h = self.heading("The bug from a minute ago, closed.")
        chain = chain_of(before)
        rewritten = chain_of(after, stroke=WARN).move_to(chain)
        slot = VGroup(chain, rewritten)
        caption = mono("each entry's fingerprint covers the one before it", 19, MUTED)

        # The anchor is the whole point of the beat, so it is an object on the
        # frame rather than a word in a caption: it takes the head, the ledger
        # is rewritten underneath it, and it visibly does not change.
        seq, digest = head
        anchor = panel(stack(mono("anchor  ·  outside the service", 19, ACCENT),
                             mono(f"head  {seq}/{digest.split(':')[-1][:10]}…", 21, INK),
                             buff=0.14, align=ORIGIN), stroke=ACCENT)
        verdicts = stack(
            chip(f"verify_chain  ->  {'clean' if chain_ok else 'broken'}", WARN),
            chip(f"against the anchor  ->  {'clean' if anchor_ok else 'caught'}", OK),
            buff=0.24, align=ORIGIN)
        # The anchor sits beside the chain, not under it: stacked, the link
        # between them runs diagonally through the caption.
        topline = row(slot, anchor, buff=0.9)
        beat_a = stack(topline, caption, verdicts, buff=0.5, align=ORIGIN)
        place(beat_a)
        rewritten.move_to(chain)

        def link_from(mob, color):
            return DashedLine(mob.get_right(), anchor.get_left(), buff=0.16,
                              color=color, stroke_width=2.5, dash_length=0.09)

        link = link_from(chain, FAINT)

        self.play(LaggedStart(*[FadeIn(c, shift=UP * 0.15) for c in chain[0]],
                              lag_ratio=0.4), run_time=1.6)
        self.play(*[GrowArrow(a) for a in chain[1]], run_time=0.8)
        self.play(FadeIn(caption), run_time=0.6)
        self.beat(0.9)

        self.cue(2)
        self.play(Create(link), run_time=0.7)
        self.play(FadeIn(anchor, shift=UP * 0.2), run_time=0.9)
        self.beat(0.8)

        # The rewrite: one entry fewer, every hash recomputed, same footprint.
        # The anchor does not move, because nothing in the service can move it.
        # Out, then in. Crossfading them in place superimposed two chains of
        # different lengths and the frame was unreadable for the whole fade.
        rewrite_caption = mono("a full rewrite recomputes every one of them",
                               19, WARN).move_to(caption)
        self.cue(3)
        self.play(FadeOut(chain, shift=UP * 0.25), run_time=0.5)
        self.play(FadeIn(rewritten, shift=DOWN * 0.25),
                  Transform(caption, rewrite_caption),
                  Transform(link, link_from(rewritten, BAD)), run_time=0.9)
        self.beat(0.9)

        self.play(FadeIn(verdicts[0], shift=UP * 0.15), run_time=0.7)
        self.beat(0.8)
        self.play(FadeIn(verdicts[1], shift=UP * 0.15),
                  anchor[0].animate.set_stroke(OK), run_time=0.8)
        detail = mono(why.split(": ", 1)[-1], 17, MUTED)
        detail.next_to(verdicts, DOWN, buff=0.3)
        self.play(FadeIn(detail), run_time=0.5)
        self.beat(1.2)
        self.play(FadeOut(beat_a), FadeOut(caption), FadeOut(link),
                  FadeOut(detail), FadeOut(h), run_time=0.6)

        # ---- the live rail --------------------------------------------
        rail = json.loads(RAIL.read_text())
        self.cue(4)
        h2 = self.heading("And it runs against the real rail.")
        rupees = rail["order_amount_minor"] // 100
        lines = stack(
            mono(f"order        {rail['order_id']}", 22, INK),
            mono(f"amount       ₹{rupees:,}   read back from Razorpay", 22, INK),
            mono(f"mode         {rail['mode']}", 22, MUTED),
            buff=0.26, align=LEFT)
        card_g = panel(lines, stroke=ACCENT)
        passed = chip(f"{rail['checks_passed']} / {rail['checks_total']} checks passed", OK)
        note = mono("the price came from Razorpay's API, never from the agent", 19, MUTED)
        beat_b = stack(card_g, passed, note, buff=0.4, align=ORIGIN)
        place(beat_b)
        self.play(FadeIn(card_g, shift=UP * 0.2), run_time=0.9)
        self.play(LaggedStart(*[FadeIn(l, shift=RIGHT * 0.2) for l in lines],
                              lag_ratio=0.4), run_time=1.2)
        self.play(FadeIn(passed, scale=1.08), FadeIn(note), run_time=0.7)
        self.beat(1.0)
        self.play(FadeOut(beat_b), FadeOut(h2), run_time=0.5)

        # ---- and what it does not prove -------------------------------
        self.cue(5)
        h3 = self.heading("What that does not prove.")
        caveat = stack(
            bullet("Capturing a payment needs a human to open the link.",
                   "so settlement is exercised against the fake rail in the "
                   "test suite, not this one", WARN),
            buff=0.4)
        place(caveat, align="left")
        self.play(FadeIn(caveat, shift=RIGHT * 0.3), run_time=1.0)
        self.beat(1.2)
        self.tail(0.7)
        self.play(FadeOut(caveat), FadeOut(h3), FadeOut(e), run_time=0.7)
