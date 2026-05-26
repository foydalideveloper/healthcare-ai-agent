"""Tier 0 + Tier 1 CNN cascade for food photo / video recognition.

Loads two ONNX classifiers ONCE at first call:
  Tier 0: Korean food CNN  (150 classes, 88.41% TTA, MFDS-keyed)
  Tier 1: Food-101 CNN     (101 international classes, 88.15% TTA)

Public surface:
  classify_image_multi(pil_image, threshold=0.60, margin_thresh=0.15)
      -> List[CascadeResult]   # all confident hits, multi-crop, deduped per (tier, class)

  classify_image(...)        -> Optional[CascadeResult]  # max-conf, back-compat
  classify_video_multi(...)  -> List[CascadeResult]
  classify_video(...)        -> Optional[CascadeResult]  # back-compat

Multi-crop sliding window: square-ish images get one center crop (= original
behavior). Portrait/landscape get 3 crops along the long axis with overlap so
multi-dish scenes (e.g. kimbap on the side, soup in the bowl) all get seen.

The cascade follows the threshold/margin pattern from hybrid_classifier.py:
top-1 confidence must be >= threshold AND top-1/top-2 margin must be
>= margin_thresh. The Food-101 README explicitly recommends 0.60.

Free-stack architecture: NO paid LLM calls anywhere in this module.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

# food_classifier.py is a sibling module dropped in from USB
from food_classifier import KoreanFoodClassifier, FoodPrediction

_MODELS_DIR = Path(__file__).parent / "models"
_DEFAULT_THRESHOLD = 0.60
_DEFAULT_MARGIN = 0.15
_DEFAULT_FRAMES_PER_VIDEO = 6
_CROP_SIZE = 384
_RESIZE_SHORT = int(round(_CROP_SIZE * 1.143))  # 439 — matches food_classifier.preprocess

_IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

_korean_cnn: Optional[KoreanFoodClassifier] = None
_food101_cnn: Optional[KoreanFoodClassifier] = None
_load_failed_reason: Optional[str] = None


def _ensure_loaded() -> bool:
    """Lazy-load both classifiers. Returns False (and stays False) if either
    file is missing — the caller can then degrade gracefully to Gemma-only."""
    global _korean_cnn, _food101_cnn, _load_failed_reason
    if _korean_cnn is not None and _food101_cnn is not None:
        return True
    if _load_failed_reason is not None:
        return False
    try:
        if _korean_cnn is None:
            _korean_cnn = KoreanFoodClassifier(
                onnx_path=_MODELS_DIR / "korean" / "korean_food_classifier.onnx",
                class_names_path=_MODELS_DIR / "korean" / "class_names.txt",
                mapping_path=_MODELS_DIR / "korean" / "class_mapping_kr_to_en.json",
                providers=["CPUExecutionProvider"],
            )
        if _food101_cnn is None:
            _food101_cnn = KoreanFoodClassifier(
                onnx_path=_MODELS_DIR / "international" / "food101_classifier.onnx",
                class_names_path=_MODELS_DIR / "international" / "class_names.txt",
                providers=["CPUExecutionProvider"],
            )
    except Exception as e:
        _load_failed_reason = str(e)
        return False
    return True


@dataclass
class CascadeResult:
    tier: str                              # "korean" | "food101"
    class_kr: str                          # Korean dish (Tier 0) OR Food-101 raw class (Tier 1)
    class_en: Optional[str]                # English label when known
    confidence: float
    margin: float                          # top-1 minus top-2 confidence
    top5: List[FoodPrediction] = field(default_factory=list)


def _is_confident(top: List[FoodPrediction], threshold: float, margin_thresh: float) -> bool:
    if not top or top[0].confidence < threshold:
        return False
    if len(top) >= 2 and (top[0].confidence - top[1].confidence) < margin_thresh:
        return False
    return True


def _multi_crop(image: Image.Image,
                crop_size: int = _CROP_SIZE,
                resize_to: int = _RESIZE_SHORT) -> List[Image.Image]:
    """Resize shorter side to `resize_to`, then generate evenly-spaced crops
    of size `crop_size` along the long axis, centered on the short axis.

    - Square-ish images (long axis <= 1.1 * crop_size after resize): 1 center crop.
      Matches the original food_classifier.preprocess behavior pixel-for-pixel.
    - Portrait/landscape: 3 crops at offsets [0, mid, end] so every pixel falls
      in at least one crop (with ~25-50% overlap between adjacent crops).
    """
    if image.mode != "RGB":
        image = image.convert("RGB")
    w, h = image.size
    scale = resize_to / min(w, h)
    new_w, new_h = int(round(w * scale)), int(round(h * scale))
    image = image.resize((new_w, new_h), Image.BILINEAR)

    is_portrait = new_h >= new_w
    long_axis = max(new_w, new_h)
    short_axis = min(new_w, new_h)
    short_offset = max(0, (short_axis - crop_size) // 2)

    if long_axis <= int(crop_size * 1.1):
        long_offset = max(0, (long_axis - crop_size) // 2)
        if is_portrait:
            box = (short_offset, long_offset, short_offset + crop_size, long_offset + crop_size)
        else:
            box = (long_offset, short_offset, long_offset + crop_size, short_offset + crop_size)
        return [image.crop(box)]

    n = 3
    crops: List[Image.Image] = []
    for i in range(n):
        long_offset = int((long_axis - crop_size) * i / (n - 1))
        if is_portrait:
            box = (short_offset, long_offset, short_offset + crop_size, long_offset + crop_size)
        else:
            box = (long_offset, short_offset, long_offset + crop_size, short_offset + crop_size)
        crops.append(image.crop(box))
    return crops


def _to_tensor(crop_img: Image.Image) -> np.ndarray:
    """Convert a 384x384 PIL crop to ImageNet-normalized model input.
    Bypasses food_classifier.preprocess()'s built-in resize+center-crop,
    which would otherwise scale our crop up to 439 then crop back to 384."""
    arr = np.asarray(crop_img, dtype=np.float32) / 255.0
    arr = (arr - _IMAGENET_MEAN) / _IMAGENET_STD
    arr = arr.transpose(2, 0, 1)[None, ...]
    return np.ascontiguousarray(arr, dtype=np.float32)


def _classify_tensor(model: KoreanFoodClassifier, tensor: np.ndarray, top_k: int = 5) -> List[FoodPrediction]:
    """Run inference on a pre-prepared tensor; reuses the wrapper's ONNX
    session and class-enrichment helpers without going through preprocess()."""
    logits = model.session.run(None, {model.input_name: tensor})[0][0]
    probs = model._softmax(logits)
    top = np.argsort(probs)[::-1][:top_k]
    return [model._enrich(int(i), rank=r + 1, confidence=float(probs[i]))
            for r, i in enumerate(top)]


def _make_result(top: List[FoodPrediction], tier: str) -> CascadeResult:
    p = top[0]
    margin = (p.confidence - top[1].confidence) if len(top) > 1 else p.confidence
    if tier == "korean":
        return CascadeResult(
            tier="korean", class_kr=p.class_kr, class_en=p.class_en,
            confidence=p.confidence, margin=margin, top5=top,
        )
    return CascadeResult(
        tier="food101", class_kr=p.class_kr, class_en=p.class_kr.replace("_", " "),
        confidence=p.confidence, margin=margin, top5=top,
    )


def classify_image_multi(
    image: Image.Image,
    threshold: float = _DEFAULT_THRESHOLD,
    margin_thresh: float = _DEFAULT_MARGIN,
) -> List[CascadeResult]:
    """Multi-crop sliding window over both tiers.

    For each crop:
      - run Korean CNN; if confident (top-1 >= threshold AND margin >= margin_thresh),
        record as a Tier 0 hit and skip Tier 1 on this crop (Korean preferred).
      - else run Food-101 CNN; if confident, record as a Tier 1 hit.

    Across crops, dedup per (tier, class) keeping the highest-confidence
    prediction. Returns the deduped list sorted by confidence desc.
    Empty list = no confident hit on any crop on either tier.
    """
    if not _ensure_loaded():
        return []
    crops = _multi_crop(image)
    best: Dict[Tuple[str, str], CascadeResult] = {}
    for crop in crops:
        tensor = _to_tensor(crop)
        k_top = _classify_tensor(_korean_cnn, tensor, top_k=5)
        if _is_confident(k_top, threshold, margin_thresh):
            r = _make_result(k_top, "korean")
            key = (r.tier, r.class_kr)
            if key not in best or r.confidence > best[key].confidence:
                best[key] = r
            continue
        f_top = _classify_tensor(_food101_cnn, tensor, top_k=5)
        if _is_confident(f_top, threshold, margin_thresh):
            r = _make_result(f_top, "food101")
            key = (r.tier, r.class_kr)
            if key not in best or r.confidence > best[key].confidence:
                best[key] = r
    return sorted(best.values(), key=lambda r: r.confidence, reverse=True)


def classify_image(
    image: Image.Image,
    threshold: float = _DEFAULT_THRESHOLD,
    margin_thresh: float = _DEFAULT_MARGIN,
) -> Optional[CascadeResult]:
    """Backward-compat: return the highest-confidence multi-crop hit, or None."""
    results = classify_image_multi(image, threshold=threshold, margin_thresh=margin_thresh)
    return results[0] if results else None


def classify_image_path(
    image_path: Path,
    threshold: float = _DEFAULT_THRESHOLD,
    margin_thresh: float = _DEFAULT_MARGIN,
) -> Optional[CascadeResult]:
    """Convenience: open a file (HEIC support via pillow_heif if registered)
    and classify it (max-conf, single-result back-compat)."""
    img = Image.open(image_path).convert("RGB")
    return classify_image(img, threshold=threshold, margin_thresh=margin_thresh)


def debug_top1_across_crops(image: Image.Image) -> Optional[Tuple[str, str, float]]:
    """Return (tier, class_kr, confidence) for the highest-confidence
    prediction across all crops on both tiers, ignoring the threshold gate.
    Used for diagnostic logging when classify_image_multi returns empty."""
    if not _ensure_loaded():
        return None
    crops = _multi_crop(image)
    best: Optional[Tuple[str, str, float]] = None
    for crop in crops:
        tensor = _to_tensor(crop)
        k_top = _classify_tensor(_korean_cnn, tensor, top_k=1)
        if k_top:
            cand = ("korean", k_top[0].class_kr, k_top[0].confidence)
            if best is None or cand[2] > best[2]:
                best = cand
        f_top = _classify_tensor(_food101_cnn, tensor, top_k=1)
        if f_top:
            cand = ("food101", f_top[0].class_kr, f_top[0].confidence)
            if best is None or cand[2] > best[2]:
                best = cand
    return best


def classify_video_multi(
    video_path: Path,
    num_frames: int = _DEFAULT_FRAMES_PER_VIDEO,
    threshold: float = _DEFAULT_THRESHOLD,
    margin_thresh: float = _DEFAULT_MARGIN,
) -> List[CascadeResult]:
    """Sample `num_frames` frames evenly, multi-crop each, return all
    confident hits deduped per (tier, class) sorted by confidence desc."""
    if not _ensure_loaded():
        return []
    import cv2
    cap = cv2.VideoCapture(str(video_path))
    try:
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if total <= 0:
            return []
        if num_frames <= 1:
            indices = [total // 2]
        else:
            step = total / num_frames
            indices = [min(total - 1, int(step * (i + 0.5))) for i in range(num_frames)]
        best: Dict[Tuple[str, str], CascadeResult] = {}
        for idx in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if not ret:
                continue
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(rgb)
            for r in classify_image_multi(img, threshold=threshold, margin_thresh=margin_thresh):
                key = (r.tier, r.class_kr)
                if key not in best or r.confidence > best[key].confidence:
                    best[key] = r
    finally:
        cap.release()
    return sorted(best.values(), key=lambda r: r.confidence, reverse=True)


def classify_video(
    video_path: Path,
    num_frames: int = _DEFAULT_FRAMES_PER_VIDEO,
    threshold: float = _DEFAULT_THRESHOLD,
    margin_thresh: float = _DEFAULT_MARGIN,
) -> Optional[CascadeResult]:
    """Backward-compat: return the highest-confidence multi-crop hit across
    all sampled frames, or None."""
    results = classify_video_multi(video_path, num_frames=num_frames,
                                   threshold=threshold, margin_thresh=margin_thresh)
    return results[0] if results else None


def is_available() -> bool:
    """True iff both ONNX models loaded successfully (used by watcher.py
    bootstrap to set _CNN_ENABLED)."""
    return _ensure_loaded()


def load_failure_reason() -> Optional[str]:
    return _load_failed_reason
