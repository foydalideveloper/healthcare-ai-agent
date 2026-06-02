"""Unit tests for the audio-OCR cross-reference layer (audio_fact_extractor).

Pure module — no pipeline imports. Examples are drawn from the real KBS test
clip transcript (20260528144922838.mp4).

Run: {venv} -m pytest backend/app/services/tests/test_audio_fact_extractor.py -v
"""
import sys
from pathlib import Path

# Put backend/ on sys.path so `app.services...` resolves regardless of rootdir.
_BACKEND = Path(__file__).resolve().parents[3]  # .../backend
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.services.audio_fact_extractor import (  # noqa: E402
    AudioFact,
    extract_audio_facts,
    cross_reference_with_ocr,
    promote_to_value_updates,
    extract_audio_only_terms,
)

# A representative slice of the real transcript.
TRANSCRIPT = (
    "하루 새에 각각 2.7%, 9.3% 급등한 삼성전자와 SK하이닉스, 30만 전자, "
    "224만 닉스 최고가를 달성했습니다. SK하이닉스의 시가총액은 1,600조 원 "
    "가까이 불어나며 시총 1조 달러 클럽에 올랐습니다. 삼성전자에 이어 국내 "
    "기업으로는 두 번째입니다. 앞선 뉴욕 등시에서는 메모리 반도체의 세계 3위 "
    "업체인 마이크론 주가가 19% 급등하며 시총 1조 달러를 돌파했습니다. 한 "
    "글로벌 투자은행이 마이크론 목표 주가를 단번에 3배나 올리면서 반도체 투자 "
    "승리가 확산됐습니다."
)


def _find(facts, raw):
    return next((f for f in facts if f.raw_match.replace(" ", "") == raw.replace(" ", "")), None)


# ── pattern extraction ───────────────────────────────────────────────────
def test_korean_trillion_currency():
    facts = extract_audio_facts("SK하이닉스의 시가총액은 1,600조 원 가까이")
    f = _find(facts, "1,600조 원")
    assert f is not None
    assert f.unit_type == "trillion_currency"


def test_trillion_dollar_milestone():
    # Milestone branch (클럽/돌파) only fires when no 시총/시가총액 shadows it.
    facts = extract_audio_facts("메모리 반도체가 1조 달러 클럽에 올랐습니다.")
    f = _find(facts, "1조 달러")
    assert f is not None
    assert f.unit_type == "trillion_currency"
    assert f.claim_type == "milestone"


def test_trillion_market_cap_precedes_milestone():
    # Real transcript phrasing: "시총 1조 달러 클럽" -> 시총 wins -> market_cap.
    facts = extract_audio_facts("시총 1조 달러 클럽에 올랐습니다.")
    f = _find(facts, "1조 달러")
    assert f.claim_type == "market_cap"


def test_percentage_extracted():
    facts = extract_audio_facts("각각 2.7%, 9.3% 급등한")
    raws = {f.raw_match.replace(" ", "") for f in facts}
    assert "2.7%" in raws
    assert "9.3%" in raws


def test_percentage_with_gain_context():
    facts = extract_audio_facts("마이크론 주가가 19% 급등하며")
    f = _find(facts, "19%")
    assert f is not None
    assert f.claim_type == "gain"


def test_percentage_loss_context():
    facts = extract_audio_facts("주가가 5.5% 하락했습니다")
    f = _find(facts, "5.5%")
    assert f is not None
    assert f.claim_type == "loss"


def test_market_cap_detection():
    facts = extract_audio_facts("SK하이닉스의 시가총액은 1,600조 원 가까이")
    f = _find(facts, "1,600조 원")
    assert f.claim_type == "market_cap"


def test_target_price_usd():
    facts = extract_audio_facts("마이크론 목표 주가를 $535 에서 $1,625 로")
    f1 = _find(facts, "$535")
    f2 = _find(facts, "$1,625")
    assert f1 is not None and f1.unit_type == "usd" and f1.claim_type == "target_price"
    assert f2 is not None and f2.unit_type == "usd" and f2.claim_type == "target_price"


