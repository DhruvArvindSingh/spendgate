# The explainer video

A five-minute Manim animation of how SpendGate works, built to be narrated live
with a webcam in the corner.

```bash
./render.sh check    # one still with the webcam box drawn — run this first
./render.sh draft    # all six scenes at 720p, fast, for checking pacing
./render.sh final    # 1080p60, then stitched to out/spendgate.mp4
```

## How it is put together

Six scenes, rendered as separate files and stitched at the end. That is
deliberate: a bad take on scene 4 costs you scene 4, not the whole video, and
you can re-record narration section by section.

| Scene | Covers | Length |
|---|---|---|
| `s1_problem` | Why the obvious design fails, ending on the split-purchase | 47s |
| `s2_where` | ACP, AP2, Razorpay — and the layer nobody builds | 31s |
| `s3_how` | The request shape, where the price comes from, the rule pipeline | 61s |
| `s4_edges` | Injection, splitting, the three-way outcome, the tamper bug | 86s |
| `s5_results` | Two-arm numbers, then the LLM finding | 56s |
| `s6_limits` | What it does not do, and the close | 36s |

[`NARRATION.md`](NARRATION.md) is the script, timed to those lengths at ~145
words per minute. Record the audio first and lay the video underneath — trying
to match a render while talking is miserable and it shows.

## The webcam

Your face sits bottom-right, about 490 × 365 in a 1920 × 1080 frame. Nothing is
ever drawn there. `theme.py` defines the box and `layout_check.py` renders a
still with it outlined, so you can prove it rather than hoping.

If you move the camera, change `FACECAM_*` in `theme.py` and re-run
`./render.sh check`.

## Pacing

Each scene has a `PACE` constant that multiplies every pause. `tools/fit_pace.py`
renders each scene, measures it, solves for the pace that matches the narration,
and writes it back — so the animation fits the words rather than the other way
round.

Rerun it after editing the script:

```bash
python tools/fit_pace.py
```

Results land in `tools/pacing.json`.

## Notes on the design

The palette is the dark theme from the project's own design document, so the
video and the written material read as one thing. Monospace carries machine
facts — rule IDs, code, amounts — and the sans face carries the argument. Every
number on screen comes from `results/full.json` or `results/llm.json`; nothing
is illustrative.
