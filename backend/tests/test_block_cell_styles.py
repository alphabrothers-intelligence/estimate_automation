"""항목 블록의 들쭉날쭉한 셀 서식 보정(_normalize_block_cell_styles) 회귀 테스트.

블렌디드랩 마스터는 표 오른쪽이 열려 있는 양식인데 한 행만 오른쪽 세로선이 있는 스타일이라,
그 행만 선이 보였다(2026-09-17 사용자 재지적).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.pdf_service import _normalize_block_cell_styles

HAIR = '<top style="hair"/><bottom style="hair"/>'
THICK_TOP = '<top style="thin"><color theme="1"/></top><bottom style="hair"/>'

STYLES_XML = (
    "<styleSheet><borders>"
    f'<border><left/><right/>{HAIR}<diagonal/></border>'  # 0: 오른쪽 열림
    f'<border><left/><right style="hair"/>{HAIR}<diagonal/></border>'  # 1: 오른쪽 닫힘
    f'<border><left/><right/>{THICK_TOP}<diagonal/></border>'  # 2: 표를 여는 진한 윗선
    "</borders><cellXfs>"
    '<xf numFmtId="0" fontId="1" borderId="0"/>'  # 0: 다수파
    '<xf numFmtId="0" fontId="1" borderId="1"/>'  # 1: 테두리만 다름 → 0으로 교정
    '<xf numFmtId="0" fontId="9" borderId="1"/>'  # 2: 글꼴까지 다름 → 그대로
    '<xf numFmtId="0" fontId="1" borderId="2"/>'  # 3: 윗선이 다름 → 그대로
    "</cellXfs></styleSheet>"
)


def _sheet(styles_by_row):
    return "".join(f'<c r="A{row}" s="{s}"/>' for row, s in styles_by_row.items())


def test_오른쪽_테두리만_다른_행은_다수파로_맞춘다():
    sheet = _sheet({13: 0, 14: 0, 15: 1, 16: 0})
    assert '<c r="A15" s="0"/>' in _normalize_block_cell_styles(sheet, STYLES_XML, [{"rows": [13, 14, 15, 16]}])


def test_문제의_행이_블록_마지막이어도_맞춘다():
    # 항목이 늘면 행이 복제돼 문제의 행이 블록 끝으로 밀린다 — 예전 로직은 이걸 놓쳤다.
    sheet = _sheet({13: 0, 14: 0, 15: 0, 16: 1})
    assert '<c r="A16" s="0"/>' in _normalize_block_cell_styles(sheet, STYLES_XML, [{"rows": [13, 14, 15, 16]}])


def test_글꼴이_다른_행은_건드리지_않는다():
    sheet = _sheet({13: 0, 14: 0, 15: 2, 16: 0})
    assert '<c r="A15" s="2"/>' in _normalize_block_cell_styles(sheet, STYLES_XML, [{"rows": [13, 14, 15, 16]}])


def test_표를_여는_윗선은_지우지_않는다():
    sheet = _sheet({13: 3, 14: 0, 15: 0, 16: 0})
    assert '<c r="A13" s="3"/>' in _normalize_block_cell_styles(sheet, STYLES_XML, [{"rows": [13, 14, 15, 16]}])


def test_두_행이_서로_다르면_동전던지기를_하지_않는다():
    sheet = _sheet({13: 0, 14: 1})
    assert '<c r="A14" s="1"/>' in _normalize_block_cell_styles(sheet, STYLES_XML, [{"rows": [13, 14]}])


def test_블렌디드랩_마스터는_행을_늘려도_표_오른쪽이_열려_있다():
    """실제 원인 회귀 — 복제 원본(끝에서 두 번째 행)이 하필 서식이 어긋난 15행이라, 항목이
    늘면 오른쪽이 막힌 행이 여러 줄로 불어나 다수파가 됐다."""
    import io
    import re
    import zipfile

    from app.services import xlsx_rows
    from app.services.pdf_service import (
        _normalize_block_styles_in_xlsx,
        _plan_row_growth,
        _sheet_internal_path,
    )

    master = (Path(__file__).resolve().parents[1] / "templates" / "blendedlab.xlsx").read_bytes()
    with zipfile.ZipFile(io.BytesIO(master)) as zin:
        sheet_path = _sheet_internal_path(zin, "견적서 (2)")

    blocks = [{"rows": [13, 14, 15, 16]}]
    plan = _plan_row_growth([{"items": [1, 2, 3, 4, 5]}], blocks)
    grown, _ = xlsx_rows.expand_sheet_rows(
        _normalize_block_styles_in_xlsx(master, sheet_path, blocks), sheet_path, "견적서 (2)", plan
    )

    sheet_xml = zipfile.ZipFile(io.BytesIO(grown)).read(sheet_path).decode("utf-8")
    styles = dict(re.findall(r'<c r="([A-Z]+\d+)" s="(\d+)"', sheet_xml))
    amount_column = {styles[f"AF{row}"] for row in range(13, 18)}
    assert len(amount_column) == 1, f"금액 칸 오른쪽 테두리가 행마다 다름: {amount_column}"