def test_year_range_contract():
    facts = extract_audio_facts("공급 계약 기간을 3년에서 5년으로 연장")
    f = _find(facts, "3년에서 5년")
    assert f is not None
    assert f.unit_type == "year_range"
    assert f.claim_type == "contract_period"


def test_multiplier_with_increase():
    facts = extract_audio_facts("목표 주가를 단번에 3배나 올리면서")
    f = _find(facts, "3배")
    assert f is not None
    assert f.unit_type == "multiplier"
    assert f.claim_type == "price_increase_multiplier"


def test_won_amount():
    facts = extract_audio_facts("삼성전자 주가가 30만 7천 원을 기록")
    won = [f for f in facts if f.unit_type == "won"]
    assert won, "expected a won-amount fact"
    assert won[0].claim_type == "price"


# ── entity detection ───────────────────────────────────────────────────────
def test_entity_detection_left_priority():
    facts = extract_audio_facts("SK하이닉스의 시가총액은 1,600조 원 가까이")
    f = _find(facts, "1,600조 원")
    assert f.entity == "SK하이닉스"


def test_entity_detection_right_fallback():
    facts = extract_audio_facts("각각 2.7% 급등한 삼성전자와")
    f = _find(facts, "2.7%")
    # No entity to the left; the entity appears to the right -> right fallback.
    assert f.entity == "삼성전자"


def test_entity_none_when_absent():
    facts = extract_audio_facts("전체 시장이 3.0% 움직였습니다")
    f = _find(facts, "3.0%")
    assert f is not None
    assert f.entity is None


# ── cross-reference with OCR ───────────────────────────────────────────────
def test_cross_ref_19_percent_in_both():
    facts = extract_audio_facts("마이크론 주가가 19% 급등")
    ocr = ["마이크론", "19%", "1조 달러"]
    also, only = cross_reference_with_ocr(facts, ocr)
    assert any(f.raw_match.replace(" ", "") == "19%" for f in also)


def test_cross_ref_1600_unique_to_audio():
    facts = extract_audio_facts("SK하이닉스의 시가총액은 1,600조 원 가까이")
    ocr = ["KOSPI 8,228.70", "KOSDAQ", "삼성전자"]
    also, only = cross_reference_with_ocr(facts, ocr)
    assert any("1,600" in f.raw_match for f in only)
    assert not any("1,600" in f.raw_match for f in also)


def test_cross_ref_empty_ocr_all_audio_only():
    facts = extract_audio_facts(TRANSCRIPT)
    also, only = cross_reference_with_ocr(facts, [])
    assert also == []
    assert len(only) == len(facts)


def test_cross_ref_no_bare_digit_collision():
    # OCR has a lone "1600" (e.g. an index value) but NOT "1600조". The audio
    # market-cap claim "1,600조 원" must NOT be treated as on-screen.
    facts = extract_audio_facts("SK하이닉스의 시가총액은 1,600조 원 가까이")
    ocr = ["KOSPI 1600", "패널 1600 포인트"]
    also, only = cross_reference_with_ocr(facts, ocr)
    assert any("1,600조" in f.raw_match for f in only)
    assert not any("1,600조" in f.raw_match for f in also)


def test_cross_ref_full_token_with_unit_matches():
    # When OCR actually shows the value with its unit, it IS cross-referenced.
    facts = extract_audio_facts("마이크론 주가가 19% 급등")
    also, only = cross_reference_with_ocr(facts, ["마이크론 19% 상승"])
    assert any(f.raw_match.replace(" ", "") == "19%" for f in also)


# ── promote to value_updates ───────────────────────────────────────────────
def test_existing_ocr_gets_video_tag():
    existing = [
        {"label": "KOSPI", "values": [{"value": "8,228.70"}], "change_count": 1},
        {"label": "SK하이닉스", "values": [{"value": "2,243,000"}], "change_count": 1},
    ]
    out = promote_to_value_updates([], existing)
    assert all(u["source"] == "video" for u in out)
    assert len(out) == 2


