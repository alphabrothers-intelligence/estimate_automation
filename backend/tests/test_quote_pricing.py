"""금액 후처리 자체 점검 — `python backend/tests/test_quote_pricing.py`.

여기가 깨지면 (a) 화면 총액과 발급본 총액이 어긋나거나 (b) 266,250원 같은 잔돈 단가가 다시
나오거나 (c) 사용자가 입력한 총액이 조용히 다른 값으로 발급된다. 세 가지 모두 2026-08-20
이전 로직에서 실제로 발생했던 증상이다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.quote_pricing import (
    CLEAN_UNIT,
    FormSpec,
    assert_storable,
    detect_form,
    finalize,
    structural_violations,
)
from app.services.quote_prompts import extract_json

# 실제 마스터 xlsx에서 읽은 수식 (2026-08-20 실측)
ALPHA_COLS = {"work_days": "T", "quantity": "V", "unit_price": "X", "supply_amount": "AA"}
SUNDAY_COLS = {"quantity": "K", "unit_price": "N", "supply_amount": "R"}
BLENDED_COLS = {"work_days": "O", "quantity": "S", "unit_price": "W", "amount": "AB"}


def _sheet(coord: str, formula: str) -> str:
    return f'<row><c r="{coord}" s="1"><f>{formula}</f><v>0</v></c></row>'


def test_every_form_uses_unit_price_times_quantity():
    """금액 규칙은 다섯 법인 전부 "단가 × 수량"이고 작업일은 금액과 무관하다(2026-08-21 확정).

    예전엔 시트 수식을 읽어 법인마다 다르게 계산했는데(알파브라더스 단가×작업일×수량,
    블렌디드랩 =단가), 화면·채팅·발급이 서로 다른 규칙을 가정하면서 금액이 갈리는 사고가
    반복됐다. 원본 수식이 다른 양식은 발급 시 그 셀의 수식을 지우고 값을 쓴다.
    """
    form = detect_form("", ALPHA_COLS, 13, {"work_days": "작업일", "quantity": "수량"})
    assert (form.uses_work_days, form.uses_quantity) == (False, True)
    assert form.formula_text == "공급가액 = 단가 × 수량"

    # 작업일이 30이어도 금액에는 영향이 없다
    assert form.amount_of({"unit_price": 500_000, "quantity": 16, "work_days": 30}) == 8_000_000
    # 수량을 고치면 금액이 바뀌고, 단가를 고쳐도 금액이 바뀐다
    assert form.amount_of({"unit_price": 500_000, "quantity": 20}) == 10_000_000
    assert form.amount_of({"unit_price": 600_000, "quantity": 16}) == 9_600_000


def test_blendedlab_also_multiplies_quantity():
    """블렌디드랩에도 수량 컬럼이 있고, 금액은 수량 × 단가다(2026-08-21 사용자 확정).
    마스터 원본 수식이 =단가라서 발급 시 그 수식을 지우고 값을 쓴다."""
    form = FormSpec()
    assert form.amount_of({"name": "x", "unit_price": 3_900_000, "quantity": 3, "work_days": 6}) == 11_700_000


def test_amount_is_always_recomputed_from_the_formula():
    """AI가 준 amount는 버린다. 수식과 어긋난 값을 그대로 저장하면 발급본과 화면이 갈린다."""
    form = FormSpec()
    items = [{"name": "a", "unit_price": 500_000, "quantity": 4, "amount": 999_999_999}]
    out, residual, _ = finalize(items, None, form)
    assert out[0]["amount"] == 2_000_000
    assert residual == 0


def test_ugly_unit_price_is_cleaned_but_round_one_is_left_alone():
    form = FormSpec(unit_price_unit=100_000)
    items = [
        # 3,033,000원 — 만원 단위로 안 떨어지는 '지저분한' 단가라 정리 대상
        {"name": "지저분", "unit_price": 3_033_000, "quantity": 1},
        # 350,000원 — 5만원 배수지만 금액도 만원 단위로 떨어지므로 그대로 둔다.
        # 10만원 배수를 강제하면 400,000원이 되어 멀쩡한 총액을 깨뜨린다(2026-08-20 재현).
        {"name": "멀쩡", "unit_price": 350_000, "quantity": 20},
    ]
    out, _, log = finalize(items, None, form)
    assert out[0]["unit_price"] == 3_000_000
    assert out[1]["unit_price"] == 350_000
    assert len(log) == 1 and "지저분" in log[0]
    assert all(i["unit_price"] % CLEAN_UNIT == 0 for i in out)


def test_hits_the_target_using_two_items_when_one_cannot_reach():
    """테스티파이 +10% 실측 케이스. 걸음이 500k/200k/200k/200k/300k라 단일 항목으로는
    +100,000원에 닿지 못한다 — 한 항목을 올리고 다른 항목을 내려야 정확히 맞는다."""
    form = FormSpec(unit_price_unit=100_000)
    items = [
        {"name": "BM 진단", "unit_price": 700_000, "quantity": 5},
        {"name": "FGI", "unit_price": 3_500_000, "quantity": 2},
        {"name": "사용성", "unit_price": 3_400_000, "quantity": 2},
        {"name": "기술성", "unit_price": 3_300_000, "quantity": 2},
        {"name": "시장성", "unit_price": 3_033_000, "quantity": 3},
    ]
    out, residual, log = finalize(items, 33_000_000, form)
    assert sum(i["amount"] for i in out) == 33_000_000
    assert residual == 0
    assert sum(1 for line in log if line.startswith("총액 맞춤")) <= 2


def test_untouched_items_stay_untouched():
    """목표에 이미 맞으면 아무것도 움직이지 않는다. 예전엔 목표가 없어도 전 항목을 다시
    반올림하고 차액을 최대 항목에 몰아줘서, 손대지도 않은 금액이 매번 흔들렸다."""
    form = FormSpec()
    items = [
        {"name": "a", "unit_price": 1_000_000, "quantity": 1},
        {"name": "b", "unit_price": 2_000_000, "quantity": 1},
    ]
    out, residual, log = finalize(items, 3_000_000, form)
    assert [i["unit_price"] for i in out] == [1_000_000, 2_000_000]
    assert residual == 0 and log == []


def test_unreachable_target_gets_as_close_as_the_grid_allows():
    """격자상 정확히 못 닿는 목표는 **가장 가까운 값까지 간 뒤** 남은 잔액을 표시한다
    (2026-08-20 결정). 예전엔 정확히 못 맞추면 아무것도 안 해서 100,000원이 통째로 남았는데,
    그게 45% 격차를 방치하는 사고로 이어졌다(2026-08-21)."""
    form = FormSpec(unit_price_unit=100_000)
    items = [{"name": "단일", "unit_price": 1_000_000, "quantity": 3}]  # 걸음이 30,000원(만원×3)
    out, residual, log = finalize(items, 3_100_000, form)
    total = sum(i["amount"] for i in out)
    assert abs(3_100_000 - total) < 100_000, f"아무것도 안 하면 안 된다: {total:,}"
    assert residual == 3_100_000 - total
    if residual:
        assert any("도달 불가" in line for line in log)


def test_absorption_never_triples_a_small_item():
    """작은 항목에 잔액을 몰아주면 100,000원짜리가 300,000원이 된다(2026-08-20 사용자 지적).
    이동 폭을 단가의 35%로 묶어 상대 중요도를 지킨다."""
    form = FormSpec(unit_price_unit=100_000)
    items = [
        {"name": "작은 항목", "unit_price": 100_000, "quantity": 1},
        {"name": "큰 항목", "unit_price": 5_000_000, "quantity": 1},
    ]
    out, _, _ = finalize(items, 6_100_000, form)
    small = next(i for i in out if i["name"] == "작은 항목")
    assert small["unit_price"] <= 135_000


def test_rescaling_a_comparison_keeps_workload_and_hits_the_new_target():
    """본견적 금액이 바뀌었을 때 비교견적을 AI 없이 맞추는 경로(generation_service.rescale_comparisons).
    단가에만 배율을 곱하고 작업일·수량은 그대로 둔다 — 업무량은 금액 사정으로 바뀌면 안 된다."""
    form = FormSpec(unit_price_unit=100_000)
    items = [
        {"name": "a", "unit_price": 3_000_000, "quantity": 2, "work_days": 30},
        {"name": "b", "unit_price": 1_000_000, "quantity": 5, "work_days": 5},
    ]
    current = sum(form.amount_of(i) for i in items)  # 11,000,000
    target = round(current * 1.2)  # 본견적이 20% 올랐다고 가정
    scaled = [dict(i, unit_price=i["unit_price"] * target / current) for i in items]
    out, residual, _ = finalize(scaled, target, form)

    assert sum(i["amount"] for i in out) == target and residual == 0
    assert [i["quantity"] for i in out] == [2, 5]
    assert [i["work_days"] for i in out] == [30, 5]
    assert all(i["amount"] > form.amount_of(src) for i, src in zip(out, items))


def test_coarse_grid_falls_back_to_a_finer_one_to_hit_the_target():
    """블렌디드랩(공급가액=단가, 단가단위 10만원)은 걸음이 전부 10만원이라 도달 가능한 총액이
    10만원 배수뿐이다. 목표가 30,030,000원이면 30,000원이 남아 사용자가 지정한 +10%가 화면에
    +9.9%로 찍혔다(2026-08-21 사용자 지적). 굵은 단위로 못 닿으면 만원 단위로 재시도한다."""
    form = FormSpec(unit_price_unit=100_000)
    items = [
        {"name": f"i{i}", "unit_price": p, "quantity": 1}
        for i, p in enumerate([8_708_699, 5_305_299, 3_303_299, 200_199, 700_699])
    ]
    target = 18_230_000  # 10만원 배수가 아니다
    out, residual, _ = finalize(items, target, form)
    assert sum(i["amount"] for i in out) == target
    assert residual == 0


def test_extract_json_handles_every_caller_shape():
    """호출부마다 응답 모양이 다르다 — 견적 생성은 items, 모듈 선택은 selected.
    필수 키를 "items"로 박아두는 바람에 모듈 선택이 항상 500으로 죽었다(2026-08-21 재현)."""
    assert extract_json('{"selected": ["A"]}')["selected"] == ["A"]
    assert extract_json('설명 {괄호} 섞임 {"items": [1, 2]}', require_key="items")["items"] == [1, 2]
    # 앞쪽 중괄호가 items를 안 가지면 건너뛰고 진짜 응답을 고른다
    got = extract_json('{"note": 1} 그리고 {"items": [1, 2, 3]}', require_key="items")
    assert got["items"] == [1, 2, 3]
    try:
        extract_json("JSON이 전혀 없는 답변")
        raise AssertionError("실패해야 한다")
    except ValueError:
        pass


def test_large_gap_is_closed_by_rescaling_not_left_alone():
    """AI가 목표의 절반 수준으로 낮게 산정한 실제 사고(2026-08-21). 흡수는 항목당 35%까지만
    움직이는 미세 조정이라 큰 격차를 못 메우는데, 예전엔 "격자상 도달 불가"라며 아무것도 안 해서
    본견적보다 싼 비교견적이 저장됐다."""
    form = FormSpec(unit_price_unit=100_000)
    items = [
        {"name": "주간 성과 리뷰", "unit_price": 600_000, "quantity": 14},
        {"name": "주간 실행과제", "unit_price": 400_000, "quantity": 13.44},
        {"name": "온라인 스토어 셋업", "unit_price": 2_900_000, "quantity": 1.08},
        {"name": "마케팅 방향성", "unit_price": 100_000, "quantity": 1.2},
    ]
    before = sum(form.amount_of(i) for i in items)
    target = 30_030_000
    assert before < target * 0.6, "전제: AI가 크게 낮게 냈다"

    out, residual, log = finalize(items, target, form)
    assert sum(i["amount"] for i in out) == target
    assert residual == 0
    assert any("전체 배율 조정" in line for line in log), log
    # 상대 중요도는 그대로 — 배율을 곱하기 전후로 금액 순위가 바뀌지 않는다
    before_rank = sorted(range(len(items)), key=lambda i: form.amount_of(items[i]))
    after_rank = sorted(range(len(out)), key=lambda i: out[i]["amount"])
    assert before_rank == after_rank


def test_finalize_output_always_passes_the_storage_guard():
    """finalize를 거친 결과는 어떤 입력이든 저장 관문을 통과해야 한다 — 실제로 사고를 냈던
    입력들(소수 수량, 수식 오해, 잔돈 단가)을 그대로 먹여 확인한다(2026-08-21)."""
    cases = [
        (FormSpec(unit_price_unit=10_000),
         [{"name": "소수 수량", "unit_price": 120_000, "work_days": 5, "quantity": 13.44},
          {"name": "소수 작업일", "unit_price": 100_000, "work_days": 3.2, "quantity": 1.08}]),
        (FormSpec(unit_price_unit=100_000),
         [{"name": "수식 오해", "unit_price": 600_000, "quantity": 14},
          {"name": "낮게 산정", "unit_price": 400_000, "quantity": 13}]),
        (FormSpec(unit_price_unit=100_000),
         [{"name": "잔돈", "unit_price": 266_250, "quantity": 16},
          {"name": "잔돈2", "unit_price": 6_222_727, "quantity": 1}]),
    ]
    for form, items in cases:
        out, _residual, _log = finalize(items, 30_000_000, form)
        assert structural_violations(out, form) == [], (form.formula_text, structural_violations(out, form))
        assert_storable(out, form, "테스트")  # 예외가 나면 실패


def test_storage_guard_actually_rejects_bad_data():
    """관문이 실제로 막는지 — 막지 못하면 관문이 없는 것과 같다."""
    form = FormSpec(unit_price_unit=100_000)
    broken = [{"name": "수식 어긋남", "unit_price": 100_000, "quantity": 2, "amount": 999}]
    assert structural_violations(broken, form)
    try:
        assert_storable(broken, form, "테스트")
        raise AssertionError("막았어야 한다")
    except ValueError as e:
        assert "수식" in str(e)


# ── 용역 사업 간접비 (마이그레이션 050) ──────────────────────────────────────────

OVERHEAD = "경비 및 간접비"


def _service_quote():
    """직접비 3줄 + 일반관리비 + 이윤. 실제 발급본(한양대 시장검증)의 모양."""
    return [
        {"category": "시장성 테스트", "name": "비즈니스 모델 진단", "unit_price": 300_000, "quantity": 3, "work_days": 1, "amount": 0},
        {"category": "시장성 테스트", "name": "시장검증 디자인 제작", "unit_price": 700_000, "quantity": 3, "work_days": 1, "amount": 0},
        {"category": "시장성 테스트", "name": "시장검증 보고서 제작", "unit_price": 600_000, "quantity": 3, "work_days": 1, "amount": 0},
        {"category": OVERHEAD, "name": "일반관리비", "unit_price": 387_000, "quantity": 1, "work_days": 1, "amount": 0},
        {"category": OVERHEAD, "name": "이윤", "unit_price": 349_364, "quantity": 1, "work_days": 1, "amount": 0},
    ]


def test_expense_items_keep_real_cost_unit_prices():
    """교통비 3만원은 실비다. 10만원 격자에 스냅하면 7만원으로 부풀고 이윤 흡수까지 깨진다."""
    items = [
        {"category": "시장성 테스트", "name": "비즈니스 모델 진단", "unit_price": 300_000, "quantity": 3, "work_days": 1, "amount": 0},
        {"category": OVERHEAD, "name": "교통비 (수요처별 방문 기준)", "unit_price": 30_000, "quantity": 12, "work_days": 1, "amount": 0},
        {"category": OVERHEAD, "name": "회의 및 기타경비", "unit_price": 20_000, "quantity": 12, "work_days": 1, "amount": 0},
        {"category": OVERHEAD, "name": "일반관리비", "unit_price": 387_000, "quantity": 1, "work_days": 1, "amount": 0},
        {"category": OVERHEAD, "name": "이윤", "unit_price": 349_364, "quantity": 1, "work_days": 1, "amount": 0},
    ]
    result, residual, log = finalize(items, 3_000_000, FormSpec())
    by_name = {i["name"]: i for i in result}

    # 실비는 만원 단위로만 정리된다 — 10만원 미만이어야 실비답다.
    assert by_name["교통비 (수요처별 방문 기준)"]["unit_price"] < 100_000, log
    assert by_name["회의 및 기타경비"]["unit_price"] < 100_000, log
    for row in result:
        assert row["unit_price"] % CLEAN_UNIT == 0 or row["name"] in ("일반관리비", "이윤"), row
    # 실비가 안 부푸니 이윤이 잔액을 정상적으로 먹는다.
    assert residual == 0, (residual, log)


def test_profit_line_absorbs_the_whole_residual():
    """이윤이 있으면 잔액 0으로 정확히 떨어지고, 직접비 단가는 하나도 안 움직인다."""
    target = 5_500_000
    items, residual, log = finalize(_service_quote(), target, FormSpec())

    assert residual == 0, (residual, log)
    assert sum(i["amount"] for i in items) == target
    for row, before in zip(items[:3], _service_quote()[:3]):
        assert row["unit_price"] == before["unit_price"], row
    assert any("이윤으로 잔액 흡수" in line for line in log), log


def test_rate_based_items_are_not_snapped_to_clean_units():
    """349,364원은 요율에서 나온 정상값이다 — 만원 단위로 밀면 요율이 깨진다."""
    items, _residual, log = finalize(_service_quote(), None, FormSpec())
    by_name = {i["name"]: i for i in items}

    assert by_name["이윤"]["unit_price"] == 349_364
    assert by_name["일반관리비"]["unit_price"] == 387_000
    assert not any("단가 정리" in line and ("이윤" in line or "일반관리비" in line) for line in log), log


def test_vat_derived_target_still_passes_the_storage_guard():
    """VAT 포함 15,000,000원 → 공급가액 13,636,364원. 만원 배수가 아니라 잔돈이 반드시 남는다.

    이 잔돈을 이윤이 먹는데, 저장 관문(structural_violations)이 만원 단위를 강제하면 발급이
    통째로 실패한다 — 관문에도 같은 예외가 있어야 한다(구현 중 실제로 걸렸다).
    """
    target = 13_636_364
    items, residual, _log = finalize(_service_quote(), target, FormSpec())

    assert residual == 0
    assert sum(i["amount"] for i in items) == target
    assert structural_violations(items, FormSpec()) == []
    # 직접비는 전부 만원 단위로 떨어지고, 잔돈은 이윤 한 줄에만 남는다.
    for row in items[:3]:
        assert row["amount"] % CLEAN_UNIT == 0, row


def test_direct_cost_items_are_still_snapped():
    """간접비 예외가 직접비까지 풀어주면 안 된다."""
    items = _service_quote()
    items[0]["unit_price"] = 266_250  # 실무자가 못 견디던 잔돈
    result, _residual, log = finalize(items, None, FormSpec())

    assert result[0]["unit_price"] % CLEAN_UNIT == 0, result[0]
    assert any("단가 정리" in line for line in log), log


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("\n전부 통과")


# --- 채팅 도구 적용 (chat_service._apply) ---
# 2026-08-21: 모델이 "행을 추가했습니다"라고 답했는데 표에는 아무 일도 없던 버그.
# 도구에 추가 수단이 없었고, 범위 밖 번호는 조용히 버려졌다.

def _items():
    return [
        {"name": "A", "category": "기획", "description": "", "work_days": 1, "quantity": 1,
         "unit_price": 1_000_000, "amount": 1_000_000},
        {"name": "B", "category": "퍼포먼스", "description": "", "work_days": 1, "quantity": 2,
         "unit_price": 2_000_000, "amount": 4_000_000},
    ]


def test_apply_adds_row_after_given_item():
    from app.services import chat_service
    form = FormSpec()
    edit = {"add_items": [{"after": 1, "name": "결과 보고", "unit_price": 500_000}]}
    result, target = chat_service._apply(_items(), edit, form)
    assert [i["name"] for i in result] == ["A", "결과 보고", "B"]
    assert target is None


def test_apply_appends_when_after_omitted():
    from app.services import chat_service
    edit = {"add_items": [{"name": "결과 보고", "unit_price": 500_000}]}
    result, _ = chat_service._apply(_items(), edit, FormSpec())
    assert [i["name"] for i in result] == ["A", "B", "결과 보고"]


def test_apply_treats_out_of_range_index_with_name_as_add():
    """모델이 add_items 대신 items에 없는 번호를 쓰는 실수를 해도 행이 사라지지 않아야 한다."""
    from app.services import chat_service
    edit = {"items": [{"i": 3, "name": "결과 보고", "unit_price": 500_000}]}
    result, _ = chat_service._apply(_items(), edit, FormSpec())
    assert [i["name"] for i in result] == ["A", "B", "결과 보고"]


def test_apply_add_position_survives_removal_in_same_call():
    """같은 요청에서 앞 항목을 지워도 추가 위치가 밀리지 않아야 한다."""
    from app.services import chat_service
    edit = {"remove_item_numbers": [1], "add_items": [{"after": 2, "name": "C", "unit_price": 100_000}]}
    result, _ = chat_service._apply(_items(), edit, FormSpec())
    assert [i["name"] for i in result] == ["B", "C"]
