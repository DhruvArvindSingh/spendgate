"""Shared visual language for the SpendGate explainer.

Two constraints shape everything here:

  1. A webcam sits in the bottom-right corner, so no content may enter
     FACECAM. `safe()` and `stage()` keep composition out of it.
  2. The palette is the dark theme from the project's own design doc, so the
     video and the written PRD look like one artifact rather than two.
"""

from __future__ import annotations

from manim import *

# ---------------------------------------------------------------- palette
BG       = "#0F1115"   # ground
INK      = "#E7E9EE"   # primary text
MUTED    = "#949BA9"   # secondary text
FAINT    = "#5A616F"   # rules, dividers
ACCENT   = "#93A3EE"   # SpendGate itself
OK       = "#5FBF8C"   # approved / safe
WARN     = "#D7A24B"   # escalated / unknown
BAD      = "#E2796F"   # refused / leaked
SURFACE  = "#171A21"   # card fill
LINE     = "#2A2F3A"   # card stroke

SANS = "DejaVu Sans"
MONO = "DejaVu Sans Mono"

# ------------------------------------------------------------ geometry
# Manim's 16:9 frame is 14.22 x 8, centred on the origin.
FRAME_W, FRAME_H = 14.222, 8.0

#: Where the webcam goes. Nothing may be drawn here.
FACECAM_W, FACECAM_H = 3.6, 2.7
FACECAM_CENTER = np.array([FRAME_W / 2 - FACECAM_W / 2 - 0.45,
                           -FRAME_H / 2 + FACECAM_H / 2 + 0.45, 0])

#: Usable area once margins and the webcam are excluded.
STAGE_LEFT, STAGE_RIGHT = -6.5, 6.5
STAGE_TOP, STAGE_BOTTOM = 3.3, -3.3
#: Content below this y must also stay left of this x, or it hits the webcam.
CLEAR_Y = -1.0
CLEAR_X = 2.4


def title(text: str, size: int = 40) -> Text:
    return Text(text, font=SANS, weight=BOLD, color=INK, font_size=size)


def body(text: str, size: int = 28, color: str = INK) -> Text:
    return Text(text, font=SANS, color=color, font_size=size)


def mono(text: str, size: int = 24, color: str = MUTED) -> Text:
    return Text(text, font=MONO, color=color, font_size=size)


def eyebrow(text: str, size: int = 20, color: str = ACCENT) -> Text:
    """Small uppercase label. Signals which section we are in."""
    return Text(text.upper(), font=MONO, color=color, font_size=size).set_opacity(0.9)


def card(width: float, height: float, stroke: str = LINE, fill: str = SURFACE,
         radius: float = 0.12) -> RoundedRectangle:
    return RoundedRectangle(width=width, height=height, corner_radius=radius,
                            stroke_color=stroke, stroke_width=1.6,
                            fill_color=fill, fill_opacity=1.0)


def labelled_box(label: str, sub: str = "", width: float = 3.0, height: float = 1.2,
                 stroke: str = LINE, label_color: str = INK) -> VGroup:
    """A box with a name and an optional small caption underneath it."""
    box = card(width, height, stroke=stroke)
    name = body(label, 26, label_color).move_to(box.get_center())
    if sub:
        name.shift(UP * 0.18)
        caption = mono(sub, 17, MUTED).next_to(name, DOWN, buff=0.12)
        return VGroup(box, name, caption)
    return VGroup(box, name)


def chip(text: str, color: str) -> VGroup:
    """A small status pill — APPROVED / REFUSED / ASK OWNER."""
    label = mono(text, 19, color)
    pill = RoundedRectangle(width=label.width + 0.42, height=0.46,
                            corner_radius=0.1, stroke_color=color,
                            stroke_width=1.4, fill_color=color, fill_opacity=0.12)
    return VGroup(pill, label.move_to(pill.get_center()))


def rule_line(width: float = 12.0) -> Line:
    return Line(LEFT * width / 2, RIGHT * width / 2, stroke_color=FAINT,
                stroke_width=1).set_opacity(0.5)


def facecam_guide() -> VGroup:
    """Visible only in the layout check — proves nothing collides with the cam."""
    box = DashedVMobject(Rectangle(width=FACECAM_W, height=FACECAM_H,
                                   stroke_color=BAD, stroke_width=2),
                         num_dashes=40).move_to(FACECAM_CENTER)
    tag = mono("FACE CAM", 18, BAD).move_to(FACECAM_CENTER)
    return VGroup(box, tag).set_opacity(0.55)


class Slide(Scene):
    """Base scene: dark ground, a section eyebrow, and the safe-area contract."""

    section = ""

    #: Multiplies every beat() so a scene can be stretched to fit its narration
    #: without touching the individual pauses. Tuned by tools/fit_pace.py.
    PACE = 1.0

    def setup(self) -> None:
        self.camera.background_color = BG
        super().setup()

    def eyebrow_in(self, text: str) -> Text:
        e = eyebrow(text).to_corner(UL, buff=0.55)
        self.play(FadeIn(e, shift=RIGHT * 0.2), run_time=0.5)
        return e

    def beat(self, t: float = 0.8) -> None:
        """A pause sized for narration, not for reading speed."""
        self.wait(t * self.PACE)
