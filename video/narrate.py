#!/usr/bin/env python3
"""Speak NARRATION.md in the Zenn voice, one file per scene.

    VOICE=/path/to/voice/.venv/bin/python
    $VOICE video/narrate.py --dump          # show the chunking, generate nothing
    $VOICE video/narrate.py --all           # the whole script
    $VOICE video/narrate.py --scene 3       # just scene 3, to re-take it

Chunking follows the script's own paragraphs rather than a character count:
a paragraph break in NARRATION.md is a breath in the delivery, and the gap
between chunks is what carries it. Long paragraphs split at sentence ends.

Output, per scene N:  audio/sN/001.wav ... plus audio/sN.wav and a manifest.
The per-chunk wavs are kept so a single fluffed line can be regenerated
without paying for the rest of the scene.
"""
from __future__ import annotations

import argparse
import gc
import json
import os
import re
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "NARRATION.md"
REF = Path("/home/dhruv/C_drive/Youtube/CreatureSense/Is Your Dog's Lick "
           "Healing You — or Killing You/zenn_ref_CLEAN.wav")

#: Chatterbox reads these the wrong way round; say them as they are spoken.
SAY = [
    (r"\bGPT-5\b", "GPT five"),
    (r"\bAP2\b", "A P two"),
    (r"\bACP\b", "A C P"),
    (r"\bSpendGate\b", "Spend Gate"),
    (r"\bUPI\b", "U P I"),
    (r"—", ","),          # em dash: a comma's pause, not a word
    (r"\*", ""),           # emphasis markers
]

GAP_PHRASE = 0.28         # between chunks of one paragraph
GAP_PARA = 0.55           # between paragraphs — the script's own breaths
MAX_CHARS = 210


def spoken(text: str) -> str:
    for pat, rep in SAY:
        text = re.sub(pat, rep, text)
    text = re.sub(r"\s+([,.;:])", r"\1", text)      # em-dash swap leaves " ,"
    return re.sub(r"\s+", " ", text).strip()


def scenes(path: Path) -> list[dict]:
    """Parse '## 01 · Title — 31s' sections and their quoted narration."""
    out: list[dict] = []
    cur: dict | None = None
    para: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        head = re.match(r"##\s+(\d+)\s+·\s+(.+?)\s+—\s+(\d+)s\s*$", line)
        if head:
            if cur:
                if para:
                    cur["paras"].append(" ".join(para))
                out.append(cur)
            para = []
            cur = {"n": int(head.group(1)), "title": head.group(2),
                   "written_s": int(head.group(3)), "paras": []}
            continue
        if cur is None:
            continue
        if line.startswith("## ") or line.startswith("---"):
            if para:
                cur["paras"].append(" ".join(para))
            para = []
            out.append(cur)
            cur = None
            continue
        if line.startswith(">"):
            body = line[1:].strip()
            if body:
                para.append(body)
            elif para:
                cur["paras"].append(" ".join(para))
                para = []
    if cur:
        if para:
            cur["paras"].append(" ".join(para))
        out.append(cur)
    return out


