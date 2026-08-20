"""allocation_service.reconcile_amounts 자체 점검 — `python backend/tests/test_reconcile_amounts.py`.

채팅 수정("소계를 1,000만원으로", "1만원 단위로 떨어지게")과 항목 자동생성이 이 함수 하나로
금액을 맞추므로(2026-08-19), 여기가 깨지면 발급 금액이 통째로 어긋난다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.allocation_service import AMOUNT_UNIT, reconcile_amounts


def test_keeps_total_and_rounds_to_unit():
    # 스크린샷의 실제 실패 사례: 소계는 유지하고 세부 항목만 1만원 단위로
    before = [152900, 458200, 4888900, 152900, 152900, 5194200]
    after = reconcile_amounts(before, sum(before), AMOUNT_UNIT)
    assert sum(after) == sum(before), after
    assert all(a % AMOUNT_UNIT == 0 for a in after), after


def test_retargets_subtotal_to_10m():
    before = [152900, 458200, 4888900, 152900, 152900, 5194200]
    after = reconcile_amounts(before, 10_000_000, AMOUNT_UNIT)
    assert sum(after) == 10_000_000, after
    assert all(a % AMOUNT_UNIT == 0 for a in after), after


def test_target_not_multiple_of_unit_still_hits_target():
    after = reconcile_amounts([100, 200, 300], 1_234_567, AMOUNT_UNIT)
    assert sum(after) == 1_234_567, after
    assert min(after) >= 0, after


def test_tiny_target_skips_unit_rounding_instead_of_going_negative():
    after = reconcile_amounts([10, 10, 10], 1_000, AMOUNT_UNIT)
    assert sum(after) == 1_000, after
    assert min(after) >= 0, after


def test_no_unit_just_scales():
    after = reconcile_amounts([1, 1, 1], 100)
    assert sum(after) == 100, after


def test_empty_is_noop():
    assert reconcile_amounts([], 100, AMOUNT_UNIT) == []


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("모두 통과")