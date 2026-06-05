"""CLI entry point for the Job 2 dataset builder.

Run from backend/:  {venv} -m training.cli --version v1.0.0
Exit code 0 on success, 1 if no examples were built (total failure).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from .dataset_builder import build_dataset


def main() -> int:
    ap = argparse.ArgumentParser(description="Build a training dataset from cross-arm consensus events")
    ap.add_argument("--output-root", default="training_data")
    ap.add_argument("--version", default="v1.0.0")
    ap.add_argument("--video-source-dir", default="C:/Users/A/AIMB-Bridge")
    ap.add_argument("--frames-per-chunk", type=int, default=16)
    ap.add_argument("--min-labels-per-chunk", type=int, default=3)
    ap.add_argument("--high-threshold", type=float, default=0.83)
    ap.add_argument("--medium-threshold", type=float, default=0.67)
    ap.add_argument("--val-fraction", type=float, default=0.2)
    args = ap.parse_args()

    summary = asyncio.run(build_dataset(
        output_root=args.output_root,
        version=args.version,
        video_source_dir=args.video_source_dir,
        frames_per_chunk=args.frames_per_chunk,
        min_labels_per_chunk=args.min_labels_per_chunk,
        high_confidence_threshold=args.high_threshold,
        medium_confidence_threshold=args.medium_threshold,
        val_fraction=args.val_fraction,
    ))

    print("\n" + json.dumps(summary, indent=2))
    return 0 if summary["total_examples"] > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
