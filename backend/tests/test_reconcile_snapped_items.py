"""단가 스냅 후 총액 되돌리기 점검 — `python backend/tests/test_reconcile_snapped_items.py`.

2026-08-20 사용자 지적 재현: 3,000만원(VAT 별도)으로 만든 본견적서가 공급가액 32,010,000원
(총합계 35,211,000원)으로 발급되고, 마크업 +10%로 만든 비교견적서가 +99%까지 벌어졌다.
원인은 snap_unit_price가 항목마다 단가를 단위로 올리기만 하고 아무도 총액을 되돌리지 않은 것.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.allocation_service import (
    COMPARISON_AMOUNT_UNIT,
    UNIT_PRICE_UNIT,
    reconcile_snapped_items,
    snap_unit_price,
)


def _snap_all(raw, unit):
    """(공급가액, 수량×작업일) 목록을 실제 발급 경로와 같은 방식으로 스냅한다."""
    items = []
    for amount, divisor in raw:
        snapped_amount, unit_price = snap_unit_price(amount, amount / divisor, unit)
        items.append({"amount": snapped_amount, "unit_price": unit_price})
    return items


def _assert_units(items, unit):
    for item in items:
        assert item["unit_price"] >= unit and item["unit_price"] % unit == 0, item
        assert item["amount"] == round(item["unit_price"] * (item["amount"] / item["unit_price"])), item


def test_primary_lands_exactly_on_entered_total():
    # 3,000만원 입력 -> 스냅 후 3,201만원으로 부풀던 구성.
    raw = [(4_260_000, 16), (4_800_000, 16), (9_600_000, 1), (960_000, 1), (10_380_000, 1)]
    items = _snap_all(raw, UNIT_PRICE_UNIT)
    assert sum(i["amount"] for i in items) != 30_000_000  # 스냅만 하면 어긋난다(회귀 전 상태)

    fixed = reconcile_snapped_items(items, 30_000_000, UNIT_PRICE_UNIT)
    assert sum(i["amount"] for i in fixed) == 30_000_000
    _assert_units(fixed, UNIT_PRICE_UNIT)


def test_comparison_markup_stays_near_ten_percent():
    # 본견적 공급가액 3,000만원 x 마크업 1.10 = 3,300만원이 목표. 100만원 단위 스냅 때문에
    # 예전엔 두 배 가까이 뛰었다.
    raw = [(4_260_000, 16), (4_800_000, 16), (9_600_000, 1), (960_000, 1), (10_380_000, 1)]
    items = _snap_all(raw, COMPARISON_AMOUNT_UNIT)
    fixed = reconcile_snapped_items(items, 33_000_000, COMPARISON_AMOUNT_UNIT)

    total = sum(i["amount"] for i in fixed)
    assert abs(total - 33_000_000) <= COMPARISON_AMOUNT_UNIT, total
    # 100만원 단위로 못 맞추는 나머지는 10만원 단위까지만 잘게 쪼갠다.
    _assert_units(fixed, UNIT_PRICE_UNIT)


def test_pulls_down_when_snap_overshot():
    # 단가가 전부 100만원 하한으로 올라가 목표를 크게 넘긴 경우(비교견적서에서 실제로 발생).
    items = _snap_all([(300_000, 1), (400_000, 1), (500_000, 2)], COMPARISON_AMOUNT_UNIT)
    assert sum(i["amount"] for i in items) == 4_000_000

    fixed = reconcile_snapped_items(items, 1_500_000, COMPARISON_AMOUNT_UNIT)
    assert sum(i["amount"] for i in fixed) == 1_500_000
    _assert_units(fixed, UNIT_PRICE_UNIT)  # 단가가 0이나 음수로 내려가면 안 된다


def test_quantities_never_move():
    """수량은 카탈로그가 정한 업무량이라 금액을 맞추려고 건드리면 안 된다.

    한 묶음이어야 할 "주간 Wrap-Up 16회 / 주간 액션플랜 16회"가 18회/19회로 어긋난 사례
    (2026-08-20 사용자 지적) — 차액은 단가로만 흡수한다.
    """
    items = [
        {"amount": 8_000_000, "unit_price": 500_000.0, "quantity": 16.0},   # 주간 Wrap-Up
        {"amount": 4_800_000, "unit_price": 300_000.0, "quantity": 16.0},   # 주간 액션플랜
        {"amount": 9_600_000, "unit_price": 9_600_000.0, "quantity": 1.0},  # Meta 광고 실비
    ]
    fixed = reconcile_snapped_items(items, 24_500_000, UNIT_PRICE_UNIT)
    assert sum(i["amount"] for i in fixed) == 24_500_000
    assert [i["quantity"] for i in fixed] == [16.0, 16.0, 1.0]
    for item in fixed:
        assert item["unit_price"] % UNIT_PRICE_UNIT == 0, item
        assert item["amount"] == item["unit_price"] * item["quantity"], item


def test_cheap_unit_price_is_not_forced_up():
    """단가가 조정 단위(10만원)보다 싼 항목을 차액과 무관하게 끌어올리면 안 된다.

    사용성 테스트 "일반테스터 모집"은 단가 10,000원 × 수량 100이라, 한 단위(10만원)만 올려도
    금액이 1,000만원 뛴다. 하한 클램프를 무조건 걸어서 실제로 그 일이 벌어졌다(2026-08-20).
    """
    items = [
        {"amount": 2_000_000, "unit_price": 20_000.0, "quantity": 100.0},
        {"amount": 2_790_000, "unit_price": 310_000.0, "quantity": 9.0},
    ]
    fixed = reconcile_snapped_items(items, 4_810_000, UNIT_PRICE_UNIT)  # 잔액 +20,000 — 아무도 못 움직인다
    assert [i["unit_price"] for i in fixed] == [20_000.0, 310_000.0]
    assert [i["amount"] for i in fixed] == [2_000_000, 2_790_000]


def test_exact_input_is_left_untouched():
    items = [{"amount": 10_000_000, "unit_price": 10_000_000.0}]
    assert reconcile_snapped_items(items, 10_000_000, UNIT_PRICE_UNIT) == items


def test_zero_amount_items_are_skipped():
    items = [{"amount": 0, "unit_price": 0}, {"amount": 5_000_000, "unit_price": 5_000_000.0}]
    fixed = reconcile_snapped_items(items, 6_000_000, UNIT_PRICE_UNIT)
    assert [i["amount"] for i in fixed] == [0, 6_000_000]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("모두 통과")