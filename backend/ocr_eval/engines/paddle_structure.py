"""PaddleStructure (PP-Structure) engine — table/layout-aware OCR.

Specifically designed for tabular content (the KRX stock board is a table), so
this is the architecture test for f07. Output format varies across PaddleOCR
versions, so _normalize_output walks the result defensively and harvests every
text fragment it can find (table cells via HTML, plus regular text blocks).
"""
from __future__ import annotations

import re
import time

from .base import OCREngine, OCRResult


class PaddleStructureEngine(OCREngine):
    @property
    def name(self) -> str:
        return "PaddleStructure"

    def initialize(self) -> bool:
        # KNOWN LIMITATION: PP-Structure layout models support only en/ch, NOT
        # korean (lang='korean' triggers a hard sys.exit in ppocr). We init with
        # 'en' — the Hana board's currencies (EUR/USD, CAD/KRW, S&P 500) are Latin
        # and may read under an English model; Korean labels (삼성전자/현대차) will
        # NOT read. This asymmetry is itself the finding.
        try:
            from paddleocr import PPStructure
            self._engine = PPStructure(show_log=False, lang="en",
                                       use_gpu=True, layout=True, table=True)
            self._lang = "en"
            print(f"[INFO] {self.name}: korean unsupported by layout models -> using lang='en'")
            return True
        except Exception as e:
            print(f"[ERR] {self.name} init: {type(e).__name__}: {str(e)[:160]}")
            return False

    def extract(self, image_path: str) -> OCRResult:
        import numpy as np
        from PIL import Image
        start = time.perf_counter()
        try:
            img = np.array(Image.open(image_path).convert("RGB"))[:, :, ::-1]  # RGB->BGR
            raw = self._engine(img)
            items = self._normalize_output(raw)
            return OCRResult(self.name, items, (time.perf_counter() - start) * 1000, None)
        except Exception as e:
            return OCRResult(self.name, [], (time.perf_counter() - start) * 1000,
                             f"{type(e).__name__}: {str(e)[:200]}")

    @staticmethod
    def _html_texts(html: str) -> list[str]:
        # strip tags, split cells on tag boundaries
        cells = re.split(r"<[^>]+>", html or "")
        return [c.strip() for c in cells if c.strip()]

    def _normalize_output(self, raw) -> list[dict]:
        items: list[dict] = []

        def add(text, conf=0.0, bbox=None):
            t = (str(text) if text is not None else "").strip()
            if t:
                items.append({"text": t, "confidence": float(conf or 0.0), "bbox": bbox or []})

        blocks = raw if isinstance(raw, (list, tuple)) else [raw]
        for block in blocks:
            if not isinstance(block, dict):
                continue
            res = block.get("res")
            btype = block.get("type")
            if btype == "table" and isinstance(res, dict):
                if res.get("html"):
                    for t in self._html_texts(res["html"]):
                        add(t, bbox=block.get("bbox"))
                for cell in (res.get("cells") or []):
                    if isinstance(cell, dict):
                        add(cell.get("text"), cell.get("confidence"), cell.get("bbox"))
            elif isinstance(res, list):
                for line in res:
                    if isinstance(line, dict):
                        add(line.get("text") or line.get("rec_text"),
                            line.get("confidence"), line.get("text_region") or line.get("bbox"))
                    elif isinstance(line, (list, tuple)) and len(line) >= 2:
                        # (bbox, (text, conf)) shape
                        txt = line[1]
                        if isinstance(txt, (list, tuple)):
                            add(txt[0], txt[1] if len(txt) > 1 else 0.0, line[0])
                        else:
                            add(txt, 0.0, line[0])
            elif isinstance(res, dict) and res.get("html"):
                for t in self._html_texts(res["html"]):
                    add(t, bbox=block.get("bbox"))
        return items

    @property
    def estimated_cost_usd(self) -> float:
        return 0.0
