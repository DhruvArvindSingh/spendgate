#!/usr/bin/env python3
"""Listen back to the narration and check it says what the script says.

    VOICE=.../voice/.venv/bin/python
    $VOICE video/verify_audio.py                # every chunk
    $VOICE video/verify_audio.py --scene 4

Chatterbox is a sampler: it occasionally drops a clause, repeats a word, or
trails off. That is inaudible in a progress log and obvious to a viewer, so
each chunk is transcribed with Whisper and diffed against the line it was
asked to read. Anything above --threshold is named, with the exact command to
re-take just that chunk.

This checks the words, not the delivery — a chunk can score 0.00 and still be
read badly. Listen to the ones it flags, then listen to the film.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

#: What the model hears versus what the script spells — not errors.
HOMOPHONES = {
    "spendgate": "spend gate", "authorised": "authorized",
    "minimax": "mini max", "razorpay": "razor pay",
    "rubies": "rupees", "ruby": "rupee", "raiser": "razor",
    "for lack": "four lakh",
}

NUMBERY = (set("zero one two three four five six seven eight nine ten eleven "
               "twelve thirteen fourteen fifteen sixteen seventeen eighteen "
               "nineteen twenty thirty forty fifty sixty seventy eighty ninety "
               "hundred thousand lakh crore million".split()))


def words(text: str) -> list[str]:
    """The spoken words, with every figure reduced to a single '#'.

    Whisper writes "96" where the script says "ninety six", and "5 000" where
    it says "five thousand" — comparing those as text marks every number in the
    film wrong and buries the defects that matter. So a run of number words or
    digits collapses to one token: this check is asking whether the sentence
    was read, not whether the figure is right. The figures are checked against
    results/models.json, which is where they came from.
    """
    text = text.lower()
    for src, dst in HOMOPHONES.items():
        text = text.replace(src, dst)
    out: list[str] = []
    for tok in re.sub(r"[^a-z0-9 ]", " ", text).split():
        if tok in ("a", "an"):
            continue                       # Whisper drops articles at speed
        numeric = tok in NUMBERY or tok.isdigit()
        if numeric and tok != "one":       # "one reason", "the one I got wrong"
            if out and out[-1] == "#":
                continue
            if out and out[-1] == "and" and len(out) > 1 and out[-2] == "#":
                out.pop()                  # "a hundred AND eighty seven"
                continue
            out.append("#")
        else:
            out.append(tok)
    return out


def wer(want: list[str], got: list[str]) -> tuple[float, str]:
    """Word error rate, plus a short human description of the difference."""
    sm = difflib.SequenceMatcher(None, want, got, autojunk=False)
    bad, notes = 0, []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        bad += max(i2 - i1, j2 - j1)
        if tag == "delete":
            notes.append(f"dropped {' '.join(want[i1:i2])!r}")
        elif tag == "insert":
            notes.append(f"added {' '.join(got[j1:j2])!r}")
        else:
            notes.append(f"{' '.join(want[i1:i2])!r} -> {' '.join(got[j1:j2])!r}")
    return bad / max(len(want), 1), "; ".join(notes[:3])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", type=int, action="append", default=[])
    ap.add_argument("--threshold", type=float, default=0.15)
    ap.add_argument("--model", default="base.en")
    args = ap.parse_args()

    manifest = json.loads((HERE / "audio" / "manifest.json").read_text())
    from faster_whisper import WhisperModel
    model = WhisperModel(args.model, device="cpu", compute_type="int8")

    flagged = []
    for key in sorted(manifest, key=lambda k: int(k[1:])):
        n = int(key[1:])
        if args.scene and n not in args.scene:
            continue
        rec = manifest[key]
        print(f"\n── {key} · {rec['title']}  ({rec['spoken_s']}s)")
        for row in rec["chunks"]:
            wav = HERE / "audio" / key / f"{row['i']:03d}.wav"
            segs, _ = model.transcribe(str(wav), beam_size=1)
            heard = words(" ".join(s.text for s in segs))
            rate, note = wer(words(row["text"]), heard)
            mark = "!!" if rate > args.threshold else "  "
            print(f"  {mark} {row['i']:2} {rate:5.1%} {row['dur']:5.1f}s  {note[:88]}")
            if rate > args.threshold:
                flagged.append((n, row["i"], rate, note))

    print()
    if not flagged:
        print(f"  all chunks within {args.threshold:.0%} of the script.")
        return 0
    print(f"  {len(flagged)} chunk(s) over {args.threshold:.0%} — re-take with:")
    for n in sorted({f[0] for f in flagged}):
        ids = " ".join(f"--chunk {f[1]}" for f in flagged if f[0] == n)
        print(f"    $VOICE video/narrate.py --scene {n} {ids}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