def test_promote_audio_to_value_updates():
    facts = extract_audio_facts("SK하이닉스의 시가총액은 1,600조 원 가까이")
    out = promote_to_value_updates(facts, [])
    audio = [u for u in out if u.get("source") == "audio"]
    assert audio, "expected an audio-sourced value_update"
    u = audio[0]
    assert u["label"] == "SK하이닉스"
    assert u["claim_type"] == "market_cap"
    assert u["values"][0]["value"].replace(" ", "") == "1,600조원".replace(" ", "")


def test_promote_skips_entityless_change():
    # Neutral context -> claim_type 'change'; no entity -> skipped per spec.
    facts = extract_audio_facts("전체 지수는 3.0% 수준입니다")
    out = promote_to_value_updates(facts, [])
    assert not any(u.get("source") == "audio" for u in out)


def test_promote_skips_currency_unit_label():
    # "1조 달러" whose only nearby entity is the unit "달러"/"원" must not become
    # a value_update row labelled with a bare currency unit.
    facts = extract_audio_facts("불어나며 시총 1조 달러 클럽에 올랐습니다")
    out = promote_to_value_updates(facts, [])
    labels = [u["label"] for u in out if u.get("source") == "audio"]
    assert "원" not in labels
    assert "달러" not in labels


def test_promote_skips_bare_multiplier_keeps_price_increase():
    # Bare "2배" (leverage) skipped; "3배" near 올리 (price hike) kept.
    bare = extract_audio_facts("레버리지 2배 ETF에 자금이 몰렸습니다")
    out_bare = promote_to_value_updates(bare, [])
    assert not any(u.get("source") == "audio" for u in out_bare)

    hike = extract_audio_facts("마이크론 목표 주가를 단번에 3배나 올리면서")
    out_hike = promote_to_value_updates(hike, [])
    assert any(u.get("claim_type") == "price_increase_multiplier"
               for u in out_hike if u.get("source") == "audio")


def test_no_dup_on_idempotent_call():
    facts = extract_audio_facts("SK하이닉스의 시가총액은 1,600조 원 가까이")
    once = promote_to_value_updates(facts, [])
    twice = promote_to_value_updates(facts, once)
    audio_once = [u for u in once if u.get("source") == "audio"]
    audio_twice = [u for u in twice if u.get("source") == "audio"]
    assert len(audio_once) == len(audio_twice)


# ── audio-only terms formatting ────────────────────────────────────────────
def test_audio_only_terms_format():
    facts = extract_audio_facts(TRANSCRIPT)
    _, only = cross_reference_with_ocr(facts, [])
    terms = extract_audio_only_terms(only)
    assert any("SK하이닉스 시가총액 1,600조 원" == t for t in terms)


def test_audio_only_terms_dedup():
    facts = extract_audio_facts("SK하이닉스 시가총액 1,600조 원. SK하이닉스 시가총액 1,600조 원.")
    terms = extract_audio_only_terms(facts)
    assert len(terms) == len(set(terms))


# ── failure modes ──────────────────────────────────────────────────────────
def test_empty_transcript():
    assert extract_audio_facts("") == []
    assert extract_audio_facts(None) == []
    assert extract_audio_facts("   ") == []


def test_whisper_garbled_text_no_crash():
    # "30만 전자" is garbled (missing tokens) — must not crash, extracts what it can.
    facts = extract_audio_facts("30만 전자 224만 닉스 최고가를 달성")
    assert isinstance(facts, list)


def test_full_transcript_smoke():
    facts = extract_audio_facts(TRANSCRIPT)
    # Should hit the 6 target patterns: 2.7%, 9.3%, 1,600조원, 1조달러, 19%, 3배.
    assert len(facts) >= 6
    types = {f.unit_type for f in facts}
    assert "trillion_currency" in types
    assert "percentage" in types
    assert "multiplier" in types
