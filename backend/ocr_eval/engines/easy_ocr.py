"""EasyOCR engine — the critical Phase C test.

EasyOCR is the only free engine that loads Korean + English in a SINGLE model
(`Reader(['ko','en'])`), so it is the one candidate that could win BOTH the
Korean KRX board (f07) and the Latin Hana currency board (f08) at once — where
PaddleStructure was CASE gamma (great on Latin, useless on Korean).

torch-based; torch is already 2.11 in the pinned stack (no downgrade — verified
at install). Init quirk: EasyOCR's download/progress hook prints the U+2588
block char, which crashes on this cp949 Windows console -> we pass verbose=False
(models are cached after first download anyway).

EVALUATION-ONLY under backend/ocr_eval/; never touches the production pipeline.
"""
from __future__ import annotations

import time

from .base import OCREngine, OCRResult


class EasyOCREngine(OCREngine):
    @property
    def name(self) -> str:
        return "EasyOCR (ko+en)"

    def initialize(self) -> bool:
        try:
            import torch
            import easyocr
            gpu = torch.cuda.is_available()
            # verbose=False suppresses the cp949-crashing block-char progress bar.
            self._reader = easyocr.Reader(["ko", "en"], gpu=gpu, verbose=False)
            self._gpu = gpu
            print(f"[INFO] {self.name}: Reader(['ko','en']) loaded; gpu={gpu}")
            return True
        except Exception as e:
            print(f"[ERR] {self.name} init: {type(e).__name__}: {str(e)[:160]}")
            return False

    def extract(self, image_path: str) -> OCRResult:
        start = time.perf_counter()
        try:
            # detail=1 -> [(bbox, text, conf), ...]; paragraph=False keeps cells split
            raw = self._reader.readtext(image_path, detail=1, paragraph=False)
            items = []
            for entry in raw:
                # entry is (bbox, text, conf); be defensive about shape
                if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                    bbox = entry[0]
                    text = entry[1]
                    conf = entry[2] if len(entry) > 2 else 0.0
                    t = (str(text) if text is not None else "").strip()
                    if t:
                        items.append({
                            "text": t,
                            "confidence": float(conf or 0.0),
                            "bbox": [[float(x), float(y)] for x, y in bbox]
                            if isinstance(bbox, (list, tuple)) else [],
                        })
            return OCRResult(self.name, items, (time.perf_counter() - start) * 1000, None)
        except Exception as e:
            return OCRResult(self.name, [], (time.perf_counter() - start) * 1000,
                             f"{type(e).__name__}: {str(e)[:200]}")

    @property
    def estimated_cost_usd(self) -> float:
        return 0.0
