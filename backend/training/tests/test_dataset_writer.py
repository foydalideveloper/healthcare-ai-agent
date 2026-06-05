"""Unit tests for Job 2 dataset_writer (pure + tmp-file IO).

Run: {venv} -m pytest backend/training/tests/test_dataset_writer.py -v
"""
import json
import sys
import tempfile
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[3]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from training.dataset_writer import (  # noqa: E402
    DATASET_SCHEMA_VERSION,
    make_example,
    write_jsonl,
    split_train_val,
    write_manifest,
)


def _example(i):
    return make_example(
        example_id=f"clip__chunk_{i:03d}",
        source_video="20260528144922838.mp4",
        chunk_start_sec=0.0,
        chunk_end_sec=30.8,
        frame_paths=[f"frames/clip/chunk_{i:03d}/frame_000.png"],
        audio_transcript="삼성전자는 307,000원입니다.",
        ocr_text=["KOSPI", "8,228.70"],
        consensus_facts_high=[{"fact": "KOSPI is at 8,228.70."}],
        consensus_facts_medium=[{"fact": "Samsung at 307,000 won."}],
        metadata={"language": "ko", "arms_compared": 4},
    )


def test_make_example_schema():
    ex = _example(0)
    assert ex["dataset_schema_version"] == DATASET_SCHEMA_VERSION
    for key in ("example_id", "source_video", "chunk_start_sec", "chunk_end_sec",
                "inputs", "labels", "metadata"):
        assert key in ex
    assert set(ex["inputs"]) == {"frame_paths", "audio_transcript", "ocr_text"}
    assert ex["labels"]["fact_count_high"] == 1
    assert ex["labels"]["fact_count_medium"] == 1


def test_make_example_korean_preserved():
    ex = _example(0)
    assert ex["inputs"]["audio_transcript"] == "삼성전자는 307,000원입니다."


def test_write_jsonl_round_trip():
    examples = [_example(i) for i in range(3)]
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "out.jsonl"
        write_jsonl(examples, str(p))
        back = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines()]
    assert back == examples


def test_write_jsonl_one_per_line():
    examples = [_example(i) for i in range(5)]
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "out.jsonl"
        write_jsonl(examples, str(p))
        lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 5
    for line in lines:
        json.loads(line)  # each line independently valid JSON


def test_split_train_val_deterministic():
    examples = [_example(i) for i in range(200)]
    import random
    shuffled = examples[:]
    random.Random(7).shuffle(shuffled)
    tr1, va1 = split_train_val(examples)
    tr2, va2 = split_train_val(shuffled)
    assert {e["example_id"] for e in va1} == {e["example_id"] for e in va2}
    assert {e["example_id"] for e in tr1} == {e["example_id"] for e in tr2}


def test_split_train_val_fraction():
    examples = [_example(i) for i in range(1000)]
    train, val = split_train_val(examples, val_fraction=0.2)
    assert abs(len(val) / 1000 - 0.2) < 0.05         # ~20% ±5pts


def test_split_train_val_no_overlap():
    examples = [_example(i) for i in range(300)]
    train, val = split_train_val(examples)
    tr_ids = {e["example_id"] for e in train}
    va_ids = {e["example_id"] for e in val}
    assert tr_ids.isdisjoint(va_ids)
    assert len(tr_ids) + len(va_ids) == 300


def test_write_manifest_contains_required_fields():
    with tempfile.TemporaryDirectory() as td:
        m = write_manifest(
            output_dir=td, dataset_version="v1.0.0", train_count=8, val_count=2,
            source_videos=["a.mp4"], arms_used=["gemma4", "gemini_2_5_pro"],
            generation_metadata={"frames_per_chunk": 16},
            extra={"first_build": True, "dataset_size_category": "thin_start",
                   "expected_growth_pattern": "auto-grows as new multi-arm v3.4+ events accumulate"},
        )
        on_disk = json.loads((Path(td) / "manifest.json").read_text(encoding="utf-8"))
    assert on_disk == m
    for key in ("dataset_schema_version", "dataset_version", "generated_at",
                "train_examples", "val_examples", "total_examples", "source_videos",
                "arms_used", "generation_metadata", "first_build", "dataset_size_category"):
        assert key in on_disk
    assert on_disk["total_examples"] == 10
    assert on_disk["first_build"] is True
