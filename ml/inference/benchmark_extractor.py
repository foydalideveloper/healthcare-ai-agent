"""Benchmark: Gemma 4 E2B vs current regex extractor on voice-report transcripts.

Compares the two extraction pipelines on labeled Whisper transcripts:
  - Current:  event_processor.py regex + FOOD_DB/MED_DB keyword lookup
  - Gemma 4:  llama-server hosting gemma-4-E2B-it-GGUF at http://localhost:8080

Measures:
  - extraction accuracy (foods, exercise, medicine, hydration — by F1 on key fields)
  - p50/p95 latency
  - cost (always $0 for both — all local)

Usage:
    # Server must be running in another window:
    #   llama-server -hf ggml-org/gemma-4-E2B-it-GGUF --port 8080
    python ml/inference/benchmark_extractor.py
"""

import json
import re
import statistics
import sys
import time
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend" / "glasses_watcher"))

LLAMA_SERVER = "http://localhost:8080/v1/chat/completions"
MODEL_TAG    = "gemma-4-E2B-it"

# ── Test set (labeled transcripts drawn from real watcher history) ──
# Each sample: (transcript, ground_truth)
# ground_truth uses the same shape event_processor emits: foods, exercise, medications, hydration.
TEST_SET = [
    {
        "id": "apr24_morning_tea_exercise",
        "transcript": "I'm drinking iced tea and today in the morning I had 45 minutes of exercise and in the lunch I ate fish which is called mackerel.",
        "truth": {
            "foods": [{"name": "mackerel"}, {"name": "iced tea"}],
            "exercise": {"minutes": 45},
            "medications": [],
        },
    },
    {
        "id": "apr22_voice_vitamin_d",
        "transcript": "Good morning, I just took my Vitamin D supplement.",
        "truth": {
            "foods": [],
            "exercise": None,
            "medications": [{"drug_name": "Vitamin D"}],
        },
    },
    {
        "id": "apr23_korean_food",
        "transcript": "점심으로 피자 먹고 홍차 한 잔 마셨어.",
        "truth": {
            "foods": [{"name": "피자"}, {"name": "홍차"}],
            "exercise": None,
            "medications": [],
        },
    },
    {
        "id": "apr22_burger_water",
        "transcript": "I had a burger for lunch and drank a bottle of water.",
        "truth": {
            "foods": [{"name": "burger"}, {"name": "water"}],
            "exercise": None,
            "medications": [],
        },
    },
    {
        "id": "apr21_breakfast_omega3",
        "transcript": "For breakfast I had toast with eggs and then took omega 3 and vitamin C.",
        "truth": {
            "foods": [{"name": "toast"}, {"name": "eggs"}],
            "exercise": None,
            "medications": [{"drug_name": "Omega-3"}, {"drug_name": "Vitamin C"}],
        },
    },
    {
        "id": "apr20_exercise_stress",
        "transcript": "오늘 30분 운동했고 스트레스 수준이 7 정도야.",
        "truth": {
            "foods": [],
            "exercise": {"minutes": 30},
            "medications": [],
        },
    },
    {
        "id": "apr19_multi_meal",
        "transcript": "For dinner I had bibimbap and kimchi jjigae, and afterwards green tea.",
        "truth": {
            "foods": [{"name": "bibimbap"}, {"name": "kimchi jjigae"}, {"name": "green tea"}],
            "exercise": None,
            "medications": [],
        },
    },
    {
        "id": "apr18_no_events",
        "transcript": "Just testing the microphone, one two three.",
        "truth": {
            "foods": [],
            "exercise": None,
            "medications": [],
        },
    },
]

# ── Gemma 4 E2B prompt ──
GEMMA_SYSTEM_PROMPT = """You extract structured health events from voice-report transcripts.
Return ONLY a JSON object with these keys:
- foods: list of {"name": str} (food or drink items mentioned as eaten/drunk)
- exercise: {"minutes": int} if any exercise mentioned, else null
- medications: list of {"drug_name": str} (supplements or medicines mentioned as taken)
No other keys. No commentary. Korean and English input both supported. Return [] or null for missing fields."""


def extract_json(text: str) -> dict:
    """Pull first JSON object out of model output."""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {"foods": [], "exercise": None, "medications": []}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"foods": [], "exercise": None, "medications": []}