def chunk(paras: list[str]) -> list[tuple[str, float]]:
    """(text, gap after) — sentence-merged within a paragraph, gap at its end."""
    items: list[tuple[str, float]] = []
    for p in paras:
        sents = [s.strip() for s in re.findall(r"[^.!?]+[.!?]+|\S[^.!?]*$", p) if s.strip()]
        parts: list[str] = []
        cur = ""
        for s in sents:
            cand = f"{cur} {s}".strip()
            if cur and len(cand) > MAX_CHARS:
                parts.append(cur)
                cur = s
            else:
                cur = cand
        if cur:
            parts.append(cur)
        for i, part in enumerate(parts):
            items.append((spoken(part), GAP_PARA if i == len(parts) - 1 else GAP_PHRASE))
    return items


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--scene", type=int, action="append", default=[])
    ap.add_argument("--chunk", type=int, action="append", default=[],
                    help="with a single --scene, regenerate only these chunks")
    ap.add_argument("--ref", default=str(REF))
    ap.add_argument("--exag", type=float, default=0.5)
    ap.add_argument("--cfg", type=float, default=0.4)
    ap.add_argument("--temp", type=float, default=0.7)
    ap.add_argument("--outdir", default=str(HERE / "audio"))
    ap.add_argument("--min-vram", type=float, default=6.0,
                    help="GB of VRAM below which CUDA is not worth attempting")
    args = ap.parse_args()

    scs = scenes(SCRIPT)
    want = set(args.scene) if args.scene else {s["n"] for s in scs}
    todo = [s for s in scs if s["n"] in want]

    if args.dump:
        for s in scs:
            items = chunk(s["paras"])
            words = sum(len(t.split()) for t, _ in items)
            gaps = sum(g for _, g in items)
            print(f"\n── scene {s['n']} · {s['title']}  "
                  f"(written {s['written_s']}s, {words} words, "
                  f"~{words / 145 * 60 + gaps:.0f}s at 145wpm)")
            for i, (t, g) in enumerate(items, 1):
                print(f"  {i:2} [{g:.2f}] {t}")
        return 0
    if not (args.all or args.scene):
        ap.error("say --all or --scene N (or --dump)")

    import numpy as np
    import soundfile as sf
    import torch
    from chatterbox.tts import ChatterboxTTS

    # Chatterbox wants ~6GB. A 4GB laptop card loads it and then dies partway
    # through the first generation, which costs a model load to discover, so
    # check the card's size instead of finding out.
    dev, why = "cpu", "FORCE_CPU"
    if os.environ.get("FORCE_CPU") != "1":
        if not torch.cuda.is_available():
            why = "no CUDA"
        else:
            vram = torch.cuda.get_device_properties(0).total_memory / 2**30
            if vram >= args.min_vram:
                dev, why = "cuda", f"{vram:.1f}GB"
            else:
                why = f"{vram:.1f}GB card, need {args.min_vram:.0f}GB"
    print(f"device {dev} ({why}) · scenes {sorted(want)} · ref {Path(args.ref).name}")
    t0 = time.time()
    model = ChatterboxTTS.from_pretrained(device=dev)
    sr = model.sr
    print(f"model ready in {time.time() - t0:.0f}s (sr={sr})")

    kw = dict(exaggeration=args.exag, cfg_weight=args.cfg, temperature=args.temp)
    if os.path.exists(args.ref):
        kw["audio_prompt_path"] = args.ref
    else:
        raise SystemExit(f"reference voice not found: {args.ref}")

    root = Path(args.outdir)
    manifest = {}
    for s in todo:
        items = chunk(s["paras"])
        d = root / f"s{s['n']}"
        d.mkdir(parents=True, exist_ok=True)
        only = set(args.chunk) if (args.chunk and len(want) == 1) else None
        for i, (text, _gap) in enumerate(items, 1):
            wav_path = d / f"{i:03d}.wav"
            if only is not None and i not in only:
                continue
            t = time.time()
            for attempt in range(2):
                try:
                    wav = model.generate(text, **kw)
                    break
                except (torch.OutOfMemoryError, RuntimeError) as e:
                    if "out of memory" not in str(e).lower() or dev == "cpu":
                        raise
                    # Reload on CPU and keep going: an hour of slow generation
                    # beats a dead run, and the chunks already written stand.
                    print(f"  [{s['n']}.{i}] CUDA OOM — reloading on CPU")
                    del model
                    gc.collect()
                    torch.cuda.empty_cache()
                    dev = "cpu"
                    model = ChatterboxTTS.from_pretrained(device=dev)
            arr = wav.squeeze(0).cpu().numpy()
            sf.write(wav_path, arr, sr)
            print(f"  s{s['n']} [{i:2}/{len(items)}] {len(arr) / sr:5.1f}s "
                  f"gen {time.time() - t:5.1f}s  {text[:52]}")
            gc.collect()
            if dev == "cuda":
                torch.cuda.empty_cache()

        # Stitch the scene from whatever chunk wavs are on disk.
        pieces, rows, clock = [], [], 0.0
        for i, (text, gap) in enumerate(items, 1):
            a, _ = sf.read(d / f"{i:03d}.wav")
            rows.append({"i": i, "start": round(clock, 3),
                         "dur": round(len(a) / sr, 3), "gap": gap, "text": text})
            clock += len(a) / sr + gap
            pieces += [a, np.zeros(int(sr * gap), dtype=a.dtype)]
        track = np.concatenate(pieces[:-1])          # no trailing gap
        sf.write(root / f"s{s['n']}.wav", track, sr)
        secs = len(track) / sr
        manifest[f"s{s['n']}"] = {"title": s["title"], "written_s": s["written_s"],
                                  "spoken_s": round(secs, 2), "chunks": rows}
        print(f"  → s{s['n']}.wav  {secs:.1f}s "
              f"(script said {s['written_s']}s)\n")

    mf = root / "manifest.json"
    old = json.loads(mf.read_text()) if mf.exists() else {}
    old.update(manifest)
    mf.write_text(json.dumps(old, indent=2))
    total = sum(v["spoken_s"] for v in old.values())
    print(f"total {total:.0f}s = {int(total // 60)}:{int(total % 60):02d}  → {mf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
