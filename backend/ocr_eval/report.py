"""Render a side-by-side OCR-engine comparison report from a results.json.

Run from backend/:  {venv} -m ocr_eval.report [results.json]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
GROUND_TRUTH = _ROOT / "test_data" / "ground_truth.json"


def render(results_path: str) -> str:
    data = json.loads(Path(results_path).read_text(encoding="utf-8"))
    gt = json.loads(GROUND_TRUTH.read_text(encoding="utf-8"))
    engines = {k: v for k, v in data["engines"].items() if not v.get("skipped")}
    frames = data["frames"]
    lines = ["=== OCR ENGINE EVALUATION RESULTS ===", ""]

    # Summary table
    lines.append(f"{'Engine':<24} {'Recovery':<14} {'CharAcc':<8} {'p50 ms':<9} {'$/1k':<7}")
    lines.append("-" * 66)
    for name, e in engines.items():
        # mean char acc across frames
        accs = [e["per_frame"][f]["metrics"]["mean_char_accuracy"] for f in frames]
        cacc = sum(accs) / len(accs) if accs else 0
        rec = f"{e['tokens_recovered']}/{e['tokens_total']} ({e['overall_recovery_rate']*100:.0f}%)"
        lines.append(f"{name:<24} {rec:<14} {cacc*100:>5.0f}%   {e['latency_p50_ms']:<9} ${e['cost_usd_per_1000']}")
    lines.append("")

    # Per-frame breakdown
    for frame in frames:
        desc = gt.get(frame, {}).get("_desc", "")
        lines.append(f"[{frame}] {desc}")
        for name, e in engines.items():
            m = e["per_frame"][frame]["metrics"]
            miss = [t for t, v in m["per_token"].items() if not v["recovered"]]
            hit = [t for t, v in m["per_token"].items() if v["recovered"]]
            lines.append(f"  {name:<24} {m['tokens_recovered']}/{m['tokens_total']} "
                         f"({m['recovery_rate']*100:.0f}%)  acc {m['mean_char_accuracy']*100:.0f}%  {m['latency_ms']}ms")
            if hit:
                lines.append(f"      hit:  {', '.join(hit)}")
            if miss:
                lines.append(f"      MISS: {', '.join(miss)}")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else str(_ROOT / "results" / "results.json")
    print(render(path))
