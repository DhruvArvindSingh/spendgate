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
#: Content stops ABOVE the webcam, not 0.25 into it — the first version
#: subtracted here and the closing line of scene 1 clipped the camera.
SAFE_BOTTOM = FACECAM_TOP + 0.3                      # ≈ -0.55

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
MAX_GROW = 1.6


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


def facecam_guide() -> VGroup:
    box = DashedVMobject(Rectangle(width=FACECAM_W, height=FACECAM_H,
                                   stroke_color=BAD, stroke_width=2),
                         num_dashes=40).move_to(FACECAM_CENTER)
    tag = mono("FACE CAM", 18, BAD).move_to(FACECAM_CENTER)
    return VGroup(box, tag).set_opacity(0.55)


# ------------------------------------------------------------------ scene
class Slide(Scene):
    """Dark ground, a section eyebrow, and a body region that cannot collide."""

    #: Multiplies every beat() so a scene stretches to fit its narration without
    #: touching individual pauses. Tuned by tools/fit_pace.py.
    PACE = 1.0

    def setup(self) -> None:
        self.camera.background_color = BG
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

    def beat(self, t: float = 0.8) -> None:
        self.wait(t * self.PACE)
