"""Korean Food CNN inference wrapper around the fine-tuned ONNX model.

Drop-in module for the watcher.py photo pipeline. Stateless after construction;
safe to reuse the instance across many predict() calls.

Files required at deploy time (must be co-located in the same directory):
  - korean_food_classifier.onnx         graph (small, ~1.3 MB)
  - korean_food_classifier.onnx.data    weights (~83 MB; auto-discovered by ORT)
  - class_names.txt                     line N = class index N
  - class_mapping_kr_to_en.json         optional metadata (en/nutrition/etc.)

Preprocessing is hard-coded to match the training script exactly:
  Resize(short side -> ceil(image_size * 1.143)) -> CenterCrop(image_size)
  -> /255 -> Normalize(ImageNet mean/std) -> CHW float32
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

import numpy as np
import onnxruntime as ort
from PIL import Image

IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


@dataclass
class FoodPrediction:
    rank: int
    class_id: int
    class_kr: str
    confidence: float
    class_en: Optional[str] = None
    category: Optional[str] = None
    nutrition_per_100g: Optional[dict] = None
    allergens: List[str] = field(default_factory=list)


class KoreanFoodClassifier:
    """ONNX-backed inference for the 150-class Korean food classifier.

    The model expects 3x384x384 ImageNet-normalized FP32 tensors. Default
    providers favor CUDA, then CPU; pass providers=["CPUExecutionProvider"]
    to force CPU. TensorRT is opt-in via the providers argument.
    """

    def __init__(
        self,
        onnx_path: str | Path,
        class_names_path: str | Path,
        mapping_path: Optional[str | Path] = None,
        image_size: int = 384,
        providers: Optional[Sequence[str]] = None,
    ) -> None:
        onnx_path = Path(onnx_path)
        if not onnx_path.exists():
            raise FileNotFoundError(f"ONNX model not found: {onnx_path}")
        # External-data weights file must sit next to the .onnx graph
        ext = onnx_path.with_suffix(onnx_path.suffix + ".data")
        if not ext.exists():
            raise FileNotFoundError(
                f"ONNX external data file missing: {ext}. The .onnx graph and "
                f".onnx.data weights must be deployed together."
            )

        if providers is None:
            providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        self.session = ort.InferenceSession(str(onnx_path), providers=list(providers))
        self.input_name = self.session.get_inputs()[0].name
        self.image_size = image_size
        self.resize_to = int(round(image_size * 1.143))

        with open(class_names_path, encoding="utf-8") as f:
            self.class_names: List[str] = [line.strip() for line in f if line.strip()]
        self.num_classes = len(self.class_names)

        self._meta: dict = {}
        if mapping_path is not None:
            with open(mapping_path, encoding="utf-8") as f:
                raw = json.load(f)
            self._meta = raw.get("classes", raw)

    # ------------------------------------------------------------------ utils
    def preprocess(self, image: Image.Image) -> np.ndarray:
        """PIL.Image -> (1, 3, H, W) FP32 ImageNet-normalized tensor."""
        if image.mode != "RGB":
            image = image.convert("RGB")
        # Match torchvision Resize(int) which scales the SHORTER side.
        w, h = image.size
        scale = self.resize_to / min(w, h)
        new_w, new_h = int(round(w * scale)), int(round(h * scale))
        image = image.resize((new_w, new_h), Image.BILINEAR)
        # Center crop
        left = (new_w - self.image_size) // 2
        top = (new_h - self.image_size) // 2
        image = image.crop((left, top, left + self.image_size, top + self.image_size))
        arr = np.asarray(image, dtype=np.float32) / 255.0
        arr = (arr - IMAGENET_MEAN) / IMAGENET_STD
        arr = arr.transpose(2, 0, 1)[None, ...]  # HWC -> CHW, add batch
        return np.ascontiguousarray(arr, dtype=np.float32)

    def _softmax(self, logits: np.ndarray) -> np.ndarray:
        # Numerically stable softmax over last axis.
        x = logits - logits.max(axis=-1, keepdims=True)
        e = np.exp(x)
        return e / e.sum(axis=-1, keepdims=True)

    def _enrich(self, class_id: int, rank: int, confidence: float) -> FoodPrediction:
        kr = self.class_names[class_id]
        meta = self._meta.get(kr, {})
        return FoodPrediction(
            rank=rank,
            class_id=class_id,
            class_kr=kr,
            confidence=confidence,
            class_en=meta.get("en"),
            category=meta.get("category"),
            nutrition_per_100g=meta.get("nutrition_per_100g"),
            allergens=meta.get("allergens", []),
        )

    # ------------------------------------------------------------------- main
    def predict(self, image: Image.Image, top_k: int = 5) -> List[FoodPrediction]:
        """Predict top-K classes for a single PIL image."""
        x = self.preprocess(image)
        logits = self.session.run(None, {self.input_name: x})[0][0]
        probs = self._softmax(logits)
        top = np.argsort(probs)[::-1][:top_k]
        return [self._enrich(int(i), rank=r + 1, confidence=float(probs[i]))
                for r, i in enumerate(top)]

    def predict_batch(
        self, images: Iterable[Image.Image], top_k: int = 5,
    ) -> List[List[FoodPrediction]]:
        """Batched prediction. All inputs are preprocessed and stacked."""
        batch = np.concatenate([self.preprocess(img) for img in images], axis=0)
        logits = self.session.run(None, {self.input_name: batch})[0]
        probs = self._softmax(logits)
        results: List[List[FoodPrediction]] = []
        for row in probs:
            top = np.argsort(row)[::-1][:top_k]
            results.append([self._enrich(int(i), rank=r + 1, confidence=float(row[i]))
                            for r, i in enumerate(top)])
        return results
