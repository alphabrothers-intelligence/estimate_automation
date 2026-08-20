"""채팅 수정이 사용자가 말한 금액을 그대로 지키는지 점검 — `python backend/tests/test_edit_targets.py`.

2026-08-20 사용자 지적("1000만원으로 해달랬는데 자꾸 900만원으로 맞춘다", "단가를 고쳐놔도
다른 값이 마음대로 움직인다")에 대한 회귀 테스트.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.allocation_service import AllocatedItem, reconcile_snapped_items
from app.services.edit_service import EditLLMResult, GroupTarget, _apply_amount_constraints


def _result(**kwargs) -> EditLLMResult:
    items = kwargs.pop("items")
    return EditLLMResult(
        scope="quote_only",
        items=[AllocatedItem(category=c, name=n, amount=a) for c, n, a in items],
        changed_items=[],
        **kwargs,
    )


def test_no_target_leaves_every_amount_alone():
    """예전엔 목표가 없어도 전 항목을 10만원 단위로 다시 반올림하고 차액을 최대 항목에 몰아줬다."""
    result = _result(items=[("A", "a", 3_333_333), ("B", "b", 1_234_567)])
    _apply_amount_constraints(result)
    assert [i.amount for i in result.items] == [3_333_333, 1_234_567], result.items


def test_group_targets_are_each_honoured():
    result = _result(
        items=[("런칭", "a", 5_000_000), ("런칭", "b", 4_000_000), ("그로스", "c", 3_000_000)],
        group_targets=[GroupTarget(category="런칭", amount=10_000_000)],
    )
    _apply_amount_constraints(result)
    assert sum(i.amount for i in result.items[:2]) == 10_000_000, result.items
    assert result.items[2].amount == 3_000_000, "목표 없는 구분은 안 움직여야 한다"


def test_group_targets_beat_supply_total():
    """사용자가 부른 숫자끼리 모순이면 더 구체적인 구분별 목표가 이긴다."""
    result = _result(
        items=[("런칭", "a", 5_000_000), ("그로스", "b", 5_000_000)],
        group_targets=[
            GroupTarget(category="런칭", amount=10_000_000),
            GroupTarget(category="그로스", amount=8_000_000),
        ],
        supply_total_target=30_000_000,
    )
    _apply_amount_constraints(result)
    assert [i.amount for i in result.items] == [10_000_000, 8_000_000], result.items


def test_vat_included_target_is_converted_to_supply():
    result = _result(
        items=[("A", "a", 10_000_000), ("B", "b", 5_000_000)],
        supply_total_target=30_000_000,
        target_includes_vat=True,
    )
    _apply_amount_constraints(result)
    # "VAT 포함 3000만원" -> 공급가액 목표 2727만원. 예전엔 3000만이 공급가액으로 그냥 들어가서
    # 발급본 총액이 3300만원이 됐다.
    assert sum(i.amount for i in result.items) == round(30_000_000 / 1.1), result.items


def test_locked_item_survives_residual_absorption():
    """사용자가 단가를 콕 집어 지정한 항목은 잔액 흡수에서 제외된다."""
    items = [
        # 수량 10 × 단가 55만원 — 10만원 격자에서 벗어난 값이지만 사용자가 지정했으니 그대로.
        {"name": "고정", "amount": 5_500_000, "unit_price": 550_000, "locked": True},
        {"name": "자유", "amount": 3_000_000, "unit_price": 3_000_000},
    ]
    fixed = reconcile_snapped_items(items, 10_000_000, 100_000)
    assert fixed[0]["amount"] == 5_500_000 and fixed[0]["unit_price"] == 550_000, fixed
    assert fixed[1]["amount"] == 4_500_000, "차액은 잠기지 않은 항목이 전부 흡수한다"


def test_unreachable_group_target_lands_on_nearest_without_raising():
    """수량 16 항목만 있는 구분은 한 걸음이 160만원이라 880만원에 닿지 못한다 — 가장 가까운
    값까지만 가고 예외를 던지거나 되묻지 않는다."""
    items = [
        {"name": "Wrap-Up", "amount": 4_800_000, "unit_price": 300_000},
        {"name": "액션플랜", "amount": 3_200_000, "unit_price": 200_000},
    ]
    fixed = reconcile_snapped_items(items, 8_800_000, 100_000)
    total = sum(i["amount"] for i in fixed)
    assert abs(total - 8_800_000) < 1_600_000, fixed
    assert all(i["unit_price"] % 100_000 == 0 for i in fixed), fixed


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("모두 통과")