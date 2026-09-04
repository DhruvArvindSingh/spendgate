# The explainer video

A Manim animation of how SpendGate works, narrated end to end by a cloned
voice. Nothing here is recorded by hand: the script is `NARRATION.md`, the
voice is Chatterbox, the animation is timed to the recording rather than the
other way round, and Whisper checks that what was spoken is what was written.

```bash
./render.sh draft    # all seven scenes at 720p, fast, for checking pacing
./render.sh final    # 1080p60, then stitched to out/spendgate.mp4

VOICE=/path/to/voice/.venv/bin/python
$VOICE narrate.py --all        # speak the script      -> audio/sN.wav
$VOICE verify_audio.py         # check it against the script
../.venv-manim/bin/python tools/fit_pace.py    # fit the animation to the audio
../.venv-manim/bin/python mux.py               # lay it under and stitch
```

Run them in that order. `fit_pace.py` reads `audio/manifest.json`, so the voice
has to exist before the timing means anything, and `render.sh final` has to run
after `fit_pace.py` has written the new `SPEED` values.

## Layout, and why it is not hand-positioned

The first cut of this video had eleven collisions — headings sitting on diagrams,
captions stacked on each other, text running off the right edge. Every one had
the same cause: content placed at guessed absolute coordinates.

Nothing sets an absolute y any more. A scene builds a group; `place()` fits it
into the band bounded by the heading above and the webcam below, and centres it
there. Too-big content shrinks, sparse content grows to fill. Overlap is not
something to be careful about — it is unrepresentable.

`panel()` sizes a card to its content rather than the reverse, and `table_row()`
allocates real columns with gaps rather than measuring one cell from the left and
another from the right until they meet in the middle.

## How it is put together

Six scenes, rendered as separate files and stitched at the end. That is
deliberate: a bad take on scene 4 costs you scene 4, not the whole video, and
you can re-record narration section by section.

| Scene | Covers |
|---|---|
| `s1_problem` | Why the obvious design fails, ending on the split-purchase |
| `s2_where` | ACP, AP2, Razorpay — and the layer nobody builds |
| `s3_how` | The request shape, where the price comes from, the rule pipeline |
| `s4_edges` | Injection, splitting, the three-way outcome, the tamper bug |
| `s5_results` | Two-arm numbers, then the LLM finding |
| `s6_proof` | The anchor that closes that bug, and the live Razorpay rail |
| `s7_limits` | What it does not do, and the close |

Scene 6 is not a description of the ledger — it runs it. The chain on screen is
built by `spendgate.ledger` while the frame renders, rewritten the way an
attacker would rewrite it, and the two verdicts are whatever `verify_chain` and
`verify_against_anchor` actually return. If the fix regresses, the scene stops
claiming it works.

[`NARRATION.md`](NARRATION.md) is the script. The audio comes first and the
video is fitted to it — matching a render while talking is miserable and it
shows.

## The voice

`narrate.py` speaks each paragraph of `NARRATION.md` as its own clip, cloning a
reference voice, and keeps the clips: a fluffed line is re-taken with
`--scene N --chunk M` for the price of one paragraph rather than the film.

Chatterbox is a sampler, so it occasionally drops a clause or trails off, and
that is inaudible in a progress log. `verify_audio.py` transcribes every clip
with Whisper and diffs it against the line it was asked to read. Figures are
reduced to a single token before comparing — Whisper writes "96" where the
script says "ninety six", and flagging that buries the two defects that matter
under a page of noise. The figures themselves are checked against
`results/models.json`, which is where they came from.

## The webcam, and why the frame is fuller now

There isn't one. The first cut reserved the bottom-right corner for a live
camera, which cost the entire lower half of the frame — content is centred in
the band beneath the heading, so a floor drawn above the camera pinned every
scene into the top third and left 60% of the picture empty. That was the
"everything is small and floating at the top" problem, and it lived in the
geometry rather than in any one scene.

`FACECAM=1 ./render.sh final` restores the reservation for a live-narrated cut,
and `./render.sh check` draws the box so you can prove it.

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
