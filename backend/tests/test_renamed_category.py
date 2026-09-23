"""대표 항목명(category)을 바꿔도 간접비 계산 규칙이 유지되는지.

화면에서 "경비 및 간접비"를 다른 이름으로 바꾸면 모듈명으로 알아보던 규칙(만원 격자,
PDF 한 줄씩 유지)이 풀렸다 — 원래 모듈명을 module에 남겨 그걸로 알아본다(2026-09-23).
실행: `python3 -m pytest tests/test_renamed_category.py`
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import chat_service, pdf_service
from app.services.quote_pricing import CLEAN_UNIT, OVERHEAD_MODULE, FormSpec, _snap_unit_for, is_overhead

RENAMED = {"category": "현장 경비", "module": OVERHEAD_MODULE, "name": "교통비", "amount": 30_000}


def test_renamed_overhead_is_still_overhead():
    assert is_overhead(RENAMED)
    assert is_overhead({"category": OVERHEAD_MODULE})  # 이름을 안 바꾼 기존 항목
    assert not is_overhead({"category": "현장 경비"})
    assert _snap_unit_for(RENAMED, FormSpec(unit_price_unit=100_000)) == CLEAN_UNIT


def test_renamed_overhead_keeps_own_rows_in_pdf():
    assert pdf_service._keeps_own_rows({"category": "현장 경비", "items": [RENAMED]})


def test_chat_rename_remembers_original_module():
    items = [{"category": OVERHEAD_MODULE, "name": "교통비", "amount": 30_000, "unit_price": 30_000}]
    result = chat_service._apply(items, {"items": [{"i": 1, "category": "현장 경비"}]}, FormSpec())[0]
    assert result[0]["category"] == "현장 경비"
    assert is_overhead(result[0])
