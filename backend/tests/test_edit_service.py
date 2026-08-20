"""edit_service._floor_nonpositive_amounts 점검 — `python backend/tests/test_edit_service.py`.

채팅으로 항목을 새로 추가할 때 Claude가 amount 0을 주는 버그(2026-08-19, "행 추가가 반영되지
않는다" 재현)를 서버가 항상 걸러내는지 확인한다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.allocation_service import AMOUNT_UNIT, AllocatedItem
from app.services.edit_service import EditLLMResult, _floor_nonpositive_amounts


def test_new_item_with_zero_amount_gets_floored():
    result = EditLLMResult(
        scope="quote_only",
        items=[
            AllocatedItem(category="마케팅", name="기존 항목", amount=5_000_000),
            AllocatedItem(category="마케팅", name="새로 추가한 항목", amount=0),
        ],
        changed_items=[AllocatedItem(category="마케팅", name="새로 추가한 항목", amount=0)],
    )
    _floor_nonpositive_amounts(result)
    assert result.items[1].amount == AMOUNT_UNIT, result.items
    assert result.items[0].amount == 5_000_000 - AMOUNT_UNIT, result.items
    assert result.changed_items[0].amount == AMOUNT_UNIT, result.changed_items


def test_positive_amounts_untouched():
    result = EditLLMResult(
        scope="quote_only",
        items=[
            AllocatedItem(category="마케팅", name="A", amount=1_000_000),
            AllocatedItem(category="마케팅", name="B", amount=2_000_000),
        ],
        changed_items=[],
    )
    _floor_nonpositive_amounts(result)
    assert [i.amount for i in result.items] == [1_000_000, 2_000_000]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("모두 통과")
