"""Confidence-thresholded hybrid: CNN first, Gemma fallback for ambiguous cases.

The CNN is fast and ~88% accurate. The Gemma vision model is slower but better
at the bottom-9 confused pairs (편육/수육/보쌈, 비빔냉면/막국수, etc.). Gating
on top-1 confidence + top-1/top-2 margin keeps Gemma calls rare.

When the CNN is unsure we don't open-end Gemma — we constrain it to choose
*from the CNN's top-K candidates*. This biases Gemma toward visually-plausible
answers and avoids hallucinated dish names.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Protocol

from PIL import Image

from food_classifier import FoodPrediction, KoreanFoodClassifier


class GemmaVisionClient(Protocol):
    """Plug-in interface. Implement against your local Gemma 2B/9B-vision,
    Gemini API, or any other VLM that can constrain output to a candidate list.

    The implementation must:
      1. Show the image to the VLM.
      2. Constrain output to one of `candidate_class_kr`.
      3. Return (chosen_class_kr, optional confidence in [0,1], optional reason).
    """

    def classify_among(
        self,
        image: Image.Image,
        candidate_class_kr: List[str],
    ) -> "GemmaResult":
        ...


@dataclass
class GemmaResult:
    class_kr: str
    confidence: Optional[float] = None
    reason: Optional[str] = None


@dataclass
class HybridResult:
    prediction: FoodPrediction
    source: str  # "cnn" | "gemma"
    cnn_top5: List[FoodPrediction] = field(default_factory=list)
    gemma_reason: Optional[str] = None


class HybridFoodClassifier:
    """Routes high-confidence CNN predictions through; falls back to Gemma for
    ambiguous ones. Tune thresholds on a small held-out set of real production
    photos before locking values.

    Defaults are calibrated against the test-set distribution observed at
    training time (median CNN top-1 confidence ~0.87 on correct samples,
    ~0.55 on incorrect samples). Adjust if your AI-glasses lighting/angle
    distribution shifts those numbers.
    """

    def __init__(
        self,
        cnn: KoreanFoodClassifier,
        gemma: Optional[GemmaVisionClient] = None,
        top1_threshold: float = 0.60,
        margin_threshold: float = 0.15,
        top_k_for_gemma: int = 5,
    ) -> None:
        self.cnn = cnn
        self.gemma = gemma
        self.top1_threshold = top1_threshold
        self.margin_threshold = margin_threshold
        self.top_k_for_gemma = top_k_for_gemma

    def _is_confident(self, top: List[FoodPrediction]) -> bool:
        if top[0].confidence < self.top1_threshold:
            return False
        if len(top) >= 2:
            margin = top[0].confidence - top[1].confidence
            if margin < self.margin_threshold:
                return False
        return True

    def predict(self, image: Image.Image) -> HybridResult:
        cnn_top = self.cnn.predict(image, top_k=max(5, self.top_k_for_gemma))

        if self._is_confident(cnn_top) or self.gemma is None:
            return HybridResult(
                prediction=cnn_top[0],
                source="cnn",
                cnn_top5=cnn_top[:5],
            )

        candidates = [p.class_kr for p in cnn_top[: self.top_k_for_gemma]]
        gemma_out = self.gemma.classify_among(image, candidates)
        # Map Gemma's chosen Korean name back to a FoodPrediction so downstream
        # code (nutrition lookup, dashboard) sees a uniform shape.
        chosen = next((p for p in cnn_top if p.class_kr == gemma_out.class_kr), None)
        if chosen is None:
            # Gemma returned a name not in the CNN's top-K — defensive fallback
            # to the CNN's top-1 with the original confidence.
            return HybridResult(
                prediction=cnn_top[0],
                source="cnn",
                cnn_top5=cnn_top[:5],
                gemma_reason="gemma_returned_unknown_class",
            )
        # Override confidence with Gemma's if it provided one.
        if gemma_out.confidence is not None:
            chosen = FoodPrediction(
                rank=1,
                class_id=chosen.class_id,
                class_kr=chosen.class_kr,
                confidence=gemma_out.confidence,
                class_en=chosen.class_en,
                category=chosen.category,
                nutrition_per_100g=chosen.nutrition_per_100g,
                allergens=chosen.allergens,
            )
        return HybridResult(
            prediction=chosen,
            source="gemma",
            cnn_top5=cnn_top[:5],
            gemma_reason=gemma_out.reason,
        )
