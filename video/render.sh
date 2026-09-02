#!/usr/bin/env bash
# Render the SpendGate explainer.
#
#   ./render.sh check     one still, with the webcam guide drawn — run this first
#   ./render.sh draft     all scenes at 480p, fast, for pacing
#   ./render.sh final     all scenes at 1080p60
#
# Scenes render separately on purpose: one bad take does not cost you the
# other five, and you can re-record narration section by section.
set -euo pipefail
cd "$(dirname "$0")"
PY=../.venv-manim/bin/python
SCENES=(s1_problem.py:S1Problem s2_where.py:S2Where s3_how.py:S3How
        s4_edges.py:S4Edges s5_results.py:S5Results s6_limits.py:S6Limits)

case "${1:-draft}" in
  check) "$PY" -m manim -sqm layout_check.py LayoutCheck; exit 0 ;;
  draft) FLAGS="-qm" ;;
  final) FLAGS="-qh --fps 60" ;;
  *) echo "usage: $0 {check|draft|final}"; exit 1 ;;
esac

for entry in "${SCENES[@]}"; do
  file="${entry%%:*}"; cls="${entry##*:}"
  echo "── $cls"
  "$PY" -m manim $FLAGS "$file" "$cls"
done

# Stitch, in order.
OUT=media/videos
mkdir -p out
: > out/concat.txt
for entry in "${SCENES[@]}"; do
  cls="${entry##*:}"
  f=$(find "$OUT" -name "${cls}.mp4" | sort | tail -1)
  [ -n "$f" ] && echo "file '$(realpath "$f")'" >> out/concat.txt
done
ffmpeg -y -f concat -safe 0 -i out/concat.txt -c copy out/spendgate.mp4 2>/dev/null
echo
echo "→ out/spendgate.mp4  ($(ffprobe -v error -show_entries format=duration \
     -of default=noprint_wrappers=1:nokey=1 out/spendgate.mp4 2>/dev/null | cut -d. -f1)s)"
