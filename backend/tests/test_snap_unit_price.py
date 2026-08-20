"""단가 10만원 단위 스냅 자체 점검 — `python backend/tests/test_snap_unit_price.py`.

항목 자동생성·채팅 수정·비교견적 동기화가 모두 allocation_service.snap_unit_price를 거쳐
단가를 떨어뜨린다(2026-08-20). 여기가 깨지면 발급본에 266,250원 같은 단가가 다시 나온다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.allocation_service import (
    COMPARISON_AMOUNT_UNIT,
    UNIT_PRICE_UNIT,
    amount_unit_for,
    grand_total,
    reconcile_amounts,
    snap_unit_price,
)


def test_quantity_16_no_longer_produces_266250():
    # 실제 실패 사례: 4,260,000원을 수량 16으로 나눠 단가가 266,250원이 됐다.
    amount, unit_price = snap_unit_price(4_260_000, 4_260_000 / 16)
    assert unit_price % UNIT_PRICE_UNIT == 0, unit_price
    assert amount == unit_price * 16, (amount, unit_price)


def test_vat_included_remainder_is_absorbed_into_round_unit():
    # 3,000만원 VAT 포함 -> 공급가액 27,272,727원처럼 1원 단위가 남던 값도 떨어져야 한다.
    amount, unit_price = snap_unit_price(6_222_727, 6_222_727.0)
    assert unit_price % UNIT_PRICE_UNIT == 0 and amount % UNIT_PRICE_UNIT == 0, (amount, unit_price)


def test_sample_pdf_prices_survive_unchanged():
    # 사용자가 정답으로 제시한 참고 견적서의 값은 이미 단위에 맞으므로 그대로여야 한다.
    for unit_price, quantity in [(500_000, 16), (300_000, 16), (100_000, 1), (9_000_000, 1)]:
        amount, snapped = snap_unit_price(unit_price * quantity, unit_price)
        assert (amount, snapped) == (unit_price * quantity, float(unit_price))


def test_tiny_amount_gets_floored_to_one_unit_not_zero():
    amount, unit_price = snap_unit_price(30_000, 30_000.0)
    assert unit_price == UNIT_PRICE_UNIT and amount == UNIT_PRICE_UNIT, (amount, unit_price)


def test_missing_unit_price_is_left_alone():
    assert snap_unit_price(1234, None) == (1234, None)
    assert snap_unit_price(0, 0) == (0, 0)


def test_grand_total_matches_both_vat_modes():
    assert grand_total(28_000_000, vat_included=False) == 30_800_000
    assert grand_total(28_000_000, vat_included=True) == 30_800_000


def test_comparison_unit_snaps_to_100man_not_10man():
    # 비교견적서는 100만원 단위여야 한다(2026-08-20) — 10만원 단위 결과(예: 4,260,000)가
    # 그대로 나오면 만원 단위가 섞인 것이므로 실무자가 쓸 수 없다.
    amount, unit_price = snap_unit_price(4_260_000, 4_260_000 / 16, COMPARISON_AMOUNT_UNIT)
    assert unit_price % COMPARISON_AMOUNT_UNIT == 0, unit_price
    assert amount % COMPARISON_AMOUNT_UNIT == 0, amount


def test_amount_unit_for_selects_unit_by_is_primary():
    assert amount_unit_for(True) == UNIT_PRICE_UNIT
    assert amount_unit_for(False) == COMPARISON_AMOUNT_UNIT


def test_alphabrothers_integrated_package_reproduces_reference_quote():
    """실제 발급본을 그대로 재현하는지 — 유일하게 정답이 확정된 케이스다.

    출처: data/(알파) 기업명(or대표자명), OO업무 견적서_YYMMDD_N차_재훈 수정.xlsx
    (알파브라더스 시장검증 "통합 패키지", 총액 55,000,000원 VAT 포함 = 공급가액 50,000,000원).
    이 시트의 공급가액 수식은 =수량×단가라 작업일은 금액에 영향이 없다(010 마이그레이션 notes).
    """
    # (비중%, 수량, 참조 단가, 참조 공급가액)
    reference = [
        (10.0, 5, 1_000_000, 5_000_000),   # BM 진단 및 고도화
        (20.0, 2, 5_000_000, 10_000_000),  # FGI (심층 그룹 인터뷰)
        (20.0, 2, 5_000_000, 10_000_000),  # 사용성 테스트
        (20.0, 2, 5_000_000, 10_000_000),  # 기술성 테스트
        (30.0, 3, 5_000_000, 15_000_000),  # 시장성 테스트
    ]
    supply = round(55_000_000 / 1.1)
    assert supply == 50_000_000

    amounts = reconcile_amounts([round(supply * r / 100) for r, *_ in reference], supply, UNIT_PRICE_UNIT)
    for (_ratio, quantity, ref_unit_price, ref_amount), amount in zip(reference, amounts):
        # 본견적(10만원)이든 비교견적(100만원)이든 참조값이 그대로 나와야 한다.
        for unit in (UNIT_PRICE_UNIT, COMPARISON_AMOUNT_UNIT):
            assert snap_unit_price(amount, amount / quantity, unit) == (ref_amount, float(ref_unit_price))

    assert grand_total(sum(amounts), vat_included=True) == 55_000_000


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("모두 통과")