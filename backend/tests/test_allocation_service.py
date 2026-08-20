"""allocation_service._split_amount_weighted 점검 — `python backend/tests/test_allocation_service.py`.

여러 모듈을 조합할 때 균등분배 대신 module_weight(참고 견적서 실제 비중)를 반영하는지,
weight가 없는 모듈이 섞이면 균등분배로 안전하게 폴백하는지 확인한다(2026-08-19).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.catalog import CatalogItem
from app.services.allocation_service import AMOUNT_UNIT, _split_amount_weighted


def _group(module_name, weight):
    return (module_name, [CatalogItem(module_name=module_name, item_name="x", is_required=True, module_weight=weight)])


def test_weighted_split_matches_real_proportions():
    groups = [_group("런칭 마케팅", 5_300_000), _group("그로스해킹", 12_800_000), _group("퍼포먼스", 9_900_000)]
    shares = _split_amount_weighted(28_000_000, groups)
    assert sum(shares) == 28_000_000, shares
    assert all(s % AMOUNT_UNIT == 0 for s in shares), shares
    # 순서대로 런칭/그로스/퍼포먼스 비중이 유지돼야 한다(균등분배였다면 셋 다 9,333,333 근처가 됨).
    assert shares[1] > shares[2] > shares[0], shares


def test_missing_weight_falls_back_to_even_split():
    groups = [_group("A", 1_000_000), _group("B", None)]
    shares = _split_amount_weighted(10_000_000, groups)
    assert shares == [5_000_000, 5_000_000], shares


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("모두 통과")
