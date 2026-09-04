#!/usr/bin/env python3
"""Tune each scene's SPEED so its motion fills its narration.

    python tools/fit_pace.py                 # every scene
    python tools/fit_pace.py S1Problem       # just the ones named

A cue can hold but it cannot rewind, so a beat that overruns the sentence it
illustrates pushes everything after it late and the whole scene runs past its
narration. One SPEED for a whole scene cannot fix that: scene 6 has seven
seconds of script over its first beat and thirteen over its third, and the
factor that fills one leaves the other stranded or late.

So each stretch of narration gets its own. Between two cues a scene spends
`anim` seconds of animation, which scaling stretches, and `held` seconds of
beats, which it does not. To fill exactly the window the script allows:

    anim_k * SPEED_k + held_k * HOLD_k = want_k - want_(k-1)

Animation is stretched first, because motion is what the viewer is watching;
the pauses only give when a window is shorter than the beats written under it,
which no animation speed can fix on its own. Two unknowns, solved in order,
no search. The scenes write those numbers down themselves during a trace
render, so this is two renders per scene rather than four.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
PY_BIN = HERE.parent / ".venv-manim" / "bin" / "python"

#: Fallback targets, from NARRATION.md at ~145 words/minute. Once the voice
#: track exists these are ignored: a scene is fitted to the recording that will
#: actually play under it, not to an estimate of how long it should have been.
SCENES = [
    ("s1_problem.py", "S1Problem", 30),
    ("s2_where.py", "S2Where", 26),
    ("s3_how.py", "S3How", 56),
    ("s4_edges.py", "S4Edges", 64),
    ("s5_results.py", "S5Results", 46),
    ("s6_proof.py", "S6Proof", 52),
    ("s7_limits.py", "S7Limits", 23),
]

#: Silence held before the first word and after the last, so a scene does not
#: start mid-breath or cut on the final consonant. Both are added to the video
#: target here and applied to the audio in mux.py — keep the two in step.
LEAD_IN = 0.35
LEAD_OUT = 0.70

#: A floor and a ceiling on each solved factor. Below the floor a beat is a
#: blur; above it, a Write becomes a crawl. A segment that wants to sit outside
#: this range is a scene with the wrong amount of content for its script, and
#: no timing dial will fix it — the report names those.
SPEED_MIN, SPEED_MAX = 0.55, 2.8

#: The same for pauses, which may be squeezed harder: a beat cut to a third is
#: a quick breath, where an animation at a third of its length is a flicker.
HOLD_MIN, HOLD_MAX = 0.15, 3.0

TRACE = HERE / "tools" / "trace"


def targets() -> dict[str, float]:
    """Scene length in seconds, measured from the narration audio if recorded."""
    mf = HERE / "audio" / "manifest.json"
    spoken = {}
    if mf.exists():
        for key, rec in json.loads(mf.read_text()).items():
            spoken[key] = rec["spoken_s"] + LEAD_IN + LEAD_OUT
    out = {}
    for i, (_f, cls, fallback) in enumerate(SCENES, 1):
        out[cls] = spoken.get(f"s{i}", float(fallback))
    if spoken:
        print(f"  targets from audio/manifest.json "
              f"({len(spoken)}/{len(SCENES)} scenes recorded)")
    else:
        print("  no narration recorded yet — using the word-count estimate")
    return out


def current_speed(path: Path) -> float:
    m = re.search(r"^    SPEED = ([\d.]+)", path.read_text(), re.M)
    return float(m.group(1)) if m else 1.0


def set_speed(path: Path, cls: str, speed: float) -> None:
    text = path.read_text()
    if re.search(r"^    SPEED = [\d.]+", text, re.M):
        text = re.sub(r"^    SPEED = [\d.]+", f"    SPEED = {speed:.2f}", text, flags=re.M)
    else:
        text = text.replace(f"class {cls}(Slide):\n",
                            f"class {cls}(Slide):\n    SPEED = {speed:.2f}\n", 1)
    path.write_text(text)


def set_tuple(path: Path, name: str, values: list[float], after: str) -> None:
    line = f"    {name} = (" + ", ".join(f"{x:.2f}" for x in values) + ",)"
    text = path.read_text()
    if re.search(rf"^    {name} = \(.*\)$", text, re.M):
        text = re.sub(rf"^    {name} = \(.*\)$", line, text, flags=re.M)
    else:
        text = re.sub(rf"^({after})$", rf"\1\n{line}", text, count=1, flags=re.M)
    path.write_text(text)


def set_tail(path: Path, cls: str, tail: float) -> None:
    text = path.read_text()
    if re.search(r"^    TAIL = [\d.]+", text, re.M):
        text = re.sub(r"^    TAIL = [\d.]+", f"    TAIL = {tail:.2f}", text, flags=re.M)
    else:
        text = re.sub(r"(^    PACE = [\d.]+$)", rf"\1\n    TAIL = {tail:.2f}",
                      text, count=1, flags=re.M)
    path.write_text(text)



def render(file: str, cls: str, cues: bool = True) -> float:
    env = dict(os.environ)
    if not cues:
        env["SPENDGATE_NO_CUES"] = "1"
        env["SPENDGATE_CUE_TRACE"] = str(TRACE)
    subprocess.run([str(PY_BIN), "-m", "manim", "-ql", "--disable_caching", file, cls],
                   cwd=HERE, capture_output=True, timeout=1800, env=env)
    vids = list((HERE / "media" / "videos").rglob(f"{cls}.mp4"))
    if not vids:
        return 0.0
    newest = max(vids, key=lambda p: p.stat().st_mtime)
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", str(newest)],
                         capture_output=True, text=True)
    return float(out.stdout.strip() or 0)


def main(only: set[str] | None = None) -> int:
    # Re-fitting a scene whose narration did not change re-derives the same
    # numbers at the cost of two renders, so a one-line script fix does not
    # have to pay for all seven.
    path_out = HERE / "tools" / "pacing.json"
    report = json.loads(path_out.read_text()) if path_out.exists() else {}
    want = targets()
    for file, cls, _fallback in SCENES:
        if only and cls not in only:
            continue
        target = want[cls]
        path = HERE / file
        set_tail(path, cls, 0.0)
        natural = render(file, cls, cues=False)
        if natural == 0:
            print(f"  {cls}: render failed")
            return 1

        trace = json.loads((TRACE / f"{cls}.json").read_text())
        speeds, holds, stuck, prev = [], [], [], 0.0
        for seg in trace:
            window, prev = seg["want"] - prev, seg["want"]
            anim, held = seg["anim"], seg["held"]
            # Stretch the motion as far as it is allowed to go, then let the
            # pauses take up whatever is left over, in either direction.
            sa = (min(max((window - held) / anim, SPEED_MIN), SPEED_MAX)
                  if anim > 0.05 else 1.0)
            sh = ((window - anim * sa) / held if held > 0.05 else 1.0)
            sh = min(max(sh, HOLD_MIN), HOLD_MAX)
            speeds.append(sa)
            holds.append(sh)
            short = window - (anim * sa + held * sh)
            if abs(short) > 0.4:
                stuck.append(f"{seg['cue']}{short:+.0f}s")
        set_speed(path, cls, sum(speeds) / len(speeds))
        set_tuple(path, "SEGMENTS", speeds, r"    SPEED = [\d.]+")
        set_tuple(path, "HOLDS", holds, r"    SEGMENTS = \(.*\)")

        final = render(file, cls)
        drift = final - target
        report[cls] = {"target": round(target, 1), "got": round(final, 1),
                       "segments": [round(x, 2) for x in speeds],
                       "holds": [round(x, 2) for x in holds],
                       "unfittable": stuck}
        flag = "" if abs(drift) < 0.35 else f"   <-- {drift:+.1f}s"
        note = f"  won't fit: {' '.join(stuck)}" if stuck else ""
        print(f"  {cls:12s} target {target:5.1f}s  got {final:5.1f}s  "
              f"{len(speeds)} beats, motion {min(speeds):.2f}–{max(speeds):.2f}"
              f"{note}{flag}")

    path_out.write_text(json.dumps(report, indent=2))
    total = sum(r["got"] for r in report.values())
    print(f"\n  TOTAL {total:.0f}s = {int(total // 60)}:{int(total % 60):02d}")
    return 0


if __name__ == "__main__":
    sys.exit(main(set(sys.argv[1:]) or None))
