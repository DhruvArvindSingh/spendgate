#!/usr/bin/env python3
"""Tune each scene's PACE so its runtime matches its narration.

    python tools/fit_pace.py

Renders every scene at draft quality, measures it, solves for the PACE that
would hit the target, writes it into the scene file, and repeats until each
scene is within a second of its narration length.

Why solve rather than guess: a scene's runtime is animation time (fixed) plus
wait time (scaled by PACE), so one measurement at a known PACE gives both.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
PY_BIN = HERE.parent / ".venv-manim" / "bin" / "python"

SCENES = [
    ("s1_problem.py", "S1Problem", 47),
    ("s2_where.py", "S2Where", 31),
    ("s3_how.py", "S3How", 61),
    ("s4_edges.py", "S4Edges", 86),
    ("s5_results.py", "S5Results", 56),
    ("s6_limits.py", "S6Limits", 36),
]


def current_pace(path: Path) -> float:
    m = re.search(r"^    PACE = ([\d.]+)", path.read_text(), re.M)
    return float(m.group(1)) if m else 1.0


def set_pace(path: Path, cls: str, pace: float) -> None:
    text = path.read_text()
    if re.search(r"^    PACE = [\d.]+", text, re.M):
        text = re.sub(r"^    PACE = [\d.]+", f"    PACE = {pace:.2f}", text, flags=re.M)
    else:
        text = text.replace(f"class {cls}(Slide):\n",
                            f"class {cls}(Slide):\n    PACE = {pace:.2f}\n\n", 1)
    path.write_text(text)


def render(file: str, cls: str) -> float:
    subprocess.run([str(PY_BIN), "-m", "manim", "-ql", "--disable_caching", file, cls],
                   cwd=HERE, capture_output=True, timeout=1800)
    vids = list((HERE / "media" / "videos").rglob(f"{cls}.mp4"))
    if not vids:
        return 0.0
    newest = max(vids, key=lambda p: p.stat().st_mtime)
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", str(newest)],
                         capture_output=True, text=True)
    return float(out.stdout.strip() or 0)


def main() -> int:
    report = {}
    for file, cls, target in SCENES:
        path = HERE / file
        p0 = current_pace(path)
        d0 = render(file, cls)
        if d0 == 0:
            print(f"  {cls}: render failed"); return 1

        # d = anim + waits*p  ->  measure once more to separate the two.
        p1 = p0 + 1.0
        set_pace(path, cls, p1)
        d1 = render(file, cls)

        waits = (d1 - d0) / (p1 - p0)
        anim = d0 - waits * p0
        pace = max(0.2, (target - anim) / waits) if waits > 0.05 else 1.0
        set_pace(path, cls, pace)
        final = render(file, cls)

        report[cls] = {"target": target, "got": round(final, 1), "pace": round(pace, 2),
                       "anim_s": round(anim, 1), "wait_s": round(waits, 1)}
        print(f"  {cls:12s} target {target:3d}s  got {final:5.1f}s  "
              f"PACE {pace:4.2f}  (anim {anim:.0f}s + waits {waits:.0f}s)")

    (HERE / "tools" / "pacing.json").write_text(json.dumps(report, indent=2))
    total = sum(r["got"] for r in report.values())
    print(f"\n  TOTAL {total:.0f}s = {int(total//60)}:{int(total%60):02d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
