"""공급가액 = 단가×수량 규칙(작업일 무관, 2026-08-14 결정)이 깨지지 않는지 확인하는
최소 self-check. pytest 없이 assert만으로 검증한다.

사용법: python scripts/check_pricing.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.edit_service import reconcile_amount  # noqa: E402


def check() -> None:
    # 작업일만 바뀌어도(edited=True) amount는 단가×수량 그대로 — work_days는 인자로도 안 받는다.
    amount, unit_price = reconcile_amount(work_days=999, quantity=2, unit_price=100, amount=1, edited=True)
    assert (amount, unit_price) == (200, 100), (amount, unit_price)

    # 단가를 고치면 amount = 단가×수량으로 재계산된다.
    amount, unit_price = reconcile_amount(work_days=5, quantity=3, unit_price=1000, amount=1, edited=True)
    assert (amount, unit_price) == (3000, 1000), (amount, unit_price)

    # 수정 안 한 경우(edited=False)엔 amount는 그대로 두고 unit_price만 amount/quantity로 역산.
    amount, unit_price = reconcile_amount(work_days=5, quantity=4, unit_price=None, amount=800, edited=False)
    assert (amount, unit_price) == (800, 200), (amount, unit_price)

    # quantity가 0이면 나눗셈 대신 amount를 그대로 unit_price로 쓴다(0으로 나누기 방지).
    amount, unit_price = reconcile_amount(work_days=1, quantity=0, unit_price=None, amount=500, edited=False)
    assert (amount, unit_price) == (500, 500), (amount, unit_price)

    print("OK — 공급가액은 항상 단가×수량이며 작업일은 가격에 영향 없음")


if __name__ == "__main__":
    check()
