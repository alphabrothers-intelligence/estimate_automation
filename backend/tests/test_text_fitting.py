"""셀 글자 담기 자체 점검 — `python backend/tests/test_text_fitting.py`.

"칸보다 넓은 글자가 들어가면 단어 중간이 잘려 세로로 쌓이거나 옆 칸을 덮어쓴다"는 문제
(2026-08-20 사용자 지적, 테스티파이·알파브라더스 양식)를 막는 판단 로직이다. 실제 마스터
템플릿의 열 폭으로 검사해 양식이 바뀌면 여기서 먼저 드러나게 한다.
"""

import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import pdf_service as p

TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "testify.xlsx"


def _capacity(sheet_name="시장성테스트"):
    with zipfile.ZipFile(TEMPLATE) as z:
        sheet_xml = z.read(p._sheet_internal_path(z, sheet_name)).decode("utf-8")
        return p._capacity_fn(sheet_xml, z.read("xl/styles.xml").decode("utf-8")), sheet_xml


def test_merged_cell_capacity_covers_all_merged_columns():
    capacity, sheet_xml = _capacity()
    assert 'ref="A13:B17"' in sheet_xml  # 이 전제가 깨지면 아래 폭 기대값도 의미가 없다
    assert capacity("A13") > capacity("A16"), "병합된 칸이 병합 안 된 칸보다 넓어야 한다"


def test_shrink_only_when_it_stays_readable():
    """글자를 얼마나 줄여야 하느냐로 판단한다.

    예전엔 "칸보다 넓은 단어가 하나라도 있으면 무조건 shrinkToFit"이었다. 그러면 폭 4.7칸에
    폭 18짜리 "퍼포먼스 광고 운영"을 한 줄로 밀어넣느라 26%(8pt→2pt)로 찌그러져 읽을 수
    없는 글자가 나왔다(2026-08-21 사용자 신고). 조금만 줄이면 되는 경우에만 줄인다.
    """
    capacity, _ = _capacity()
    # 공백으로 끊어 담을 수 있으면 줄바꿈으로 충분하다.
    assert p._fit_mode("자사몰 데이터 세팅", capacity("A13")) == "wrap"
    # 한글 한 글자 폭은 2다. 칸에 딱 맞게/살짝 넘치게/크게 넘치게 만들어 세 갈래를 확인한다.
    narrow = capacity("C13")
    fits = "가" * int(narrow / 2)
    assert p._fit_mode(fits, narrow) == "wrap", "안 넘치면 줄일 이유가 없다"
    assert p._fit_mode(fits + "가", narrow) == "shrink", "살짝 넘치면 줄여서 한 줄에 담는다"
    # 크게 넘치면 읽을 수 없는 크기가 되므로 차라리 줄바꿈한다(한글은 글자 단위로 접힌다).
    assert p._fit_mode(fits * 3, narrow) == "wrap"
    assert p._fit_mode("퍼포먼스 광고 운영", 4.7) == "wrap"


def test_wrapped_line_count_counts_folded_lines_not_just_newlines():
    # \n 3개(=4줄)지만 각 줄이 길어 접히면 그보다 많아야 한다 — 행 높이가 그만큼 필요하다.
    text = "\n".join(["가나다라마바사아자차카타파하" * 3] * 4)
    assert p._wrapped_line_count(text, 20.0) > text.count("\n") + 1
    assert p._wrapped_line_count("짧은 값", 40.0) == 1


def test_plan_wraps_and_centers_narrow_label_cells():
    capacity, sheet_xml = _capacity()
    with zipfile.ZipFile(TEMPLATE) as z:
        styles_xml = z.read("xl/styles.xml").decode("utf-8")
    blocks = [{"category_large_cell": "A13", "rows": [13, 14, 15, 16, 17]}]
    columns = {"category_mid": "C", "item_name": "E", "description": "I"}
    plan = p._plan_text_fitting(
        sheet_xml,
        styles_xml,
        {"C13": "자사몰데이터세팅운영", "E13": "마케팅 전략안", "A13": "그로스해킹"},
        blocks,
        columns,
    )
    # 폭 11.9칸에 폭 20짜리 값 — 60%까지 줄여야 해서 읽을 수 없다. 줄바꿈으로 담는다.
    assert plan["C13"]["wrapText"] == "1" and "shrinkToFit" not in plan["C13"]
    assert plan["E13"]["wrapText"] == "1" and "shrinkToFit" not in plan["E13"]
    # 구분(대)/구분(중)/상품명은 가운데 정렬까지 보장한다.
    for coord in ("A13", "C13", "E13"):
        assert plan[coord]["horizontal"] == "center", coord


def test_cells_outside_item_table_keep_original_format():
    capacity, sheet_xml = _capacity()
    with zipfile.ZipFile(TEMPLATE) as z:
        styles_xml = z.read("xl/styles.xml").decode("utf-8")
    plan = p._plan_text_fitting(sheet_xml, styles_xml, {"D6": "아주 긴 수신처 담당자 이름"}, [], {})
    assert plan == {}, plan


def test_alignment_patch_produces_valid_styles_xml():
    with zipfile.ZipFile(TEMPLATE) as z:
        sheet_xml = z.read(p._sheet_internal_path(z, "시장성테스트")).decode("utf-8")
        styles_xml = z.read("xl/styles.xml").decode("utf-8")
    patched_sheet, patched_styles = p._ensure_alignment(
        sheet_xml, styles_xml, {"C13": {"shrinkToFit": "1", "wrapText": "0", "horizontal": "center"}}
    )
    body = re.search(r'<cellXfs count="(\d+)">(.*?)</cellXfs>', patched_styles, re.DOTALL)
    assert int(body.group(1)) == len(re.findall(r"<xf\b[^>]*?(?:/>|>.*?</xf>)", body.group(2), re.DOTALL))
    # 같은 속성이 두 번 붙으면 LibreOffice가 styles.xml 전체를 버린다.
    for xf in re.findall(r"<xf\b[^>]*?(?:/>|>.*?</xf>)", body.group(2), re.DOTALL):
        assert xf.count("wrapText=") <= 1 and xf.count("shrinkToFit=") <= 1, xf
    assert re.search(r'<c r="C13" s="(\d+)"', patched_sheet)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("모두 통과")


def test_remap_cell_map_moves_integer_row_numbers():
    """행 번호가 정수로 들어 있는 자리(totals.grand_total_row)도 삽입만큼 밀려야 한다.

    2026-08-21: "rows" 리스트만 옮기고 정수는 통과시켜서, 썬데이워커 합계 행이 35에 머문 채
    실제 합계는 37로 밀렸다. 그 사이 두 행이 안 지워져 0이 두 줄 남았다.
    """
    from app.services.xlsx_rows import remap_cell_map

    cell_map = {
        "item_blocks": [{"rows": [13, 14], "category_large_cell": "A13"}],
        "totals": {"grand_total_row": 35, "top_display_cell": "R9"},
        "always_clear_cells": ["B24"],
    }
    out = remap_cell_map(cell_map, {13: 13, 14: 14, 24: 26, 35: 37})
    assert out["totals"]["grand_total_row"] == 37
    assert out["totals"]["top_display_cell"] == "R9"  # 옮길 필요 없는 좌표는 그대로
    assert out["item_blocks"][0]["rows"] == [13, 14]
    assert out["always_clear_cells"] == ["B26"]
