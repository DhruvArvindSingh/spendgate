#!/usr/bin/env python3
"""Lay the narration under the rendered scenes and stitch the film.

    ../.venv-manim/bin/python video/mux.py            # 1080p60 renders
    ../.venv-manim/bin/python video/mux.py --quality 720p30

Each scene is muxed on its own before anything is joined, so a re-taken line
costs one scene's mux and not the whole film. The audio is delayed by LEAD_IN
and padded with silence to the video's exact length: the video is the clock,
because fit_pace.py already stretched it to fit these recordings.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCENES = ["S1Problem", "S2Where", "S3How", "S4Edges", "S5Results", "S6Proof",
          "S7Limits"]

# Must match tools/fit_pace.py, which added both to the render target.
LEAD_IN = 0.35
LEAD_OUT = 0.70


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", str(path)],
                         capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def find_render(cls: str, quality: str | None) -> Path:
    root = HERE / "media" / "videos"
    hits = [p for p in root.rglob(f"{cls}.mp4")
            if quality is None or p.parent.name == quality]
    if not hits:
        raise SystemExit(f"no render for {cls}"
                         + (f" at {quality}" if quality else "")
                         + " — run ./render.sh final")
    return max(hits, key=lambda p: p.stat().st_mtime)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quality", default="1080p60",
                    help="manim quality directory, or 'any'")
    ap.add_argument("--out", default=str(HERE / "out" / "spendgate_narrated.mp4"))
    args = ap.parse_args()
    quality = None if args.quality == "any" else args.quality

    manifest = json.loads((HERE / "audio" / "manifest.json").read_text())
    stage = HERE / "out" / "scenes"
    stage.mkdir(parents=True, exist_ok=True)

    parts, drift = [], []
    for i, cls in enumerate(SCENES, 1):
        vid = find_render(cls, quality)
        voice = HERE / "audio" / f"s{i}.wav"
        if not voice.exists():
            raise SystemExit(f"missing narration: {voice}")
        vlen, alen = duration(vid), duration(voice)
        need = alen + LEAD_IN + LEAD_OUT
        drift.append((cls, vlen, need))

        out = stage / f"s{i}_{cls}.mp4"
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(vid), "-i", str(voice),
            # delay the voice, pad with silence, then cut to the video's length
            "-filter_complex",
            f"[1:a]adelay={int(LEAD_IN * 1000)}|{int(LEAD_IN * 1000)},"
            f"apad,atrim=0:{vlen:.3f},"
            # loudnorm resamples to 192k internally, so the rate has to be set
            # after it or the encoder inherits that: the first cut shipped 96kHz
            # AAC, which some players will not touch.
            f"loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[a]",
            "-map", "0:v", "-map", "[a]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ac", "2",
            "-movflags", "+faststart", str(out),
        ], check=True)
        parts.append(out)
        fit = vlen - need
        flag = "" if abs(fit) < 1.0 else "   <-- CHECK"
        print(f"  s{i} {cls:10s} video {vlen:6.1f}s  voice {alen:6.1f}s  "
              f"slack {fit:+5.1f}s{flag}")

    listing = HERE / "out" / "concat_narrated.txt"
    listing.write_text("".join(f"file '{p}'\n" for p in parts))
    final = Path(args.out)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                    "-i", str(listing), "-c", "copy", "-movflags", "+faststart",
                    str(final)], check=True)

    total = duration(final)
    spoken = sum(v["spoken_s"] for v in manifest.values())
    print(f"\n  → {final}  {int(total // 60)}:{total % 60:04.1f}"
          f"  ({spoken:.0f}s of speech, {100 * spoken / total:.0f}% talking)")
    worst = max(drift, key=lambda d: abs(d[1] - d[2]))
    print(f"  worst fit: {worst[0]} off by {worst[1] - worst[2]:+.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
