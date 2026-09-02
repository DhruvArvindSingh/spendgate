"""A single still that proves nothing collides with the webcam.

    manim -sqm layout_check.py LayoutCheck

Render this first. If any element sits inside the dashed box, the face will
cover it in the final video.
"""

from manim import *

from theme import *


class LayoutCheck(Slide):
    def construct(self):
        e = eyebrow("03 · how it works").to_corner(UL, buff=0.55)
        head = body("The agent's entire vocabulary.", 36).move_to(UP * 2.9)
        req = VGroup(
            mono("request_payment(", 30, INK),
            mono("    mandate_id          = \"mnd_01J9F2K7\"", 26, ACCENT),
            mono("    checkout_session_id = \"cs_8fK2mNp\"", 26, ACCENT),
            mono("    agent_id            = \"agt_shopper_01\"", 26, ACCENT),
            mono(")", 30, INK),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.2).move_to(UP * 1.35 + LEFT * 1.4)
        punch = body("There is nowhere to put a lie.", 34, ACCENT).move_to(DOWN * 2.35 + LEFT * 2.2)

        safe = DashedVMobject(
            Rectangle(width=STAGE_RIGHT - STAGE_LEFT, height=STAGE_TOP - STAGE_BOTTOM,
                      stroke_color=OK, stroke_width=1.5), num_dashes=60).set_opacity(0.35)
        safe_tag = mono("safe area", 16, OK).next_to(safe, UP, buff=0.08).align_to(safe, LEFT)

        self.add(e, head, req, punch, safe, safe_tag, facecam_guide())
        self.wait(0.1)
