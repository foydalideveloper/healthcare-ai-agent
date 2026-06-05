"""Metrics for OCR-engine comparison: entity recovery, char accuracy, latency.

Pure-stdlib (no new packages). Entity matching is garble-tolerant:
  - numbers compared comma/space-stripped ("1,276,000" == "1276000")
  - a token is "recovered" if it appears (normalized substring) in the OCR blob
    OR its best fuzzy similarity vs any OCR token >= FUZZY_THRESHOLD
  - char accuracy = best fuzzy similarity (1.0 = exact) for that token
"""
from __future__ import annotations

import re

FUZZY_THRESHOLD = 0.80


def _norm(s: str) -> str:
    """Lowercase, strip spaces and digit-group commas for tolerant matching."""
    s = re.sub(r"(\d),(\d)", r"\1\2", str(s))
    return re.sub(r"\s+", "", s).lower()


def _lev_ratio(a: str, b: str) -> float:
    """Levenshtein similarity ratio in [0,1] (pure python)."""
    a, b = _norm(a), _norm(b)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    la, lb = len(a), len(b)
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev = cur
    dist = prev[lb]
    return 1.0 - dist / max(la, lb)


def score_token(token: str, ocr_texts: list[str], ocr_blob_norm: str) -> tuple[bool, float]:
    """Return (recovered, best_char_accuracy) for one ground-truth token."""
    tn = _norm(token)
    if tn and tn in ocr_blob_norm:           # clean substring hit
        return True, 1.0
    best = 0.0
    for t in ocr_texts:
        r = _lev_ratio(token, t)
        if r > best:
            best = r
        # also test against sliding windows for tokens embedded in longer OCR items
        nt = _norm(t)
        if tn and len(nt) > len(tn):
            for k in range(0, len(nt) - len(tn) + 1):
                r2 = _lev_ratio(tn, nt[k:k + len(tn)])
                if r2 > best:
                    best = r2
    return (best >= FUZZY_THRESHOLD), best


def compute_metrics(result, expected: dict) -> dict:
    """Per-frame metrics for one engine's OCRResult vs the ground truth."""
    tokens = expected.get("must_contain", [])
    texts = result.texts()
    blob_norm = _norm(result.text_blob())
    per_token = {}
    recovered = 0
    acc_sum = 0.0
    for tok in tokens:
        ok, acc = score_token(tok, texts, blob_norm)
        per_token[tok] = {"recovered": ok, "char_accuracy": round(acc, 3)}
        recovered += 1 if ok else 0
        acc_sum += acc
    n = len(tokens) or 1
    return {
        "tokens_total": len(tokens),
        "tokens_recovered": recovered,
        "recovery_rate": round(recovered / n, 3),
        "mean_char_accuracy": round(acc_sum / n, 3),
        "latency_ms": round(result.latency_ms, 1),
        "error": result.error,
        "per_token": per_token,
    }
