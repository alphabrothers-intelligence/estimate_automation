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


def test_long_single_word_is_shrunk_not_wrapped():
    capacity, _ = _capacity()
    # 공백이 없어 줄바꿈으로는 못 담는 값 — wrapText면 단어 중간이 깨진다.
    assert p._needs_shrink("자사몰데이터세팅운영", capacity("C13"))
    # 공백으로 끊어 담을 수 있으면 줄바꿈으로 충분하다.
    assert not p._needs_shrink("자사몰 데이터 세팅", capacity("A13"))


def test_wrapped_line_count_counts_folded_lines_not_just_newlines():
    # \n 3개(=4줄)지만 각 줄이 길어 접히면 그보다 많아야 한다 — 행 높이가 그만큼 필요하다.
    text = "\n".join(["가나다라마바사아자차카타파하" * 3] * 4)
    assert p._wrapped_line_count(text, 20.0) > text.count("\n") + 1
    assert p._wrapped_line_count("짧은 값", 40.0) == 1


def test_plan_marks_shrink_and_center_for_narrow_label_cells():
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
    assert plan["C13"]["shrinkToFit"] == "1" and plan["C13"]["wrapText"] == "0"
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
