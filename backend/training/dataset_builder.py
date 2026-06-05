"""Orchestrate the Job 2 dataset build: DB consensus -> labeled (input, label) JSONL.

Read-only over the DB + video files; writes only under `output_root/version`. Reuses
Job 1's consensus (per-chunk) and preserves determinism end-to-end:
  - arms sorted before clustering (event_query),
  - chunks keyed by chunk_idx and windowed by even-split,
  - transcript segments + OCR tokens SORTED before serialisation (a set->list would be
    non-deterministic and would break the byte-identical re-run guarantee),
  - train/val split by SHA256(seed:example_id).
Same DB state + same videos -> same dataset bytes (modulo the manifest timestamp).
"""
from __future__ import annotations

from pathlib import Path

from .event_query import (
    fetch_multi_arm_events,
    group_events_into_chunks,
    compute_per_chunk_consensus,
)
from .frame_extractor import (
    get_video_duration,
    compute_chunk_window,
    extract_frames_uniform,
)
from .label_filter import split_by_confidence_tier, has_sufficient_labels
from .dataset_writer import make_example, write_jsonl, write_manifest, split_train_val


def _aggregate_inputs(chunk_events: list[dict]) -> tuple[str, list[str]]:
    """Collect transcript + OCR from a chunk's events (flattened fields). Both are
    SORTED-unique for determinism (a set->list ordering would differ run to run)."""
    transcripts: set[str] = set()
    ocr: set[str] = set()
    for e in chunk_events:
        ae = e.get("audio_extraction")
        if isinstance(ae, dict):
            tx = ae.get("transcript_full")
            if isinstance(tx, str) and tx.strip():
                transcripts.add(tx.strip())
        ve = e.get("video_extraction")
        if isinstance(ve, dict):
            for tok in (ve.get("ocr_text_full") or []):
                if isinstance(tok, str) and tok.strip():
                    ocr.add(tok.strip())
    return "\n\n".join(sorted(transcripts)), sorted(ocr)


