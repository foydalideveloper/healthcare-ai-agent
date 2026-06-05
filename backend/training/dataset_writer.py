"""Write the Job 2 training dataset: JSONL examples + versioned manifest (read-only DB).

Each example pairs INPUTS the model sees (frames + transcript + OCR) with LABELS it
should predict (high-/medium-confidence consensus facts from Job 1). The train/val
split is deterministic by SHA256(seed:example_id) so Job 3 gets the same split every
run — reproducibility is the whole point of versioning the dataset.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

DATASET_SCHEMA_VERSION = "1.0.0"


def make_example(
    example_id: str,
    source_video: str,
    chunk_start_sec: float,
    chunk_end_sec: float,
    frame_paths: list[str],
    audio_transcript: str,
    ocr_text: list[str],
    consensus_facts_high: list[dict],
    consensus_facts_medium: list[dict],
    metadata: dict,
) -> dict:
    """Build one training example. INPUTS = frames+transcript+ocr; LABELS = consensus
    facts split by confidence tier. `dataset_schema_version` is embedded so Job 3 can
    detect format changes per-example, not just via the manifest."""
    return {
        "dataset_schema_version": DATASET_SCHEMA_VERSION,
        "example_id": example_id,
        "source_video": source_video,
        "chunk_start_sec": chunk_start_sec,
        "chunk_end_sec": chunk_end_sec,
        "inputs": {
            "frame_paths": frame_paths,           # relative to the dataset version dir
            "audio_transcript": audio_transcript,
            "ocr_text": ocr_text,
        },
        "labels": {
            "high_confidence_facts": [f["fact"] for f in consensus_facts_high],
            "medium_confidence_facts": [f["fact"] for f in consensus_facts_medium],
            "fact_count_high": len(consensus_facts_high),
            "fact_count_medium": len(consensus_facts_medium),
        },
        "metadata": metadata,
    }


def write_jsonl(examples: list[dict], output_path: str) -> None:
    """Write one example per line, UTF-8, ensure_ascii=False (Korean preserved), no
    pretty-printing (machine-readable)."""
    with open(output_path, "w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")


def split_train_val(
    examples: list[dict],
    val_fraction: float = 0.2,
    seed: int = 42,
) -> tuple[list[dict], list[dict]]:
    """Deterministic split by hashing `seed:example_id` → [0,1) bucket. Same id (+seed)
    always lands in the same split, regardless of input order or run — Job 3 reproducible."""
    train: list[dict] = []
    val: list[dict] = []
    for ex in examples:
        h = hashlib.sha256(f"{seed}:{ex['example_id']}".encode("utf-8")).hexdigest()
        bucket = int(h[:8], 16) / 0xFFFFFFFF
        (val if bucket < val_fraction else train).append(ex)
    return train, val


def write_manifest(
    output_dir: str,
    dataset_version: str,
    train_count: int,
    val_count: int,
    source_videos: list[str],
    arms_used: list[str],
    generation_metadata: dict,
    extra: dict | None = None,
) -> dict:
    """Write manifest.json (dataset version + stats + build params). `extra` is merged
    at the top level (e.g. first_build / dataset_size_category flags). Returns the dict."""
    manifest = {
        "dataset_schema_version": DATASET_SCHEMA_VERSION,
        "dataset_version": dataset_version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "train_examples": train_count,
        "val_examples": val_count,
        "total_examples": train_count + val_count,
        "source_videos": source_videos,
        "arms_used": arms_used,
        "generation_metadata": generation_metadata,
    }
    if extra:
        manifest.update(extra)
    with open(Path(output_dir) / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    return manifest
