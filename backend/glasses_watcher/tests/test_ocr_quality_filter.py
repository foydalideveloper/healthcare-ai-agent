"""Unit tests for the v3.3 OCR / observation quality filter.

Run: {venv} -m pytest backend/glasses_watcher/tests/test_ocr_quality_filter.py -v
"""
import sys
from pathlib import Path

# Put backend/ on sys.path so `glasses_watcher` resolves as a namespace package
# regardless of pytest's rootdir.
_BACKEND = Path(__file__).resolve().parents[2]  # .../backend
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from glasses_watcher.ocr_quality_filter import (  # noqa: E402
    is_meaningful_ocr_item,
    is_meaningful_observation,
    is_mojibake,
    filter_ocr_items,
    filter_enumerated_observations,
)


# ── OCR item: keeps ──────────────────────────────────────────────────────
def test_keeps_digits():
    assert is_meaningful_ocr_item("8,228.70")
    assert is_meaningful_ocr_item("307,000")
    assert is_meaningful_ocr_item("+9.31%")


def test_keeps_entities():
    assert is_meaningful_ocr_item("KOSPI")
    assert is_meaningful_ocr_item("SK하이닉스")
    assert is_meaningful_ocr_item("Samsung")


def test_keeps_currency_pairs():
    assert is_meaningful_ocr_item("USD/KRW")
    assert is_meaningful_ocr_item("EUR/USD")


# ── OCR item: drops ──────────────────────────────────────────────────────
def test_drops_particles():
    assert not is_meaningful_ocr_item("의")
    assert not is_meaningful_ocr_item("를")
    assert not is_meaningful_ocr_item("는")


def test_drops_single_chars():
    assert not is_meaningful_ocr_item("A")
    assert not is_meaningful_ocr_item("ㄱ")


def test_drops_garbage():
    assert not is_meaningful_ocr_item("WiHdoWs")     # broken CamelCase
    assert not is_meaningful_ocr_item("EXAHANUGE")   # all-caps non-entity
    assert not is_meaningful_ocr_item("LLLVA")       # repeated-char run


# ── Mojibake (the v3.3 refinement) ───────────────────────────────────────
def test_drops_mojibake_replacement_char():
    # U+FFFD replacement chars (what our PaddleOCR actually emits)
    assert is_mojibake("��")
    assert not is_meaningful_ocr_item("����")
    assert not is_meaningful_ocr_item("�KOSP")  # mojibake beats partial-entity
    # ...and never meaningful even wrapped in a sentence with a digit-free token
    assert not is_meaningful_observation("The text '���' is visible on the screen.")


def test_drops_mojibake_cp1252_and_c1():
    # Classic UTF-8-read-as-cp1252 mojibake of "éè" -> "Ã©Ã¨" (Latin-1 run)
    assert is_mojibake("Ã©Ã¨")
    assert not is_meaningful_ocr_item("Ã©Ã¨")
    # C1 control character
    assert is_mojibake("KO\x9dSPI")
    assert not is_meaningful_ocr_item("KO\x9dSPI")


# ── Observation filter ───────────────────────────────────────────────────
def test_drops_noise_observations():
    assert not is_meaningful_observation("The text '의' is visible on the screen.")
    assert not is_meaningful_observation("The character '를' is visible.")
    assert not is_meaningful_observation("The text 'WiHdoWs' is visible on the screen.")


def test_keeps_factual_observations():
    assert is_meaningful_observation("Samsung Electronics priced at 307,000 won, up 2.68%.")
    assert is_meaningful_observation("Headline reads 'SK Hynix joins 1 trillion club'.")
    assert is_meaningful_observation("KOSPI index displayed at 8,228.70.")
    # noise SHAPE but meaningful quoted token → keep
    assert is_meaningful_observation("The text 'KOSPI 8,228.70' is visible on the screen.")


# ── Functional split helpers ─────────────────────────────────────────────
def test_filter_ocr_items_split():
    items = ["8,228.70", "의", "KOSPI", "LLLVA", "��", "Samsung"]
    meaningful, dropped = filter_ocr_items(items)
    assert meaningful == ["8,228.70", "KOSPI", "Samsung"]
    assert set(dropped) == {"의", "LLLVA", "��"}
    # never-empty fallback: all-garbage input still yields some meaningful
    m2, _ = filter_ocr_items(["의", "를", "는"])
    assert len(m2) >= 1


def test_filter_enumerated_observations_split():
    sentences = [
        "KOSPI index displayed at 8,228.70.",                 # keep (digit)
        "The text '의' is visible on the screen.",            # drop (particle)
        "Samsung Electronics priced at 307,000 won.",         # keep (digit)
        "The text '��' is visible on the screen.",  # drop (mojibake token)
    ]
    meaningful, dropped = filter_enumerated_observations(sentences)
    assert len(meaningful) == 2
    assert len(dropped) == 2
