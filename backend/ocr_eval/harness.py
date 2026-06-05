"""OCR-engine evaluation harness — run each engine on the ground-truth frames,
collect entity-recovery / char-accuracy / latency metrics, write results JSON.

Run from backend/:  {venv} -m ocr_eval.harness --engines paddle_baseline[,paddle_structure,easy_ocr]
EVALUATION-ONLY; never touches the production pipeline.
"""
from __future__ import annotations

# DLL-ORDER GUARD: import torch FIRST so its DLLs (shm.dll etc.) load before any
# paddle import. The baseline engine pulls in production ocr_preprocessor ->
# paddle, and paddle-before-torch corrupts torch's DLL stack (WinError 127),
# which would break the torch-based EasyOCR engine that runs later in the same
# process. This mirrors production's torch-first ordering (_lifelog_test.py:51).
import torch  # noqa: F401  (import for DLL side-effect; must precede paddle)

import argparse
import json
import statistics
from pathlib import Path

from ocr_eval.metrics import compute_metrics

_ROOT = Path(__file__).resolve().parent
FRAMES_DIR = _ROOT / "test_data" / "frames"
GROUND_TRUTH = _ROOT / "test_data" / "ground_truth.json"
RESULTS_DIR = _ROOT / "results"


def _make_engine(key: str):
    if key == "paddle_baseline":
        from ocr_eval.engines.paddle_baseline import PaddleBaselineEngine
        return PaddleBaselineEngine()
    if key == "paddle_structure":
        from ocr_eval.engines.paddle_structure import PaddleStructureEngine
        return PaddleStructureEngine()
    if key == "easy_ocr":
        from ocr_eval.engines.easy_ocr import EasyOCREngine
        return EasyOCREngine()
    if key == "clova_ocr":
        from ocr_eval.engines.clova_ocr import ClovaOCREngine
        return ClovaOCREngine()
    raise ValueError(f"unknown engine key: {key}")


def run_evaluation(engine_keys: list[str]) -> dict:
    ground_truth = json.loads(GROUND_TRUTH.read_text(encoding="utf-8"))
    frames = [f for f in ground_truth
              if not f.startswith("_") and not ground_truth[f].get("appendix")]
    out: dict = {"frames": frames, "engines": {}}

    for key in engine_keys:
        engine = _make_engine(key)
        print(f"\n=== {engine.name} ===")
        if not engine.initialize():
            print(f"[SKIP] {engine.name} failed to initialize")
            out["engines"][engine.name] = {"skipped": True}
            continue

        per_frame = {}
        lats, recov_tot, tok_tot = [], 0, 0
        for frame in frames:
            res = engine.extract(str(FRAMES_DIR / frame))
            m = compute_metrics(res, ground_truth[frame])
            per_frame[frame] = {"metrics": m, "ocr_texts": res.texts()}
            lats.append(m["latency_ms"])
            recov_tot += m["tokens_recovered"]
            tok_tot += m["tokens_total"]
            print(f"  {frame}: {m['tokens_recovered']}/{m['tokens_total']} recovered "
                  f"| char_acc {m['mean_char_accuracy']} | {m['latency_ms']}ms"
                  + (f" | ERR {m['error']}" if m['error'] else ""))

        out["engines"][engine.name] = {
            "cost_usd_per_1000": engine.estimated_cost_usd,
            "overall_recovery_rate": round(recov_tot / max(1, tok_tot), 3),
            "tokens_recovered": recov_tot,
            "tokens_total": tok_tot,
            "latency_p50_ms": round(statistics.median(lats), 1) if lats else 0,
            "latency_max_ms": round(max(lats), 1) if lats else 0,
            "per_frame": per_frame,
        }
        e = out["engines"][engine.name]
        print(f"  OVERALL: {e['tokens_recovered']}/{e['tokens_total']} "
              f"({e['overall_recovery_rate']*100:.0f}%) | p50 {e['latency_p50_ms']}ms | "
              f"${e['cost_usd_per_1000']}/1k")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engines", default="paddle_baseline",
                    help="comma-separated: paddle_baseline,paddle_structure,easy_ocr,clova_ocr")
    ap.add_argument("--out", default=str(RESULTS_DIR / "results.json"))
    args = ap.parse_args()
    keys = [k.strip() for k in args.engines.split(",") if k.strip()]
    results = run_evaluation(keys)
    RESULTS_DIR.mkdir(exist_ok=True)
    Path(args.out).write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n[OK] wrote {args.out}")


if __name__ == "__main__":
    main()
