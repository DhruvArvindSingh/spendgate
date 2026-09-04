"""Shared visual language and layout system for the SpendGate explainer.

The first draft of this video had eleven collisions — headings sitting on top of
diagrams, captions overlapping each other, text running off the right edge. All
of them had one cause: content was placed at guessed absolute coordinates
(`move_to(UP * 2.9)`) rather than measured and stacked.

So nothing here uses an absolute y for body content. A scene sets a heading, and
`Stage.show()` centres and scales whatever it is given inside the region that is
left over. If content is too big it shrinks; it can never overlap the heading and
it can never leave the frame.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from manim import *

# ---------------------------------------------------------------- palette
BG      = "#0F1115"   # ground
INK     = "#E7E9EE"   # primary text
MUTED   = "#949BA9"   # secondary text
FAINT   = "#5A616F"   # rules, dividers
ACCENT  = "#93A3EE"   # SpendGate itself
OK      = "#5FBF8C"   # approved / safe
WARN    = "#D7A24B"   # escalated / unknown
BAD     = "#E2796F"   # refused / leaked
SURFACE = "#171A21"   # card fill
LINE    = "#2A2F3A"   # card stroke

SANS = "DejaVu Sans"
MONO = "DejaVu Sans Mono"

# --------------------------------------------------------------- geometry
FRAME_W, FRAME_H = 14.222, 8.0

#: Where the webcam sits. Nothing is ever drawn here.
FACECAM_W, FACECAM_H = 3.2, 2.4
FACECAM_CENTER = np.array([FRAME_W / 2 - FACECAM_W / 2 - 0.45,
                           -FRAME_H / 2 + FACECAM_H / 2 + 0.45, 0])
FACECAM_TOP = FACECAM_CENTER[1] + FACECAM_H / 2      # ≈ -0.85
FACECAM_LEFT = FACECAM_CENTER[0] - FACECAM_W / 2     # ≈  3.06

#: The band every scene works in: full width, stopping clear of the webcam.
#: 12.8 x 5.4 is a lot of room — the fix for a cramped slide is less content,
#: not a taller band.
SAFE_W = 12.8
SAFE_TOP = 3.6
#: Set FACECAM=1 to render for live narration with a camera in the corner.
#: The narrated cut has no camera, and reserving the corner for one costs the
#: whole lower half of the frame: content is centred in the band below the
#: heading, so a floor at -0.85 pins every scene into the top third and leaves
#: 60% of the picture empty. That was the "everything is tiny and floating at
#: the top" problem, and it was in the geometry, not in any one scene.
FACECAM = os.environ.get("FACECAM") == "1"

#: Content stops ABOVE the webcam, not 0.25 into it — the first version
#: subtracted here and the closing line of scene 1 clipped the camera.
SAFE_BOTTOM = (FACECAM_TOP + 0.3) if FACECAM else (-FRAME_H / 2 + 0.62)

EYEBROW_Y = SAFE_TOP - 0.05
HEAD_Y = SAFE_TOP - 0.62
#: Body content lives between here and SAFE_BOTTOM.
BODY_TOP = HEAD_Y - 0.55


# ------------------------------------------------------------- primitives
def title(text: str, size: int = 40) -> Text:
    return Text(text, font=SANS, weight=BOLD, color=INK, font_size=size)


def body(text: str, size: int = 28, color: str = INK) -> Text:
    return Text(text, font=SANS, color=color, font_size=size, line_spacing=0.9)


def mono(text: str, size: int = 24, color: str = MUTED) -> Text:
    return Text(text, font=MONO, color=color, font_size=size, line_spacing=0.9)


def eyebrow(text: str, size: int = 20, color: str = ACCENT) -> Text:
    return Text(text.upper(), font=MONO, color=color, font_size=size).set_opacity(0.9)


def head(text: str, size: int = 34) -> Text:
    """A scene heading. Always sits at HEAD_Y, always scaled to fit the width."""
    t = Text(text, font=SANS, color=INK, font_size=size)
    fit(t, SAFE_W)
    t.move_to(np.array([0, HEAD_Y, 0]))
    return t


# ---------------------------------------------------------------- layout
def fit(mob: Mobject, max_w: float = SAFE_W, max_h: float | None = None) -> Mobject:
    """Shrink (never grow) a mobject until it fits. In place, returns it."""
    factor = 1.0
    if mob.width > max_w:
        factor = min(factor, max_w / mob.width)
    if max_h is not None and mob.height * factor > max_h:
        factor = min(factor, max_h / mob.height)
    if factor < 1.0:
        mob.scale(factor)
    return mob


#: How much of the body region content should try to occupy, and the most a
#: slide may be scaled up. Without the cap, a two-word slide becomes a poster.
FILL = 0.94
MAX_GROW = 1.6 if FACECAM else 2.1


def place(mob: Mobject, *, top: float = BODY_TOP, bottom: float = SAFE_BOTTOM,
          width: float = SAFE_W, align: str = "center", grow: bool = True) -> Mobject:
    """Fit a mobject into the body region and centre it there.

    This is what makes collisions structurally impossible: the region is bounded
    by the heading above and the webcam below, and content larger than it is
    scaled down rather than allowed to spill.

    `grow` also scales sparse slides UP, so a three-line slide fills the frame
    instead of floating in the top third with dead space beneath it.
    """
    height = top - bottom
    fit(mob, width, height)
    if grow:
        factor = min(width * FILL / mob.width, height * FILL / mob.height, MAX_GROW)
        if factor > 1.0:
            mob.scale(factor)
    mob.move_to(np.array([0, (top + bottom) / 2, 0]))
    if align == "left":
        mob.to_edge(LEFT, buff=(FRAME_W - SAFE_W) / 2)
    return mob


def stack(*items: Mobject, buff: float = 0.34, align=LEFT) -> VGroup:
    return VGroup(*items).arrange(DOWN, aligned_edge=align, buff=buff)


def row(*items: Mobject, buff: float = 0.5) -> VGroup:
    return VGroup(*items).arrange(RIGHT, buff=buff)


# ------------------------------------------------------------- components
def card(width: float, height: float, stroke: str = LINE, fill: str = SURFACE,
         radius: float = 0.12) -> RoundedRectangle:
    return RoundedRectangle(width=width, height=height, corner_radius=radius,
                            stroke_color=stroke, stroke_width=1.6,
                            fill_color=fill, fill_opacity=1.0)


def panel(content: Mobject, stroke: str = LINE, pad_x: float = 0.5,
          pad_y: float = 0.38, fill: str = SURFACE) -> VGroup:
    """A card sized to its content, rather than content jammed into a card.

    The first draft did the opposite and the injected-listing text ran off both
    edges of its box.
    """
    box = card(content.width + 2 * pad_x, content.height + 2 * pad_y,
               stroke=stroke, fill=fill)
    return VGroup(box, content.move_to(box.get_center()))


def labelled_box(label: str, sub: str = "", stroke: str = LINE,
                 label_color: str = INK, min_w: float = 2.6) -> VGroup:
    """A named box that sizes itself around its own text."""
    name = body(label, 26, label_color)
    inner = name if not sub else stack(name, mono(sub, 17, MUTED),
                                       buff=0.14, align=ORIGIN)
    group = panel(inner, stroke=stroke, pad_x=0.45, pad_y=0.3)
    if group[0].width < min_w:
        extra = (min_w - group[0].width) / 2
        group[0].stretch_to_fit_width(min_w)
        group[1].move_to(group[0].get_center())
    return group


def chip(text: str, color: str) -> VGroup:
    label = mono(text, 19, color)
    pill = RoundedRectangle(width=label.width + 0.42, height=0.46, corner_radius=0.1,
                            stroke_color=color, stroke_width=1.4,
                            fill_color=color, fill_opacity=0.12)
    return VGroup(pill, label.move_to(pill.get_center()))


def bullet(headline: str, sub: str = "", dot_color: str = BAD,
           head_size: int = 27, sub_size: int = 19) -> VGroup:
    """One list item: a dot, a headline, and an optional caption beneath it."""
    dot = Dot(radius=0.065, color=dot_color)
    text = body(headline, head_size, INK)
    if sub:
        text = stack(text, mono(sub, sub_size, MUTED), buff=0.11)
    dot.move_to(text.get_corner(UL) + LEFT * 0.32 + DOWN * 0.19)
    return VGroup(dot, text)


def tick(headline: str, sub: str = "") -> VGroup:
    mark = Text("✓", font=SANS, color=OK, font_size=30)
    text = body(headline, 27, INK)
    if sub:
        text = stack(text, mono(sub, 19, MUTED), buff=0.11)
    mark.move_to(text.get_corner(UL) + LEFT * 0.42 + DOWN * 0.2)
    return VGroup(mark, text)


def table_row(left: str, mid: str, right: str, right_color: str = MUTED,
              width: float = 9.2, height: float = 0.86,
              stroke: str = LINE) -> VGroup:
    """A row with three columns that cannot overlap.

    Each cell is fitted into its own allocated column rather than positioned at
    a guessed offset — the first draft measured the right column from the right
    edge and the left column from the left, and they met in the middle.
    """
    box = card(width, height, stroke=stroke)
    pad = 0.4
    inner = width - 2 * pad
    gap = 0.3
    inner -= 2 * gap
    w_left, w_mid, w_right = inner * 0.54, inner * 0.28, inner * 0.18

    l = fit(body(left, 24, INK), w_left, height * 0.6)
    m = fit(mono(mid, 18, MUTED), w_mid, height * 0.55)
    r = fit(mono(right, 19, right_color), w_right, height * 0.55)

    x0 = box.get_left()[0] + pad
    l.move_to(np.array([x0 + w_left / 2, box.get_center()[1], 0]), aligned_edge=ORIGIN)
    l.align_to(np.array([x0, 0, 0]), LEFT)
    m.move_to(np.array([x0 + w_left + gap + w_mid / 2, box.get_center()[1], 0]))
    r.move_to(np.array([x0 + w_left + w_mid + 2 * gap + w_right / 2,
                        box.get_center()[1], 0]))
    return VGroup(box, l, m, r)


def counter(value: int, size: int = 46, color: str = INK) -> VGroup:
    """A rupee figure that can be animated between values."""
    t = Text(f"₹{value:,}", font=MONO, weight=BOLD, color=color, font_size=size)
    t.figure = value
    return t


def cell(text: str, color: str, w: float = 1.55, h: float = 0.5,
         fill_opacity: float = 0.14) -> VGroup:
    """One square in a results grid."""
    box = RoundedRectangle(width=w, height=h, corner_radius=0.06,
                           stroke_color=color, stroke_width=1.2,
                           fill_color=color, fill_opacity=fill_opacity)
    return VGroup(box, mono(text, 15, color).move_to(box.get_center()))


def facecam_guide() -> VGroup:
    box = DashedVMobject(Rectangle(width=FACECAM_W, height=FACECAM_H,
                                   stroke_color=BAD, stroke_width=2),
                         num_dashes=40).move_to(FACECAM_CENTER)
    tag = mono("FACE CAM", 18, BAD).move_to(FACECAM_CENTER)
    return VGroup(box, tag).set_opacity(0.55)


# ------------------------------------------------------- narration timing
#: Where narrate.py wrote the voice track, and the silence mux.py puts either
#: side of it. These three numbers have to agree with mux.py or the film drifts.
AUDIO = Path(__file__).resolve().parent / "audio" / "manifest.json"
LEAD_IN = 0.35
LEAD_OUT = 0.70

#: fit_pace.py measures a scene's natural length, which cue holds would distort.
CUES_ON = os.environ.get("SPENDGATE_NO_CUES") != "1"

#: With this set to a directory, every scene writes down what each of its cues
#: cost it, and fit_pace.py solves SPEED against those numbers rather than
#: probing for it with repeated renders.
TRACE_DIR = Path(os.environ["SPENDGATE_CUE_TRACE"]) if os.environ.get(
    "SPENDGATE_CUE_TRACE") else None


def narration(key: str | None) -> tuple[list[float], float] | None:
    """When each line of a scene's narration starts, and when the scene ends.

    Returns None when the voice has not been recorded, so a scene still renders
    (unsynced) on a clean checkout.
    """
    if key is None or not AUDIO.exists():
        return None
    rec = json.loads(AUDIO.read_text()).get(key)
    if not rec:
        return None
    return ([LEAD_IN + c["start"] for c in rec["chunks"]],
            LEAD_IN + rec["spoken_s"] + LEAD_OUT)


# ------------------------------------------------------------------ scene
class Slide(Scene):
    """Dark ground, a section eyebrow, and a body region that cannot collide."""

    #: Which scene of NARRATION.md this is ("s6"), so its beats can be cued to
    #: the recording. None renders unsynced.
    VOICE: str | None = None

    def setup(self) -> None:
        self.camera.background_color = BG
        #: Animation seconds before SPEED is applied, and hold seconds, which
        #: SPEED does not touch. Kept apart so fit_pace.py can solve for SPEED
        #: instead of measuring two renders and interpolating between them.
        self._elapsed = 0.0
        self._seg = 0            # which stretch of narration we are under
        self._seg_anim = 0.0     # its animation seconds, before scaling
        self._seg_held = 0.0     # its beats, which scaling does not touch
        self._trace: list[dict] = []
        cues = narration(self.VOICE)
        self._cues, self._end = cues if cues else (None, None)
        super().setup()

    def eyebrow_in(self, text: str) -> Text:
        e = eyebrow(text)
        e.move_to(np.array([-SAFE_W / 2 + e.width / 2, EYEBROW_Y, 0]))
        self.play(FadeIn(e, shift=RIGHT * 0.2), run_time=0.5)
        return e

    def heading(self, text: str, size: int = 34, run_time: float = 1.1) -> Text:
        h = head(text, size)
        self.play(Write(h), run_time=run_time)
        return h

    #: Stretches every animation's run_time. This is the right dial for fitting
    #: a scene to narration: a Write that takes two seconds instead of one is
    #: still motion, whereas a longer wait is a hole. Tuned by tools/fit_pace.py.
    SPEED = 1.0

    #: One SPEED per stretch of narration, in order, so a beat with three
    #: seconds of script and a beat with fifteen are each filled with motion
    #: rather than averaged into a single factor that suits neither. Empty
    #: means fall back to SPEED. Tuned by tools/fit_pace.py.
    SEGMENTS: tuple[float, ...] = ()

    #: The same, for pauses. A stretch of narration can be shorter than the
    #: beats written under it, and then no animation speed can fit it — the
    #: pauses have to give. Tuned by tools/fit_pace.py.
    HOLDS: tuple[float, ...] = ()

    @property
    def speed(self) -> float:
        """The stretch factor for the beat currently playing."""
        if self.SEGMENTS and self._seg < len(self.SEGMENTS):
            return self.SEGMENTS[self._seg]
        return self.SPEED

    @property
    def hold(self) -> float:
        """How much of its written length a pause here actually gets."""
        if self.HOLDS and self._seg < len(self.HOLDS):
            return self.HOLDS[self._seg]
        return 1.0

    #: Multiplies pauses, but no single hold may exceed MAX_HOLD however the
    #: scene is paced — a uniform multiplier turns a 1.1s pause into a six
    #: second stare while leaving the short ones fine.
    #: 97% motion reads as relentless — a punchline needs a moment to land.
    #: With beats of 0.4–1.1s this gives roughly 1–2s of settle, capped.
    PACE = 2.5
    MAX_HOLD = 2.0

    #: A short closing pause, so a scene does not cut the instant it settles.
    TAIL = 0.0

    def play(self, *animations, **kwargs):
        """Every animation is stretched by SPEED, so fitting a scene to its
        narration adds movement rather than stillness.

        Holds are exempt, and that exemption is not cosmetic: Scene.wait() is
        implemented as play(Wait(run_time=duration)) with no run_time keyword,
        so the default-and-scale below used to replace every hold's duration
        with SPEED seconds. A three-second cue and a half-second beat both came
        out the same length, and tuning PACE or MAX_HOLD did nothing at all.
        """
        if len(animations) == 1 and isinstance(animations[0], Wait):
            # Waits are already the length they should be — beat() scales the
            # discretionary ones, and a cue's gap must not be scaled at all.
            self._elapsed += animations[0].run_time
            return super().play(*animations, **kwargs)
        raw = kwargs.get("run_time", 1.0)
        self._seg_anim += raw
        kwargs["run_time"] = raw * self.speed
        self._elapsed += kwargs["run_time"]
        return super().play(*animations, **kwargs)

    def beat(self, t: float = 0.8) -> None:
        """A pause for a point to land. The only kind fit_pace may compress."""
        base = min(t * self.PACE, self.MAX_HOLD)
        self._seg_held += base          # recorded unscaled, so it can be solved
        self.wait(base * self.hold)

    def cue(self, line: int) -> None:
        """Hold until line `line` of this scene's narration is spoken.

        Matching a scene's total length to its narration is not the same thing
        as matching it: stretching every animation by one factor put scene 6's
        "second, the rail" ten seconds before the rail appeared. So the voice
        drives the beats — each one waits for the sentence that describes it.

        A beat that overruns its cue cannot be rewound, which is what SPEED is
        for: fit_pace.py leaves enough slack that cues hold rather than lag.
        """
        if not self._cues or line > len(self._cues):
            return
        want = self._cues[line - 1]
        self._close_segment(line, want)
        if CUES_ON:
            gap = want - self._elapsed
            if gap > 0.05:
                self.wait(gap)

    def tail(self, closing: float = 0.0) -> None:
        """Hold so the scene ends on the last word.

        `closing` is the run_time of the fade-out still to come, before SPEED
        is applied — without it the scene runs past its own narration by
        however long it takes to clear the frame.
        """
        if self._end is not None:
            # The closing fade is animation too, so it scales with the beat.
            self._seg_anim += closing
            closing_speed = self.speed      # _close_segment moves past it
            self._close_segment("end", self._end)
            gap = self._end - self._elapsed - closing * closing_speed
            if gap > 0.05:
                self.wait(gap)
        elif self.TAIL > 0:
            self.wait(self.TAIL)

    def _close_segment(self, name, want: float) -> None:
        """Record what this stretch of narration cost, and start the next."""
        self._trace.append({"cue": name, "want": want, "at": self._elapsed,
                            "anim": self._seg_anim, "held": self._seg_held})
        self._seg_anim = self._seg_held = 0.0
        self._seg += 1

    def tear_down(self) -> None:
        if TRACE_DIR is not None and self._trace:
            TRACE_DIR.mkdir(parents=True, exist_ok=True)
            (TRACE_DIR / f"{type(self).__name__}.json").write_text(
                json.dumps(self._trace, indent=2))
        super().tear_down()
