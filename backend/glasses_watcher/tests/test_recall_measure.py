"""Recall measurement: compare live video OCR output to ground-truth.

Ground truth = OCR run over the 12 hand-picked KBS screenshots (these are
the canonical "things that should be visible" — already validated by the
Phase 2 unit test which found 154 items).

Live = video_extraction.ocr_text_full from the .lifelog.json that
gemini_watcher just produced.

Recall = how many ground-truth items appear (exact or fuzzy match) in the
live OCR text. Fuzzy match uses normalized substring containment (the same
KOSPI number may render slightly differently across frames).

Also reports OLD baseline: how many ground-truth items appear in the
description fields from the v2-style extraction (no OCR pass) — the
content the VLM caught on its own.

Moved 2026-05-29 from C:\\Users\\A\\AppData\\Local\\Temp\\recall_measure.py
into the repo for permanence. Run from anywhere:
    {venv_python} backend/glasses_watcher/tests/test_recall_measure.py <clip.lifelog.json>
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\A\projects\healthcare-ai-agent")
sys.path.insert(0, str(ROOT / "backend" / "glasses_watcher"))

import ocr_preprocessor as op  # noqa: E402


def _normalize(s: str) -> str:
    """Lowercase + strip non-alphanumeric for fuzzy matching."""
    return re.sub(r"[^a-z0-9가-힣]", "", s.lower())


_FROZEN_GT_PATH = ROOT / "test_data" / "kbs_clip" / "ground_truth_frozen.json"


def _build_ground_truth() -> set[str]:
    """Return the normalized ground-truth item set.

    FROZEN by default: the recall fixes (a)/(d) change the OCR preprocessor,
    which would otherwise shift this screenshot-derived pool every run and make
    before/after recall deltas meaningless. So we snapshot the pool once to
    `ground_truth_frozen.json` and reuse it. Delete that file (or set
    REBUILD_GT=1) to regenerate from the current OCR config.
    """
    import os
    if _FROZEN_GT_PATH.exists() and not os.environ.get("REBUILD_GT"):
        return set(json.loads(_FROZEN_GT_PATH.read_text(encoding="utf-8")))
    from PIL import Image
    shot_dir = ROOT / "test_data" / "kbs_clip" / "screenshots"
    files = sorted(shot_dir.glob("*.png"))
    frames = [Image.open(p).convert("RGB") for p in files]
    op.reset_phash_cache()
    res = op.extract_text_from_frames(frames, [i * 5.0 for i in range(len(frames))])
    items = [
        x for x in res["ocr_full_text"].split("\n")
        if len(x.strip()) >= 2
        and not re.fullmatch(r"\d:\d{2}:\d{2}", x.strip())  # drop video timestamps
    ]
    gt = {_normalize(x) for x in items if _normalize(x)}
    _FROZEN_GT_PATH.write_text(json.dumps(sorted(gt), ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"   [froze ground truth: {len(gt)} items -> {_FROZEN_GT_PATH.name}]")
    return gt


def _live_items_from_json(json_path: Path) -> tuple[set[str], list[str]]:
    """Extract OCR items from a .lifelog.json (gemini-only output, v3)."""
    data = json.loads(json_path.read_text(encoding="utf-8"))
    items: set[str] = set()
    raw_items: list[str] = []
    arms = ("gemma", "qwen", "llama4", "gemini")
    for arm in arms:
        arm_data = data.get(arm, {})
        for ev in arm_data.get("events", []):
            ve = ev.get("_video_extraction") or {}
            for x in ve.get("ocr_text_full", []) or []:
                raw_items.append(str(x))
            ocr_flat = ev.get("_ocr_text_full") or ""
            for line in ocr_flat.split("\n"):
                if line.strip():
                    raw_items.append(line.strip())
    for x in raw_items:
        n = _normalize(x)
        if n:
            items.add(n)
    return items, raw_items


def _old_baseline_items_from_json(json_path: Path) -> set[str]:
    """Pre-v3 baseline: just whatever the VLM put in description / screen
    fields. Approximates the OLD (no-OCR) recall."""
    data = json.loads(json_path.read_text(encoding="utf-8"))
    items: set[str] = set()
    arms = ("gemma", "qwen", "llama4", "gemini")
    for arm in arms:
        for ev in data.get(arm, {}).get("events", []):
            for f in ("description", "screen", "audio_heard",
                      "numbers_mentioned", "topic", "decision"):
                v = ev.get(f)
                if isinstance(v, str) and v:
                    items.add(_normalize(v))
    return items


def recall_at_substring(gt: set[str], hay_text: str) -> tuple[int, int]:
    """For each ground-truth item, count it as 'recalled' if its normalized
    form appears as a substring anywhere in the normalized hay_text."""
    hay = _normalize(hay_text)
    hits = sum(1 for g in gt if g and g in hay)
    return hits, len(gt)


def main():
    if len(sys.argv) < 2:
        print("usage: test_recall_measure.py <path/to/clip.lifelog.json>")
        sys.exit(2)
    json_path = Path(sys.argv[1])
    if not json_path.exists():
        print(f"[ERR] not found: {json_path}")
        sys.exit(2)

    print("== Building ground truth from 12 KBS screenshots ==")
    gt = _build_ground_truth()
    print(f"   ground-truth items: {len(gt)}")

    print("\n== New pipeline (v3 with OCR) recall ==")
    new_items, new_raw = _live_items_from_json(json_path)
    print(f"   live OCR items from clip: {len(new_items)} (raw {len(new_raw)})")
    new_hay = "\n".join(new_raw)
    new_hits, new_n = recall_at_substring(gt, new_hay)
    new_pct = round(new_hits / max(1, new_n) * 100, 1)
    print(f"   recall@substring: {new_hits}/{new_n} = {new_pct}%")

    print("\n== Old baseline (VLM description fields only, no OCR pass) ==")
    old_items = _old_baseline_items_from_json(json_path)
    print(f"   old-style items (descriptions etc.): {len(old_items)}")
    old_hay = "\n".join(old_items)
    old_hits, _ = recall_at_substring(gt, old_hay)
    old_pct = round(old_hits / max(1, len(gt)) * 100, 1)
    print(f"   recall@substring: {old_hits}/{len(gt)} = {old_pct}%")

    print("\n== Summary ==")
    print(f"   OLD recall: {old_pct}%")
    print(f"   NEW recall: {new_pct}%")
    delta = round(new_pct - old_pct, 1)
    print(f"   Δ:          {delta:+}%")


if __name__ == "__main__":
    main()
