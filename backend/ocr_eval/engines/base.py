"""Abstract OCR-engine interface for the side-by-side evaluation harness.

Every candidate engine (PaddleOCR baseline, PaddleStructure, EasyOCR, Clova)
implements this interface so the harness can run them uniformly on the same
frames and compare entity-recovery / character-accuracy / latency / cost.

This is EVALUATION-ONLY scaffolding under backend/ocr_eval/ — it never touches
the production pipeline.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class OCRResult:
    engine_name: str
    items: list[dict] = field(default_factory=list)  # [{text, confidence, bbox}, ...]
    latency_ms: float = 0.0
    error: str | None = None

    def text_blob(self) -> str:
        """All recognized text joined for substring/fuzzy matching."""
        return " || ".join(str(i.get("text", "")) for i in self.items)

    def texts(self) -> list[str]:
        return [str(i.get("text", "")) for i in self.items if i.get("text")]


class OCREngine(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def initialize(self) -> bool:
        """Load models / verify config. Return True if ready, False to skip."""
        ...

    @abstractmethod
    def extract(self, image_path: str) -> OCRResult:
        """Run OCR on one frame. ALWAYS returns an OCRResult (error set on failure)."""
        ...

    @property
    @abstractmethod
    def estimated_cost_usd(self) -> float:
        """USD per 1000 frames. 0.0 for free/local engines."""
        ...
