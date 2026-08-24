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