async def build_dataset(
    output_root: str = "training_data",
    version: str = "v1.0.0",
    video_source_dir: str = "C:/Users/A/AIMB-Bridge",
    frames_per_chunk: int = 16,
    min_labels_per_chunk: int = 3,
    high_confidence_threshold: float = 0.83,
    medium_confidence_threshold: float = 0.67,
    val_fraction: float = 0.2,
) -> dict:
    """Build the full dataset. Returns a summary dict."""
    output_dir = Path(output_root) / version
    (output_dir / "frames").mkdir(parents=True, exist_ok=True)

    events_by_video = await fetch_multi_arm_events(min_arms=2)
    print(f"[OK] {len(events_by_video)} multi-arm VLM clips with consensus-capable facts")

    examples: list[dict] = []
    skipped_no_video: list[str] = []
    skipped_no_consensus: list[str] = []
    skipped_insufficient_labels: list[str] = []
    arms_seen: set[str] = set()

    for source_video in sorted(events_by_video):
        events = events_by_video[source_video]
        video_path = Path(video_source_dir) / source_video
        if not video_path.exists():
            skipped_no_video.append(source_video)
            print(f"[SKIP] video file missing: {source_video}")
            continue

        try:
            duration = get_video_duration(str(video_path))
        except Exception as e:
            skipped_no_video.append(source_video)
            print(f"[ERR] cannot read duration for {source_video}: {type(e).__name__}: {str(e)[:100]}")
            continue

        chunks = group_events_into_chunks(events)
        total_chunks = len(chunks)
        clip_id = source_video.rsplit(".", 1)[0]

        for chunk_idx, chunk_events in chunks.items():
            tag = f"{source_video}/chunk_{chunk_idx}"
            consensus = compute_per_chunk_consensus(
                chunk_events, min_agreement_fraction=medium_confidence_threshold)
            if not consensus:
                skipped_no_consensus.append(tag)
                print(f"[SKIP] no consensus: {tag}")
                continue

            tiered = split_by_confidence_tier(
                consensus, high_threshold=high_confidence_threshold,
                medium_threshold=medium_confidence_threshold)
            if not has_sufficient_labels(tiered["high"] + tiered["medium"], min_labels_per_chunk):
                skipped_insufficient_labels.append(tag)
                print(f"[SKIP] <{min_labels_per_chunk} labels: {tag}")
                continue

            start_sec, end_sec = compute_chunk_window(duration, chunk_idx, total_chunks)
            chunk_id = f"chunk_{chunk_idx:03d}"
            frames_subdir = output_dir / "frames" / clip_id / chunk_id
            frame_paths = extract_frames_uniform(
                video_path=str(video_path), output_dir=str(frames_subdir),
                num_frames=frames_per_chunk, start_sec=start_sec, end_sec=end_sec)
            if len(frame_paths) < frames_per_chunk:
                print(f"[WARN] {tag}: extracted {len(frame_paths)}/{frames_per_chunk} frames")

            relative_frame_paths = [
                str(Path("frames") / clip_id / chunk_id / Path(p).name) for p in frame_paths]
            audio_transcript, ocr_text = _aggregate_inputs(chunk_events)
            for e in chunk_events:
                if e.get("source_model"):
                    arms_seen.add(e["source_model"])

            example = make_example(
                example_id=f"{clip_id}__{chunk_id}",
                source_video=source_video,
                chunk_start_sec=round(start_sec, 3),
                chunk_end_sec=round(end_sec, 3),
                frame_paths=relative_frame_paths,
                audio_transcript=audio_transcript,
                ocr_text=ocr_text,
                consensus_facts_high=tiered["high"],
                consensus_facts_medium=tiered["medium"],
                metadata={
                    "language": "ko",
                    "content_type": "broadcast",
                    "arms_compared": len({e.get("source_model") for e in chunk_events if e.get("source_model")}),
                    "fact_count_high": len(tiered["high"]),
                    "fact_count_medium": len(tiered["medium"]),
                    "transcript_length_chars": len(audio_transcript),
                    "ocr_item_count": len(ocr_text),
                },
            )
            examples.append(example)
            print(f"[OK] example {example['example_id']}: "
                  f"{len(tiered['high'])} high + {len(tiered['medium'])} med labels, "
                  f"{len(frame_paths)} frames")

    train, val = split_train_val(examples, val_fraction=val_fraction)
    write_jsonl(train, str(output_dir / "train.jsonl"))
    write_jsonl(val, str(output_dir / "val.jsonl"))
    write_manifest(
        output_dir=str(output_dir), dataset_version=version,
        train_count=len(train), val_count=len(val),
        source_videos=sorted(events_by_video.keys()), arms_used=sorted(arms_seen),
        generation_metadata={
            "frames_per_chunk": frames_per_chunk,
            "min_labels_per_chunk": min_labels_per_chunk,
            "high_confidence_threshold": high_confidence_threshold,
            "medium_confidence_threshold": medium_confidence_threshold,
            "val_fraction": val_fraction,
            "video_source_dir": video_source_dir,
            "skipped_no_video": skipped_no_video,
            "skipped_no_consensus": skipped_no_consensus,
            "skipped_insufficient_labels": skipped_insufficient_labels,
        },
        extra={
            "first_build": True,
            "dataset_size_category": "thin_start",
            "expected_growth_pattern": "auto-grows as new multi-arm v3.4+ events accumulate",
        },
    )

    summary = {
        "total_examples": len(examples),
        "train": len(train),
        "val": len(val),
        "output_dir": str(output_dir),
        "skipped_no_video": len(skipped_no_video),
        "skipped_no_consensus": len(skipped_no_consensus),
        "skipped_insufficient_labels": len(skipped_insufficient_labels),
    }
    print(f"[OK] dataset build complete: {summary}")
    return summary
