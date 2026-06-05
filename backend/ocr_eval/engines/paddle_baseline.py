"""PaddleOCR baseline engine — reuses the PRODUCTION PaddleOCR instance + call.

To make the baseline a faithful reproduction of production (and avoid config
drift), this wraps `ocr_preprocessor._ensure_ocr()` + `_run_paddleocr_once()`
directly (read-only import — production code is NOT modified). The result is the
single full-frame primary OCR pass exactly as production runs it, which is the
fair per-engine comparison point (every other engine also gets one full-frame
pass; PaddleOCR's ROI re-OCR machinery is PaddleOCR-specific post-processing).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from .base import OCREngine, OCRResult

# Read-only import of the production OCR module (do NOT modify it).
_GW = Path(__file__).resolve().parents[2] / "glasses_watcher"
if str(_GW) not in sys.path:
    sys.path.insert(0, str(_GW))


class PaddleBaselineEngine(OCREngine):
    @property
    def name(self) -> str:
        return "PaddleOCR (baseline)"

    def initialize(self) -> bool:
        try:
            import ocr_preprocessor as _ocr  # production module, read-only
            self._ocr = _ocr
            self._model = _ocr._ensure_ocr()
            return self._model is not None
        except Exception as e:  # pragma: no cover
            print(f"[ERR] {self.name} init: {type(e).__name__}: {e}")
            return False

    def extract(self, image_path: str) -> OCRResult:
        from PIL import Image
        start = time.perf_counter()
        try:
            img = Image.open(image_path).convert("RGB")
            boxes = self._ocr._run_paddleocr_once(self._model, img)
            items = [{"text": b.get("text", ""), "confidence": b.get("confidence", 0.0),
                      "bbox": b.get("bbox", [])} for b in boxes]
            return OCRResult(self.name, items, (time.perf_counter() - start) * 1000, None)
        except Exception as e:
            return OCRResult(self.name, [], (time.perf_counter() - start) * 1000, str(e))

    @property
    def estimated_cost_usd(self) -> float:
        return 0.0
