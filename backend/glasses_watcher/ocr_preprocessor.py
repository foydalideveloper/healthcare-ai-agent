"""PaddleOCR-based text extraction for video frames.

Self-contained — importable even when paddleocr is not installed (degrades to
a stub that returns empty results so the parent watcher keeps working).

Public API:
    extract_text_from_frames(frames, timestamps) -> dict

Output shape (see spec PART B step 7-8):
    {
        "ocr_full_text": str,               # all unique text joined with \\n
        "per_frame": [
            {
                "frame_idx": int,
                "timestamp_sec": float,
                "text_boxes": [{"text", "confidence", "bbox": [x1,y1,x2,y2]}],
                "broadcast_mode": bool,     # KOSPI / KOSDAQ / 원 / $ detected
                "text_density": int,
            },
            ...
        ],
        "broadcast_mode_detected": bool,
        "total_unique_text_items": int,
        "ocr_latency_sec": float,
    }

Design notes:
  * Lazy init — the PaddleOCR model loads on first call (model files are
    downloaded once into %USERPROFILE%\\.paddleocr) and cached at module
    scope; subsequent calls reuse it.
  * Frame dedup via imagehash.phash (Hamming distance <= 4 => duplicate).
    A duplicate frame returns the cached OCR result without re-running.
  * Adaptive ROI: if >5 text boxes cluster in a horizontal band (broadcast
    ticker), the band is cropped and re-OCR'd at 2x upscale for higher recall.
  * Broadcast detection: any of KOSPI / KOSDAQ / 원 / $ / EUR / JPY / ticker-
    looking patterns in the detected text triggers broadcast_mode = True.
  * Pure CPU mode for now (paddlepaddle-gpu wheels don't support Blackwell
    sm_120 yet). On a Ryzen 9800X3D, 1600x1200 frame OCR is ~0.5-0.8s.
  * All print() output uses [OK] / [ERR] / [WARN] markers — no Unicode
    symbols, so Windows cp949 stdout doesn't crash.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Optional

import numpy as np

log = logging.getLogger("ocr_preprocessor")

# ── Optional import: degrade to stub if paddleocr / imagehash missing ──
try:
    from paddleocr import PaddleOCR
    import imagehash
    from PIL import Image
    OCR_AVAILABLE = True
    _import_err: Optional[str] = None
except Exception as e:  # pragma: no cover - exercised on broken envs
    OCR_AVAILABLE = False
    _import_err = f"{type(e).__name__}: {e}"
    print(f"[WARN] ocr_preprocessor: paddleocr/imagehash import failed - degrading to stub ({_import_err})")

# cv2 is used only for the Speed Win #2 motion-skip; optional, degrades to
# "never skip" if unavailable.
try:
    import cv2
except Exception:
    cv2 = None


# ── Module-scope singletons ────────────────────────────────────────────
_OCR_MODEL = None
_OCR_MODE: str = "uninit"   # "gpu" | "cpu" | "stub"
_PHASH_CACHE: dict[str, dict] = {}  # phash hex -> single-frame OCR result

# Broadcast / finance keywords that flip broadcast_mode True. Includes
# Korean (KOSPI / KOSDAQ / 원), USD ($, USD), EUR, JPY, and a regex for
# ticker-looking uppercase tokens (e.g., NVDA, AAPL, 005930).
_BROADCAST_KEYWORDS = (
    "KOSPI", "KOSDAQ", "코스피", "코스닥", "원", "$", "USD", "EUR", "JPY",
    "원/달러", "환율", "지수", "선물", "코인", "비트",
)
_TICKER_RE = re.compile(r"\b[A-Z]{3,5}\b|\b\d{6}\b")


def _ensure_ocr():
    """Lazy-load the PaddleOCR model. Idempotent. Returns the model or None."""
    global _OCR_MODEL, _OCR_MODE
    if not OCR_AVAILABLE:
        _OCR_MODE = "stub"
        return None
    if _OCR_MODEL is not None:
        return _OCR_MODEL
    # Try GPU first; fall back to CPU on any init exception (Blackwell sm_120
    # is not in PaddlePaddle 2.6's cu123 kernels — runner will OOM or crash).
    for mode, use_gpu in (("gpu", True), ("cpu", False)):
        try:
            _OCR_MODEL = PaddleOCR(
                use_angle_cls=True, lang="korean",
                use_gpu=use_gpu, show_log=False,
                # Speed Win #1: batch text-crop recognition. 16 measured ~7%
                # faster than the default 6 on dense broadcast frames; 32 was
                # slower (GPU padding overhead), so 16 is the sweet spot.
                rec_batch_num=16,
            )
            _OCR_MODE = mode
            print(f"[OK] PaddleOCR initialized in {mode.upper()} mode")
            return _OCR_MODEL
        except Exception as e:
            print(f"[WARN] PaddleOCR {mode.upper()} init failed: {type(e).__name__}: {str(e)[:160]}")
            _OCR_MODEL = None
    _OCR_MODE = "stub"
    return None


# ── Helpers ────────────────────────────────────────────────────────────

def _as_pil(frame: Any) -> Optional["Image.Image"]:
    """Convert numpy / PIL / path-like to a PIL.Image.

    Returns None if the input is unusable. Defensive — _lifelog_test passes
    PIL.Image objects already, but the public API claims numpy and we should
    handle both."""
    if frame is None:
        return None
    if hasattr(frame, "save"):  # PIL.Image
        return frame
    try:
        arr = np.asarray(frame)
    except Exception:
        return None
    if arr.ndim == 2:  # grayscale -> RGB
        arr = np.stack([arr] * 3, axis=-1)
    if arr.ndim == 3 and arr.shape[2] == 4:  # RGBA -> RGB
        arr = arr[:, :, :3]
    if arr.dtype != np.uint8:
        arr = arr.astype(np.uint8)
    try:
        return Image.fromarray(arr)
    except Exception:
        return None


def _phash(img: "Image.Image") -> str:
    return str(imagehash.phash(img))


def _frames_too_similar(frame_a, frame_b, threshold: float = 0.03) -> bool:
    """True if two same-size frames are >97% similar by mean abs pixel diff.

    Speed Win #2: lets `extract_text_from_frames` skip a fresh OCR pass on a
    near-duplicate of the last frame it actually OCR'd. Returns False on shape
    mismatch or when cv2 is unavailable — i.e. never skip when uncertain.
    """
    if frame_a is None or frame_b is None or cv2 is None:
        return False
    if getattr(frame_a, "shape", None) != getattr(frame_b, "shape", None):
        return False
    diff = cv2.absdiff(frame_a, frame_b)
    return float(diff.mean()) / 255.0 < threshold


def _detect_broadcast(text_items: list[str]) -> bool:
    blob = " ".join(text_items)
    if any(k in blob for k in _BROADCAST_KEYWORDS):
        return True
    # Ticker patterns: at least 2 distinct ticker-looking tokens
    hits = _TICKER_RE.findall(blob)
    return len(set(hits)) >= 2


# ── v2 (Fix 2): multi-panel detection + ROI re-OCR ─────────────────
# When a frame shows multiple distinct content areas (TV split-screen,
# multi-monitor, YouTube + recommended-videos sidebar, Hana Bank multi-
# currency board), DBSCAN-cluster the text-box centers, crop each cluster's
# bounding box, upscale 2x, and re-OCR. Small text (currency values, ticker
# codes) becomes readable that PaddleOCR missed at native resolution.

def _dbscan_text_boxes(centers: list[tuple[float, float]], eps: float,
                       min_samples: int) -> list[int]:
    """Minimal DBSCAN. Returns label per point (-1 = noise). No sklearn dep."""
    n = len(centers)
    labels = [-1] * n
    visited = [False] * n
    cluster_id = 0
    eps_sq = eps * eps

    def _neighbors(i: int) -> list[int]:
        xi, yi = centers[i]
        out = []
        for j in range(n):
            if j == i:
                continue
            xj, yj = centers[j]
            if (xi - xj) ** 2 + (yi - yj) ** 2 <= eps_sq:
                out.append(j)
        return out

    for i in range(n):
        if visited[i]:
            continue
        visited[i] = True
        nb = _neighbors(i)
        if len(nb) + 1 < min_samples:  # +1 includes self
            continue
        labels[i] = cluster_id
        queue = list(nb)
        while queue:
            j = queue.pop(0)
            if not visited[j]:
                visited[j] = True
                nj = _neighbors(j)
                if len(nj) + 1 >= min_samples:
                    queue.extend(nj)
            if labels[j] == -1:
                labels[j] = cluster_id
        cluster_id += 1
    return labels


def detect_panels(text_boxes: list[dict],
                  frame_shape: tuple[int, int]) -> list[tuple[int, int, int, int]]:
    """Cluster OCR text boxes into 'panels' (distinct content regions).

    Returns list of (x1, y1, x2, y2) axis-aligned panel bboxes with 5%
    padding, in image coordinates. Boxes spanning >85% of both width and
    height (i.e. whole-screen pseudo-panel) are rejected.

    `frame_shape` = (height, width).
    """
    h, w = frame_shape
    if not text_boxes or h <= 0 or w <= 0:
        return []
    # Center of each box
    centers: list[tuple[float, float]] = []
    for b in text_boxes:
        x1, y1, x2, y2 = b["bbox"]
        centers.append(((x1 + x2) / 2.0, (y1 + y2) / 2.0))
    # eps = 12% of frame diagonal
    diag = (h * h + w * w) ** 0.5
    eps = 0.12 * diag
    labels = _dbscan_text_boxes(centers, eps=eps, min_samples=4)
    # Group boxes by cluster label (>=0)
    clusters: dict[int, list[dict]] = {}
    for box, lbl in zip(text_boxes, labels):
        if lbl < 0:
            continue
        clusters.setdefault(lbl, []).append(box)
    panels: list[tuple[int, int, int, int]] = []
    for lbl, group in clusters.items():
        if len(group) < 4:
            continue
        xs1 = [b["bbox"][0] for b in group]
        ys1 = [b["bbox"][1] for b in group]
        xs2 = [b["bbox"][2] for b in group]
        ys2 = [b["bbox"][3] for b in group]
        x1, y1, x2, y2 = min(xs1), min(ys1), max(xs2), max(ys2)
        bw = x2 - x1
        bh = y2 - y1
        # Reject whole-screen clusters
        if bw >= 0.85 * w and bh >= 0.85 * h:
            continue
        # 5% padding, clipped to frame
        pad_x = int(0.05 * bw)
        pad_y = int(0.05 * bh)
        x1 = max(0, x1 - pad_x)
        y1 = max(0, y1 - pad_y)
        x2 = min(w, x2 + pad_x)
        y2 = min(h, y2 + pad_y)
        if x2 - x1 < 32 or y2 - y1 < 16:
            continue
        panels.append((int(x1), int(y1), int(x2), int(y2)))
    return panels


# C1 (2026-06-04, authorized OCR session): density override threshold. A LARGE
# panel packing this many text boxes per 100k px^2 is treated as a dense small-
# text board (Hana Bank multi-currency / KRX stock list) and promoted 2x -> 3x.
# Calibrated on the KBS clip so the boards qualify but sparse large regions and
# the wide single-row ticker do not.
_DENSE_PANEL_BOXES_PER_100KPX = 2.0


def _upscale_factor_for(bw: int, bh: int, box_count: int = 0) -> int:
    """Adaptive ROI upscale (Recall Fix a). Smaller panels get more zoom so
    tiny currency/ticker fonts (e.g. the Hana Bank board's 1,500.40 / 8,424.66)
    become legible to PaddleOCR.

        panel >= 600x400          -> 2x  (3x if DENSE — see C1 below)
        300x200 <= panel < 600x400 -> 3x
        panel < 300x200            -> 4x

    C1 density override: the "large == already readable" assumption fails for
    dense small-text financial boards. When a large panel's box density exceeds
    `_DENSE_PANEL_BOXES_PER_100KPX`, promote 2x -> 3x (not 4x — keep headroom).
    `box_count` is the number of text boxes inside the panel; 0 (default) keeps
    the original size-only behaviour for any caller that doesn't pass it.
    """
    if bw >= 600 and bh >= 400:
        density = box_count / (max(1, bw * bh) / 100000.0)
        return 3 if density >= _DENSE_PANEL_BOXES_PER_100KPX else 2
    if bw >= 300 and bh >= 200:
        return 3
    return 4


def reocr_panel(model, img: "Image.Image",
                bbox: tuple[int, int, int, int],
                box_count: int = 0) -> list[dict]:
    """Crop the image to bbox, adaptively upscale, OCR, translate boxes back
    to the original frame's coordinate space. Upscale factor scales inversely
    with panel size and (C1) text density (see _upscale_factor_for); capped so
    the upscaled crop width stays <= 4000px to bound GPU memory. `box_count` is
    the number of text boxes inside the panel (0 = size-only legacy behaviour)."""
    x1, y1, x2, y2 = bbox
    if x2 <= x1 or y2 <= y1:
        return []
    crop = img.crop((x1, y1, x2, y2))
    if crop.width < 8 or crop.height < 8:
        return []
    factor = _upscale_factor_for(x2 - x1, y2 - y1, box_count)
    # Cap upscaled width at 4000px (INTER_CUBIC-equivalent BICUBIC resize).
    factor = max(1, min(factor, 4000 // max(1, crop.width)))
    up = (crop.resize((crop.width * factor, crop.height * factor), Image.BICUBIC)
          if factor > 1 else crop)
    try:
        boxes = _run_paddleocr_once(model, up)
    except Exception:
        return []
    # Translate: divide by the actual factor to undo upscale, then add offset.
    out: list[dict] = []
    for b in boxes:
        bx1, by1, bx2, by2 = b["bbox"]
        out.append({
            "text": b["text"],
            "confidence": b["confidence"],
            "bbox": [
                int(bx1 / factor) + x1, int(by1 / factor) + y1,
                int(bx2 / factor) + x1, int(by2 / factor) + y1,
            ],
        })
    return out


def _ticker_band_crop(img: "Image.Image", boxes: list[dict]) -> Optional["Image.Image"]:
    """If >5 boxes cluster in a horizontal band (within 60 px y-range), return
    a 2x-upscaled crop of that band for higher-recall second pass.

    Returns None if no qualifying cluster found.
    """
    if len(boxes) <= 5:
        return None
    # Bucket by y-center in 60 px buckets, find densest bucket
    buckets: dict[int, list[dict]] = {}
    for b in boxes:
        x1, y1, x2, y2 = b["bbox"]
        yc = (y1 + y2) / 2
        bucket = int(yc // 60)
        buckets.setdefault(bucket, []).append(b)
    biggest = max(buckets.values(), key=len)
    if len(biggest) <= 5:
        return None
    y1s = [b["bbox"][1] for b in biggest]
    y2s = [b["bbox"][3] for b in biggest]
    band_top = max(0, int(min(y1s) - 8))
    band_bot = min(img.height, int(max(y2s) + 8))
    if band_bot - band_top < 16:
        return None
    crop = img.crop((0, band_top, img.width, band_bot))
    return crop.resize((crop.width * 2, crop.height * 2), Image.BICUBIC)


def _run_paddleocr_once(model, img: "Image.Image") -> list[dict]:
    """Run PaddleOCR on a single PIL image. Returns normalised text boxes.

    Tries the call once; on OOM / CUDA error, callers should swallow + retry
    in CPU-only mode (we already start in CPU when GPU init failed)."""
    arr = np.array(img)
    raw = model.ocr(arr, cls=True)
    out: list[dict] = []
    if not raw or not raw[0]:
        return out
    for item in raw[0]:
        if not item or len(item) < 2:
            continue
        bbox_pts, (text, conf) = item[0], item[1]
        if not text:
            continue
        # bbox_pts is 4 (x, y) corners; convert to axis-aligned x1y1x2y2.
        xs = [int(p[0]) for p in bbox_pts]
        ys = [int(p[1]) for p in bbox_pts]
        out.append({
            "text": str(text),
            "confidence": float(conf),
            "bbox": [min(xs), min(ys), max(xs), max(ys)],
        })
    return out


# ── Public API ─────────────────────────────────────────────────────────

def extract_text_from_frames(
    frames: list[Any],
    timestamps: list[float],
) -> dict:
    """Run PaddleOCR over a list of frames; dedupe + adaptive ROI re-scan.

    `frames` may be PIL.Image, numpy ndarray, or anything `np.asarray` accepts.
    `timestamps` aligns with frames (same length); used only for the output.

    Always returns a well-formed dict (never raises). On total failure
    (PaddleOCR not installed / model init failed), returns an empty schema
    with `ocr_latency_sec=0` and a single per-frame stub per frame.
    """
    t_start = time.perf_counter()
    n = len(frames)

    # Empty input → empty schema, no error
    if n == 0:
        return _empty_result(0.0)

    if len(timestamps) < n:
        timestamps = list(timestamps) + [0.0] * (n - len(timestamps))

    model = _ensure_ocr()
    if model is None:
        # Stub: per-frame entries with empty text_boxes
        per_frame = [
            {"frame_idx": i, "timestamp_sec": float(timestamps[i]),
             "text_boxes": [], "broadcast_mode": False, "text_density": 0}
            for i in range(n)
        ]
        return {
            "ocr_full_text": "",
            "per_frame": per_frame,
            "broadcast_mode_detected": False,
            "total_unique_text_items": 0,
            "ocr_latency_sec": 0.0,
        }

    per_frame: list[dict] = []
    seen_text: set[str] = set()
    any_broadcast = False
    # Speed Win #1 instrumentation: split primary OCR vs re-OCR (ROI) cost.
    total_primary_ms = 0.0
    total_reocr_ms = 0.0
    frames_ocrd = 0

    # Speed Win #2: motion-based frame skip. A frame >97% pixel-identical to
    # the last frame we actually resolved reuses its boxes instead of a fresh
    # OCR pass. Complements the exact-phash cache (which only catches byte-
    # identical phashes — near-duplicates with scrolling tickers slip past it).
    # At least 10 evenly-spaced frames are ALWAYS OCR'd so a small-panel value
    # change (under the 3% whole-frame threshold) still gets sampled.
    last_unique_arr = None
    last_unique_entry = None
    frames_skipped_by_motion = 0
    # Always OCR at least every other frame within this call so a value that
    # changes for >=1 frame is still sampled even if its whole-frame pixel
    # delta falls under the 3% motion threshold. (extract_text_from_frames is
    # called per ~10-frame group, so a fixed min-10 floor would force-OCR the
    # whole group; an every-other floor leaves room for near-dupe skips.)
    mandatory = {i for i in range(n) if i % 2 == 0}

    for i in range(n):
        img = _as_pil(frames[i])
        if img is None:
            per_frame.append({
                "frame_idx": i, "timestamp_sec": float(timestamps[i]),
                "text_boxes": [], "broadcast_mode": False, "text_density": 0,
            })
            continue

        t0 = time.perf_counter()

        # Speed Win #2: motion skip (cheapest gate, runs before phash + OCR).
        cur_arr = np.asarray(img)
        if (i not in mandatory and last_unique_entry is not None
                and _frames_too_similar(cur_arr, last_unique_arr)):
            src = last_unique_entry
            entry = {
                "frame_idx": i, "timestamp_sec": float(timestamps[i]),
                "text_boxes": list(src["text_boxes"]),
                "broadcast_mode": src["broadcast_mode"],
                "text_density": src["text_density"],
                "panels_detected": list(src.get("panels_detected", [])),
                "panel_reocr_items_added": src.get("panel_reocr_items_added", 0),
            }
            per_frame.append(entry)
            for b in src["text_boxes"]:
                seen_text.add(b["text"])
            if src["broadcast_mode"]:
                any_broadcast = True
            frames_skipped_by_motion += 1
            ms = int((time.perf_counter() - t0) * 1000)
            print(f"[OK] OCR frame {i+1}/{n} {len(src['text_boxes'])} boxes (motion skip) {ms}ms")
            continue

        # Dedup via phash — skip OCR if we've already processed an identical-
        # enough frame in this batch.
        try:
            ph = _phash(img)
        except Exception:
            ph = None

        if ph and ph in _PHASH_CACHE:
            cached = _PHASH_CACHE[ph]
            entry = {
                "frame_idx": i, "timestamp_sec": float(timestamps[i]),
                "text_boxes": list(cached["text_boxes"]),
                "broadcast_mode": cached["broadcast_mode"],
                "text_density": cached["text_density"],
                "panels_detected": list(cached.get("panels_detected", [])),
                "panel_reocr_items_added": cached.get("panel_reocr_items_added", 0),
            }
            per_frame.append(entry)
            for b in cached["text_boxes"]:
                seen_text.add(b["text"])
            if cached["broadcast_mode"]:
                any_broadcast = True
            # A phash-cache hit still has valid boxes → use it as the motion
            # baseline so later near-duplicates can skip against it too.
            last_unique_arr = cur_arr
            last_unique_entry = entry
            ms = int((time.perf_counter() - t0) * 1000)
            print(f"[OK] OCR frame {i+1}/{n} {len(cached['text_boxes'])} boxes (cache hit) {ms}ms")
            continue

        # Real OCR pass (primary, full-frame)
        _tp = time.perf_counter()
        try:
            boxes = _run_paddleocr_once(model, img)
        except Exception as e:
            # GPU OOM mid-batch: retry once in CPU. _ensure_ocr already
            # tries CPU on init, so if we're here in CPU mode, just log + skip.
            print(f"[ERR] OCR frame {i+1}/{n} raised {type(e).__name__}: {str(e)[:160]}")
            boxes = []
        total_primary_ms += (time.perf_counter() - _tp) * 1000
        frames_ocrd += 1
        _tr = time.perf_counter()

        # Adaptive ROI re-scan for ticker bands (legacy single-band heuristic).
        # NOTE: kept running unconditionally — it uniquely catches items the
        # multi-panel pass misses on dense frames (verified: gating it behind
        # "no multi-panel" dropped the screenshot ground-truth pool 144->124).
        if len(boxes) > 5:
            try:
                band = _ticker_band_crop(img, boxes)
                if band is not None:
                    extra = _run_paddleocr_once(model, band)
                    existing_text = {b["text"] for b in boxes}
                    for x in extra:
                        if x["text"] not in existing_text:
                            boxes.append(x)
            except Exception as e:
                print(f"[WARN] OCR frame {i+1}/{n} band re-scan failed: {type(e).__name__}: {str(e)[:120]}")

        # ── Fix 2: multi-panel ROI re-OCR ──
        # When a frame is dense (>15 boxes) AND DBSCAN finds >=2 distinct
        # panels, crop each panel at 2x upscale and re-OCR. Catches small
        # text in side panels (Hana Bank board, YouTube sidebar) that the
        # native-resolution pass misses.
        panels: list[tuple[int, int, int, int]] = []
        panel_added = 0
        panel_upscale_factors: list[int] = []
        if len(boxes) > 15:
            try:
                panels = detect_panels(boxes, (img.height, img.width))
                if len(panels) >= 2:
                    # C1: count text boxes whose center falls inside each panel so
                    # _upscale_factor_for can promote dense large boards 2x -> 3x.
                    def _boxes_in(p: tuple) -> int:
                        px1, py1, px2, py2 = p
                        return sum(
                            1 for b in boxes
                            if px1 <= (b["bbox"][0] + b["bbox"][2]) / 2 <= px2
                            and py1 <= (b["bbox"][1] + b["bbox"][3]) / 2 <= py2
                        )
                    panel_counts = [_boxes_in(p) for p in panels]
                    panel_upscale_factors = [
                        _upscale_factor_for(p[2] - p[0], p[3] - p[1], c)
                        for p, c in zip(panels, panel_counts)
                    ]
                    existing_pairs = [(b["text"], (b["bbox"][1] + b["bbox"][3]) // 2) for b in boxes]
                    for p, c in zip(panels, panel_counts):
                        extra = reocr_panel(model, img, p, c)
                        for x in extra:
                            yc = (x["bbox"][1] + x["bbox"][3]) // 2
                            # Dedup: same text within +/- 30 px y-band = duplicate
                            is_dup = any(
                                t == x["text"] and abs(y - yc) <= 30
                                for t, y in existing_pairs
                            )
                            if not is_dup:
                                boxes.append(x)
                                existing_pairs.append((x["text"], yc))
                                panel_added += 1
            except Exception as e:
                print(f"[WARN] OCR frame {i+1}/{n} panel re-scan failed: {type(e).__name__}: {str(e)[:120]}")

        total_reocr_ms += (time.perf_counter() - _tr) * 1000

        text_items = [b["text"] for b in boxes]
        broadcast = _detect_broadcast(text_items)
        if broadcast:
            any_broadcast = True

        entry = {
            "frame_idx": i, "timestamp_sec": float(timestamps[i]),
            "text_boxes": boxes,
            "broadcast_mode": broadcast,
            "text_density": sum(len(b["text"]) for b in boxes),
            "panels_detected": panels,
            "panel_reocr_items_added": panel_added,
            "panel_upscale_factors": panel_upscale_factors,
        }
        per_frame.append(entry)
        for b in boxes:
            seen_text.add(b["text"])

        if ph:
            _PHASH_CACHE[ph] = entry

        # Freshly-OCR'd frame becomes the motion baseline for Speed Win #2.
        last_unique_arr = cur_arr
        last_unique_entry = entry

        ms = int((time.perf_counter() - t0) * 1000)
        print(f"[OK] OCR frame {i+1}/{n} extracted {len(boxes)} text boxes in {ms}ms")

    # Order seen_text by first occurrence per frame so the joined dump is
    # somewhat narrative-stable (not random set order).
    ordered_text: list[str] = []
    seen = set()
    for f in per_frame:
        for b in f["text_boxes"]:
            t = b["text"]
            if t not in seen:
                ordered_text.append(t)
                seen.add(t)

    elapsed = round(time.perf_counter() - t_start, 3)
    if frames_ocrd or frames_skipped_by_motion:
        print(f"[SPEED] OCR primary {total_primary_ms/1000:.1f}s + reocr "
              f"{total_reocr_ms/1000:.1f}s over {frames_ocrd} frame(s); "
              f"motion-skipped {frames_skipped_by_motion}")
    return {
        "ocr_full_text": "\n".join(ordered_text),
        "per_frame": per_frame,
        "broadcast_mode_detected": any_broadcast,
        "total_unique_text_items": len(ordered_text),
        "ocr_latency_sec": elapsed,
        "ocr_mode": _OCR_MODE,
        "ocr_primary_sec": round(total_primary_ms / 1000, 3),
        "ocr_reocr_sec": round(total_reocr_ms / 1000, 3),
        "frames_skipped_by_motion": frames_skipped_by_motion,
    }


def _empty_result(elapsed_sec: float) -> dict:
    return {
        "ocr_full_text": "",
        "per_frame": [],
        "broadcast_mode_detected": False,
        "total_unique_text_items": 0,
        "ocr_latency_sec": elapsed_sec,
        "ocr_mode": _OCR_MODE,
    }


def reset_phash_cache() -> None:
    """Test/utility — clear the dedup cache between unrelated batches."""
    _PHASH_CACHE.clear()


# ── v2 (Fix 3): value change detection across frames ───────────────
# When the same metric (e.g. "SK하이닉스") appears with different numeric
# values across frames in the same chunk, treat it as an UPDATE rather
# than a duplicate. Surfaced into combined_analysis.value_updates in the
# prompt + DB.

_LABEL_RE = re.compile(r"[ㄱ-힣]{2,}|[A-Z][A-Za-z가-힣]{2,}")
_VALUE_RE = re.compile(
    r"(?:[+\-▲▼]?\s*[\d][\d,]*(?:\.\d+)?\s*(?:%|원|\$|EUR|JPY|KRW|USD)?)"
    r"|(?:\d+\s*(?:조|억|만|천)\s*)+\d*"
)
_KOREAN_UNIT_SCALES = {"조": 10**12, "억": 10**8, "만": 10**4, "천": 10**3}


def normalize_korean_numeral(text: str) -> Optional[int]:
    """Parse mixed-Korean numerals into an integer. Returns None on failure.

    Examples:
      "30만 7천 원"      -> 307000
      "224만 3천 원"     -> 2243000
      "1조"             -> 1000000000000
      "1조 6천억"        -> 1600000000000
      "307,000원"       -> 307000
      "₩2,243,000"      -> 2243000
    """
    if not text:
        return None
    s = text.strip().replace(",", "").replace("₩", "").replace("$", "").replace("원", "")
    s = s.strip()
    # Pure-digit fast path
    if s.isdigit():
        return int(s)
    # Korean-unit composite
    total = 0
    cur_num = ""
    last_scale = 10**16  # for ordering check
    saw_unit = False
    for ch in s:
        if ch.isdigit():
            cur_num += ch
        elif ch in _KOREAN_UNIT_SCALES:
            saw_unit = True
            n = int(cur_num) if cur_num else 1
            scale = _KOREAN_UNIT_SCALES[ch]
            if scale >= last_scale:  # units must descend (조>억>만>천)
                return None
            total += n * scale
            last_scale = scale
            cur_num = ""
        elif ch.isspace():
            continue
        else:
            return None
    if cur_num:
        total += int(cur_num)
    return total if saw_unit and total > 0 else None


def _values_equal_loose(a: str, b: str) -> bool:
    """True if a and b represent the same numeric value (loose comparison).
    Handles comma/no-comma, Korean numerals, percentage strings, currency."""
    if a == b:
        return True
    pa = normalize_korean_numeral(a)
    pb = normalize_korean_numeral(b)
    if pa is not None and pb is not None:
        return pa == pb
    # Fallback: strip non-digit-dot, compare numerically
    aa = re.sub(r"[^\d.]", "", a)
    bb = re.sub(r"[^\d.]", "", b)
    if aa and bb:
        try:
            return abs(float(aa) - float(bb)) < 1e-6
        except ValueError:
            return False
    return False


def _value_pct_change(a: str, b: str) -> Optional[float]:
    """Approximate |Δ|/avg as a fraction. None if non-numeric."""
    pa = normalize_korean_numeral(a) if a else None
    pb = normalize_korean_numeral(b) if b else None
    if pa is None:
        try:
            pa = float(re.sub(r"[^\d.]", "", a))
        except (ValueError, TypeError):
            return None
    if pb is None:
        try:
            pb = float(re.sub(r"[^\d.]", "", b))
        except (ValueError, TypeError):
            return None
    if not pa or not pb:
        return None
    return abs(pa - pb) / max(abs(pa), abs(pb))


def _normalize_label(s: str) -> str:
    return re.sub(r"\s+", "", s).lower()


def detect_value_changes(per_frame_results: list[dict]) -> list[dict]:
    """Across all per-frame OCR results, find metrics whose displayed value
    changed during the recording window.

    Returns list of {label, values:[{value,frame_idx,timestamp_sec}], change_count,
    first_seen_sec, last_seen_sec}.

    Pairing algorithm: a "label box" is one matching _LABEL_RE; a "value box"
    matches _VALUE_RE. Boxes A and B are considered a pair when they're on the
    same row (y-center within ±30 px) AND within 150 px horizontally.

    A change is reported when:
      * same normalized label appears in >=2 frames
      * with >=2 distinct numeric values (loose-equal aware)
      * time delta between observations >= 3.0 sec (filters OCR jitter)
      * %change >= 2% (filters OCR misread noise like 2,328,000 vs 2,329,000)
    """
    pairs: list[tuple[str, str, int, float]] = []  # (label, value, frame_idx, ts)
    for pf in per_frame_results:
        ts = float(pf.get("timestamp_sec", 0))
        fi = int(pf.get("frame_idx", 0))
        boxes = pf.get("text_boxes", [])
        # Annotate each box with center coords for fast pairing
        ann = []
        for b in boxes:
            x1, y1, x2, y2 = b["bbox"]
            ann.append({
                "text": b["text"],
                "cx": (x1 + x2) / 2.0,
                "cy": (y1 + y2) / 2.0,
                "x1": x1, "x2": x2,
            })
        for a in ann:
            if not _LABEL_RE.search(a["text"]):
                continue
            # Find nearest value-box on same row to the right (or close left)
            best_b = None
            best_dist = float("inf")
            for b in ann:
                if a is b:
                    continue
                if not _VALUE_RE.fullmatch(b["text"].strip()):
                    continue
                if abs(a["cy"] - b["cy"]) > 30:
                    continue
                dx = abs(a["cx"] - b["cx"])
                if dx > 150:
                    continue
                if dx < best_dist:
                    best_dist = dx
                    best_b = b
            if best_b is not None:
                pairs.append((a["text"], best_b["text"], fi, ts))

    if not pairs:
        return []

    # Group by normalized label
    by_label: dict[str, list[tuple[str, int, float]]] = {}
    for label, value, fi, ts in pairs:
        by_label.setdefault(_normalize_label(label), []).append((value, fi, ts))

    out: list[dict] = []
    for nlabel, obs in by_label.items():
        if len(obs) < 2:
            continue
        # Order by timestamp
        obs.sort(key=lambda x: x[2])
        # Find first observation
        first_value, first_fi, first_ts = obs[0]
        distinct_values: list[tuple[str, int, float]] = [(first_value, first_fi, first_ts)]
        for value, fi, ts in obs[1:]:
            prev = distinct_values[-1]
            prev_value, prev_ts = prev[0], prev[2]
            if _values_equal_loose(prev_value, value):
                continue
            if ts - prev_ts < 3.0:  # too close in time -> OCR jitter
                continue
            pct = _value_pct_change(prev_value, value)
            if pct is not None and pct < 0.02:  # <2% change -> noise
                continue
            distinct_values.append((value, fi, ts))
        if len(distinct_values) < 2:
            continue
        # Pretty label: use the first observation's raw text (preserves Korean)
        original_label = next((p[0] for p in pairs if _normalize_label(p[0]) == nlabel), nlabel)
        out.append({
            "label": original_label,
            "values": [
                {"value": v, "frame_idx": fi, "timestamp_sec": round(ts, 1)}
                for (v, fi, ts) in distinct_values
            ],
            "change_count": len(distinct_values),
            "first_seen_sec": round(distinct_values[0][2], 1),
            "last_seen_sec": round(distinct_values[-1][2], 1),
        })
    return out


# ── v2 (Fix 1): distinct-frame picker for VLM input subset ─────────────
# When we OCR 60 frames at 1fps for a broadcast, the VLM only needs the
# 20 most visually-distinct frames as image input (sending all 60 would
# blow the context budget). Greedy max-min Hamming distance over phashes.

def pick_distinct_frames_phash(frames: list[Any], target_count: int) -> list[int]:
    """Return indices of `target_count` most visually-distinct frames.

    Greedy max-min: start from frame 0, then repeatedly add the frame whose
    minimum Hamming distance to the already-picked set is the largest.

    Failure-safe fallbacks:
      * len(frames) <= target_count -> return all indices in order
      * phash fails on a frame -> that frame's distance defaults to 0 (low
        priority but still eligible)
      * if the maximum pairwise distance across the whole pool is below
        threshold (8 / 64 bits ≈ 12% — near-identical pool), fall back to
        evenly-spaced indices so we still cover the timeline.
    """
    n = len(frames)
    if n <= target_count:
        return list(range(n))
    if not OCR_AVAILABLE:
        # imagehash unavailable -> even spacing
        return [int(round(i * (n - 1) / (target_count - 1))) for i in range(target_count)]

    # Compute phashes (int form for fast XOR-popcount distance)
    hashes: list[Optional[int]] = []
    for f in frames:
        img = _as_pil(f)
        if img is None:
            hashes.append(None)
            continue
        try:
            hashes.append(int(str(_phash(img)), 16))
        except Exception:
            hashes.append(None)

    def _ham(a: Optional[int], b: Optional[int]) -> int:
        if a is None or b is None:
            return 0
        return bin(a ^ b).count("1")

    # Quick spread check on a sample — if max-pairwise distance is tiny,
    # phash picking adds nothing over even spacing.
    sample_idxs = list(range(0, n, max(1, n // 12)))[:12]
    spread = 0
    for i in range(len(sample_idxs)):
        for j in range(i + 1, len(sample_idxs)):
            spread = max(spread, _ham(hashes[sample_idxs[i]], hashes[sample_idxs[j]]))
    if spread < 8:  # 8/64 = ~12% — near-identical pool
        return [int(round(i * (n - 1) / (target_count - 1))) for i in range(target_count)]

    selected = [0]
    # Cache: min distance from each unpicked frame to current selected set
    min_dist = [_ham(hashes[0], hashes[j]) for j in range(n)]
    min_dist[0] = -1  # mark selected

    while len(selected) < target_count:
        # Pick the unpicked frame with the largest min-dist
        best_i, best_d = -1, -1
        for j in range(n):
            if min_dist[j] > best_d:
                best_d = min_dist[j]
                best_i = j
        if best_i < 0:
            break
        selected.append(best_i)
        min_dist[best_i] = -1
        # Update min-dist with the newly-selected frame
        for j in range(n):
            if min_dist[j] >= 0:
                d = _ham(hashes[best_i], hashes[j])
                if d < min_dist[j]:
                    min_dist[j] = d

    selected.sort()  # return in temporal order
    return selected
