"""품명 한 칸짜리 양식 묶음 표시 자체 점검 — `python backend/tests/test_name_only_grouping.py`.

블렌디드랩·썬데이워커처럼 구분(대/중)도 상품구성 칸도 없는 양식은 세부 항목을 낱개 행으로
나열하면 무슨 묶음인지 알 수 없다 — "그로스마케팅 운영\n(주간 성과 리포트 / 주간 실행과제)"
처럼 카테고리당 한 줄로 묶는 게 기본 표시 방식이다(2026-08-24 사용자 재지적).

묶은 줄에 단가를 안 넣으면 양식의 공급가액 수식(블렌디드랩 AB=+W 등)이 0으로 재계산되어
합계까지 0으로 나갔던 회귀(2026-08-21)도 함께 막는다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import pdf_service as p

# 블렌디드랩 마스터의 실제 cell_map(마이그레이션 010 + 023)
BLENDEDLAB_COLUMNS = {"item_name": "B", "work_days": "O", "quantity": "S", "unit_price": "W", "amount": "AB"}
BLENDEDLAB_BLOCKS = [{"rows": [13, 14, 15, 16]}]

# 상품구성 칸이 있는 양식(알파브라더스) — 묶어도 품명 뒤 괄호를 쓰지 않는다
ALPHA_COLUMNS = {"item_name": "E", "description": "I", "work_days": "T", "quantity": "V", "unit_price": "X", "supply_amount": "AA"}
ALPHA_BLOCKS = [{"category_large_cell": "A13", "category_mid_cell": "C13", "rows": [13, 14, 15, 16, 17]}]


def _items():
    return [
        {"category": "그로스마케팅 운영", "name": "주간 성과 리포트 & 전략 미팅", "amount": 8_000_000,
         "unit_price": 500_000, "work_days": 1, "quantity": 16},
        {"category": "그로스마케팅 운영", "name": "주간 실행과제 이행", "amount": 5_600_000,
         "unit_price": 400_000, "work_days": 1, "quantity": 14},
        {"category": "브랜드 런칭 지원", "name": "자사 쇼핑몰 셋업", "amount": 2_630_000,
         "unit_price": 2_630_000, "work_days": 1, "quantity": 1},
        {"category": "브랜드 런칭 지원", "name": "마케팅 방향성 기획안", "amount": 200_000,
         "unit_price": 200_000, "work_days": 3, "quantity": 1},
    ]


def _items_with_description():
    """테스티파이 시장성 테스트 카탈로그의 모양 — 상품명마다 상품구성이 붙어 있다."""
    return [
        {"category": "시장성 테스트", "name": "BM 진단 및 고도화", "amount": 2_000_000,
         "unit_price": 2_000_000, "work_days": 1, "quantity": 1,
         "description": "1. Business Model 9 Canvas 작성 및 분석\n2. Value Curve 작성 및 분석"},
        {"category": "시장성 테스트", "name": "MVP 제작", "amount": 9_000_000,
         "unit_price": 3_000_000, "work_days": 10, "quantity": 3,
         "description": "1. MVP 상세페이지 디자인 작업\n2. MVP별 랜딩페이지 구축"},
        {"category": "시장성 테스트", "name": "결과 리포트 제공", "amount": 1_500_000,
         "unit_price": 1_500_000, "work_days": 1, "quantity": 1,
         "description": "1. 시장성 데이터 분석 리포트 제작\n2. 분석 결과 보고"},
    ]


def test_name_only_form_detection():
    assert p._is_name_only_form(BLENDEDLAB_COLUMNS, BLENDEDLAB_BLOCKS)
    assert not p._is_name_only_form(ALPHA_COLUMNS, ALPHA_BLOCKS)


def test_blendedlab_groups_into_one_row_per_category():
    """4행에 낱개 4개가 그대로 들어가도(=자리는 충분해도) 묶어서 2줄로 나와야 한다."""
    groups = p._group_line_items(_items())
    assignments = p._assign_groups_to_blocks(groups, BLENDEDLAB_BLOCKS, BLENDEDLAB_COLUMNS)

    names = [item["name"] for _, group, _ in assignments for item in group["items"]]
    assert names == [
        "그로스마케팅 운영\n(주간 성과 리포트 & 전략 미팅 / 주간 실행과제 이행)",
        "브랜드 런칭 지원\n(자사 쇼핑몰 셋업 / 마케팅 방향성 기획안)",
    ], names
    # 괄호는 반드시 다음 줄에서 시작한다 — 품명 옆에 붙으면 어디까지가 품명인지 구분이 안 된다.
    assert all(n.count("\n") == 1 and n.split("\n")[1].startswith("(") for n in names)


def test_grouped_row_carries_unit_price_so_form_formula_survives():
    """블렌디드랩 AB=+W, 썬데이워커 R=N*K, 알파브라더스 AA=SUM(T*V*X) — 셋 다 총액이 나와야."""
    groups = p._group_line_items(_items())
    assignments = p._assign_groups_to_blocks(groups, BLENDEDLAB_BLOCKS, BLENDEDLAB_COLUMNS)

    for _, group, _ in assignments:
        item = group["items"][0]
        assert item["unit_price"] > 0, item
        assert item["unit_price"] == item["amount"]  # AB = +W
        assert item["unit_price"] * item["quantity"] == item["amount"]  # R = N*K
        assert item["work_days"] * item["quantity"] * item["unit_price"] == item["amount"]  # AA = SUM(T*V*X)

    assert sum(g["amount"] for _, g, _ in assignments) == sum(i["amount"] for i in _items())


def test_blendedlab_splits_one_row_per_product_when_description_exists():
    """실무자 지적(2026-08-24): 테스티파이 상품명이 블렌디드랩 품명, 상품구성이 그 아래 괄호."""
    groups = p._group_line_items(_items_with_description())
    assignments = p._assign_groups_to_blocks(groups, BLENDEDLAB_BLOCKS, BLENDEDLAB_COLUMNS)

    names = [item["name"] for _, group, _ in assignments for item in group["items"]]
    assert names == [
        "BM 진단 및 고도화\n(Business Model 9 Canvas 작성 및 분석 / Value Curve 작성 및 분석)",
        "MVP 제작\n(MVP 상세페이지 디자인 작업 / MVP별 랜딩페이지 구축)",
        "결과 리포트 제공\n(시장성 데이터 분석 리포트 제작 / 분석 결과 보고)",
    ], names


def test_split_rows_keep_their_own_unit_price_and_quantity():
    """항목당 한 줄이면 각 줄이 자기 단가·수량을 그대로 들고 가야 양식 수식이 맞는다."""
    groups = p._group_line_items(_items_with_description())
    assignments = p._assign_groups_to_blocks(groups, BLENDEDLAB_BLOCKS, BLENDEDLAB_COLUMNS)
    rows = [item for _, group, _ in assignments for item in group["items"]]

    for row, src in zip(rows, _items_with_description()):
        assert (row["unit_price"], row["quantity"], row["work_days"], row["amount"]) == (
            src["unit_price"], src["quantity"], src["work_days"], src["amount"]
        ), row
    assert sum(r["amount"] for r in rows) == sum(i["amount"] for i in _items_with_description())


def test_row_growth_counts_split_rows_not_categories():
    """상품구성이 있으면 카테고리 1개라도 항목 수만큼 행을 늘려야 한다(예전엔 1줄로 셌다)."""
    groups = p._fold_name_only(p._group_line_items(_items_with_description()))
    assert sum(len(g["items"]) for g in groups) == 3


def test_description_form_keeps_vertical_list_not_parentheses():
    """상품구성 칸이 있는 양식은 예전처럼 세로형 개조식으로 접는다(품명 괄호 아님)."""
    groups = p._group_line_items(_items())
    assignments = p._assign_groups_to_blocks(groups, ALPHA_BLOCKS * 2, ALPHA_COLUMNS)

    item = assignments[0][1]["items"][0]
    assert "(" not in item["name"]
    assert item["description"].startswith("1. ")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("모두 통과")