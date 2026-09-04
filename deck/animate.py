#!/usr/bin/env python3
"""Add slide transitions and entrance animations to the built deck.

    python deck/animate.py

PptxGenJS cannot express animations, so they are injected into the OOXML after
the fact. This rewrites SpendGate.pptx in place (via a temp copy), giving every
slide a fade transition and building its shapes in one at a time.

The build order matters: run this AFTER deck/build.js, because build.js writes
the file from scratch and would discard anything added here.
"""

from __future__ import annotations

import re
import shutil
import sys
import zipfile
from pathlib import Path

DECK = Path(__file__).resolve().parent
PPTX = DECK / "SpendGate.pptx"

P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"

#: A fade between slides. Kept slow enough to read as deliberate rather than a
#: glitch, and applied to every slide so the deck has one consistent rhythm.
TRANSITION = (
    '<mc:AlternateContent xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006">'
    '<mc:Choice xmlns:p14="http://schemas.microsoft.com/office/powerpoint/2010/main" Requires="p14">'
    '<p:transition spd="med" p14:dur="600"><p:fade/></p:transition>'
    "</mc:Choice>"
    "<mc:Fallback><p:transition spd="
    '"med"><p:fade/></p:transition></mc:Fallback>'
    "</mc:AlternateContent>"
)


def anim_block(shape_ids: list[int], index: int, delay_ms: int,
               dur_ms: int = 450) -> str:
    """One build step: a group of shapes fading up together.

    Batched deliberately. A card, its stripe, its icon circle and its icon are
    four shapes but one thing on screen — animating them separately reads as a
    stutter, not a build. Everything runs on auto timing rather than on click,
    because a presenter who has to click twenty times per slide stops using the
    animation.
    """
    base = 100 + index * 20
    targets = "".join(
        f'<p:set><p:cBhvr><p:cTn id="{base + 3 + j * 2}" dur="1" fill="hold">'
        f'<p:stCondLst><p:cond delay="0"/></p:stCondLst></p:cTn>'
        f'<p:tgtEl><p:spTgt spid="{sid}"/></p:tgtEl>'
        f"<p:attrNameLst><p:attrName>style.visibility</p:attrName></p:attrNameLst>"
        f'</p:cBhvr><p:to><p:strVal val="visible"/></p:to></p:set>'
        f'<p:animEffect transition="in" filter="fade">'
        f'<p:cBhvr><p:cTn id="{base + 4 + j * 2}" dur="{dur_ms}"/>'
        f'<p:tgtEl><p:spTgt spid="{sid}"/></p:tgtEl></p:cBhvr></p:animEffect>'
        for j, sid in enumerate(shape_ids)
    )
    first = shape_ids[0]
    return f"""<p:par><p:cTn id="{base}" fill="hold"><p:stCondLst><p:cond delay="{delay_ms}"/></p:stCondLst><p:childTnLst><p:par><p:cTn id="{base + 1}" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst><p:childTnLst><p:par><p:cTn id="{base + 2}" presetID="10" presetClass="entr" presetSubtype="0" fill="hold" grpId="0" nodeType="afterEffect"><p:stCondLst><p:cond delay="0"/></p:stCondLst><p:childTnLst>{targets}</p:childTnLst></p:cTn></p:par></p:childTnLst></p:cTn></p:par></p:childTnLst></p:cTn></p:par>"""


#: A slide builds in at most this many steps. More than six and the audience is
#: watching a slide assemble instead of listening to the person in front of it.
MAX_STEPS = 6


def batches(ids: list[int], max_steps: int = MAX_STEPS) -> list[list[int]]:
    """Split shapes into build steps of roughly equal size, in document order."""
    if len(ids) <= max_steps:
        return [[i] for i in ids]
    size = -(-len(ids) // max_steps)          # ceil
    return [ids[i:i + size] for i in range(0, len(ids), size)]


def timing(shape_ids: list[int], step_ms: int = 380) -> str:
    """A whole slide's build, as one auto-advancing sequence."""
    if not shape_ids:
        return ""
    groups = batches(shape_ids)
    blocks = "".join(
        anim_block(g, i, 0 if i == 0 else step_ms)
        for i, g in enumerate(groups)
    )
    return (
        "<p:timing><p:tnLst><p:par><p:cTn id=\"1\" dur=\"indefinite\" "
        'restart="never" nodeType="tmRoot"><p:childTnLst>'
        '<p:seq concurrent="1" nextAc="seek"><p:cTn id="2" dur="indefinite" '
        'nodeType="mainSeq"><p:childTnLst>'
        f"{blocks}"
        "</p:childTnLst></p:cTn>"
        '<p:prevCondLst><p:cond evt="onPrev" delay="0"><p:tgtEl><p:sldTgt/>'
        "</p:tgtEl></p:cond></p:prevCondLst>"
        '<p:nextCondLst><p:cond evt="onNext" delay="0"><p:tgtEl><p:sldTgt/>'
        "</p:tgtEl></p:cond></p:nextCondLst></p:seq>"
        "</p:childTnLst></p:cTn></p:par></p:tnLst></p:timing>"
    )


def shape_ids(xml: str) -> list[int]:
    """Every drawable shape on the slide, in document order.

    Background rectangles animate too — fading the card in before its text is
    what makes a build read as one motion rather than text appearing on nothing.
    """
    return [int(m) for m in re.findall(r'<p:cNvPr id="(\d+)"', xml)]


def process(src: Path) -> tuple[int, int]:
    tmp = src.with_suffix(".animated.pptx")
    slides = anims = 0
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(
        tmp, "w", zipfile.ZIP_DEFLATED
    ) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if re.fullmatch(r"ppt/slides/slide\d+\.xml", item.filename):
                xml = data.decode("utf-8")
                ids = shape_ids(xml)
                # Shape 1 is the slide's own group placeholder, never animated.
                ids = [i for i in ids if i > 1]
                block = TRANSITION + timing(ids)
                if "</p:sld>" in xml and "<p:timing>" not in xml:
                    xml = xml.replace("</p:sld>", block + "</p:sld>")
                    slides += 1
                    anims += len(batches(ids))
                data = xml.encode("utf-8")
            zout.writestr(item, data)
    shutil.move(str(tmp), str(src))
    return slides, anims


def main() -> int:
    if not PPTX.exists():
        print("SpendGate.pptx not found — run `node deck/build.js` first",
              file=sys.stderr)
        return 1
    slides, anims = process(PPTX)
    print(f"  {slides} slides: fade transition + {anims} build steps")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