def run_gemma(transcript: str) -> tuple[dict, float]:
    t0 = time.perf_counter()
    resp = httpx.post(
        LLAMA_SERVER,
        json={
            "messages": [
                {"role": "system", "content": GEMMA_SYSTEM_PROMPT},
                {"role": "user",   "content": transcript},
            ],
            "max_tokens": 256,
            "temperature": 0.0,
        },
        timeout=120,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    elapsed = time.perf_counter() - t0
    return extract_json(content), elapsed


def run_regex(transcript: str) -> tuple[dict, float]:
    """Call the current event_processor.py extractor."""
    from event_processor import EventProcessor
    proc = EventProcessor()
    t0 = time.perf_counter()
    extracted = proc.extract_from_transcript(transcript)
    elapsed = time.perf_counter() - t0
    return {
        "foods":       extracted.get("foods", []),
        "exercise":    extracted.get("exercise"),
        "medications": extracted.get("medications", []),
    }, elapsed


# ── Scoring ──
def norm(s: str) -> str:
    return (s or "").strip().lower()


def food_set(result: dict) -> set:
    return {norm(f["name"]) for f in (result.get("foods") or []) if f.get("name")}


def med_set(result: dict) -> set:
    return {norm(m["drug_name"]) for m in (result.get("medications") or []) if m.get("drug_name")}


def score(pred: dict, truth: dict) -> dict:
    # Food/med overlap is fuzzy — count as hit if predicted name contains or is contained in truth
    def fuzzy_f1(pred_set, truth_set):
        if not pred_set and not truth_set:
            return 1.0, 1.0, 1.0  # both empty = perfect
        if not pred_set or not truth_set:
            return 0.0, 0.0, 0.0
        tp = 0
        for t in truth_set:
            if any(t in p or p in t for p in pred_set):
                tp += 1
        precision = tp / len(pred_set)
        recall    = tp / len(truth_set)
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        return precision, recall, f1

    fp, fr, ff = fuzzy_f1(food_set(pred),  food_set(truth))
    mp, mr, mf = fuzzy_f1(med_set(pred),   med_set(truth))

    ex_pred  = (pred.get("exercise")  or {}).get("minutes")
    ex_truth = (truth.get("exercise") or {}).get("minutes") if truth.get("exercise") else None
    if ex_pred is None and ex_truth is None:
        ex_f1 = 1.0
    elif ex_pred is None or ex_truth is None:
        ex_f1 = 0.0
    else:
        # Treat exercise minutes as correct if within 20% of truth
        ex_f1 = 1.0 if abs(ex_pred - ex_truth) / max(ex_truth, 1) < 0.2 else 0.0

    return {"food_f1": ff, "med_f1": mf, "exercise_f1": ex_f1}


def main():
    print("=" * 70)
    print("BENCHMARK: Gemma 4 E2B  vs  event_processor.py regex extractor")
    print("=" * 70)

    # Verify Gemma server is up
    try:
        httpx.get("http://localhost:8080/health", timeout=3).raise_for_status()
        print("[OK] llama-server reachable on :8080\n")
    except Exception:
        try:
            httpx.get("http://localhost:8080/v1/models", timeout=3).raise_for_status()
            print("[OK] llama-server reachable on :8080\n")
        except Exception as e:
            print(f"[FAIL] Gemma server not reachable: {e}")
            print("Start it first:  llama-server -hf ggml-org/gemma-4-E2B-it-GGUF --port 8080")
            sys.exit(1)

    rows = []
    for sample in TEST_SET:
        print(f"-- {sample['id']}")
        print(f"   transcript: {sample['transcript']}")
        gemma_out,  gemma_t  = run_gemma(sample["transcript"])
        regex_out,  regex_t  = run_regex(sample["transcript"])
        gemma_sc = score(gemma_out,  sample["truth"])
        regex_sc = score(regex_out,  sample["truth"])
        rows.append({
            "id":       sample["id"],
            "gemma_t":  gemma_t,
            "regex_t":  regex_t,
            "gemma":    gemma_sc,
            "regex":    regex_sc,
        })
        print(f"   Gemma  {gemma_t:5.1f}s  food_f1={gemma_sc['food_f1']:.2f}  ex_f1={gemma_sc['exercise_f1']:.2f}  med_f1={gemma_sc['med_f1']:.2f}")
        print(f"   Regex  {regex_t:5.3f}s  food_f1={regex_sc['food_f1']:.2f}  ex_f1={regex_sc['exercise_f1']:.2f}  med_f1={regex_sc['med_f1']:.2f}\n")

    # Aggregate
    def avg(key_a, key_b):
        return statistics.mean(r[key_a][key_b] for r in rows)

    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"{'':20} {'Gemma 4 E2B':>15} {'Regex':>15}")
    print(f"{'Food F1':20} {avg('gemma','food_f1'):>15.3f} {avg('regex','food_f1'):>15.3f}")
    print(f"{'Exercise F1':20} {avg('gemma','exercise_f1'):>15.3f} {avg('regex','exercise_f1'):>15.3f}")
    print(f"{'Medication F1':20} {avg('gemma','med_f1'):>15.3f} {avg('regex','med_f1'):>15.3f}")
    g_times = sorted(r["gemma_t"] for r in rows)
    r_times = sorted(r["regex_t"] for r in rows)
    print(f"{'Latency p50 (s)':20} {g_times[len(g_times)//2]:>15.2f} {r_times[len(r_times)//2]:>15.4f}")
    print(f"{'Latency p95 (s)':20} {g_times[int(len(g_times)*0.95)]:>15.2f} {r_times[int(len(r_times)*0.95)]:>15.4f}")

    # Write JSON report
    report_path = PROJECT_ROOT / "docs" / "gemma_vs_regex_benchmark.json"
    report_path.write_text(json.dumps({"model": MODEL_TAG, "rows": rows}, indent=2, ensure_ascii=False))
    print(f"\nFull report -> {report_path}")


if __name__ == "__main__":
    main()
