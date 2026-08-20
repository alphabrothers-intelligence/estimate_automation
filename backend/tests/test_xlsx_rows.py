"""xlsx_rows 자체 점검 — `python backend/tests/test_xlsx_rows.py`.

Excel이 "행 삽입"할 때 지켜야 하는 것들(아래 행 번호·수식 참조·병합·인쇄영역이 함께 밀리고,
복제된 행의 상대 참조가 자기 위치를 가리키는 것)을 확인한다. 여기가 깨지면 발급 견적서의
카테고리 소계·합계가 조용히 틀린 값으로 나간다.

실제 법인 마스터 대신 같은 구조의 최소 시트를 만들어 쓴다 — 마스터 파일은 Storage에 있고
계속 손보는 중이라, 테스트가 그 파일의 현재 모양에 매이면 안 된다.
"""

import re
import sys
import zipfile
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.xlsx_rows import expand_sheet_rows, remap_cell_map

SHEET = "견적서"
SHEET_PATH = "xl/worksheets/sheet1.xml"

# 테스티파이 마케팅 시트와 같은 모양: 라벨행(소계 수식) + 항목행들 블록 2개, 그 아래 합계.
_ROWS = {
    15: '<c r="A15" t="inlineStr"><is><t>SEO</t></is></c><c r="H15"><f>SUM(H16:I17)</f><v>0</v></c>',
    16: '<c r="A16" t="inlineStr"><is><t>항목1</t></is></c><c r="H16"><f>E16*G16</f><v>0</v></c>',
    17: '<c r="A17" t="inlineStr"><is><t>항목2</t></is></c><c r="H17"><f>E17*G17</f><v>0</v></c>',
    18: '<c r="A18" t="inlineStr"><is><t>그로스</t></is></c><c r="H18"><f>SUM(H19:I20)</f><v>0</v></c>',
    19: '<c r="A19" t="inlineStr"><is><t>항목3</t></is></c><c r="H19"><f>E19*G19</f><v>0</v></c>',
    20: '<c r="A20" t="inlineStr"><is><t>항목4</t></is></c><c r="H20"><f>E20*G20</f><v>0</v></c>',
    21: '<c r="A21" t="inlineStr"><is><t>합계</t></is></c><c r="H21"><f>H15+H18</f><v>0</v></c>',
}
_MERGES = ["A15:B15", "A16:B16", "A17:B17", "A18:B18", "A19:B19", "A20:B20", "A21:B21"]


def _build_xlsx() -> bytes:
    rows = "".join(f'<row r="{r}" ht="20" customHeight="1">{cells}</row>' for r, cells in sorted(_ROWS.items()))
    merges = "".join(f'<mergeCell ref="{m}"/>' for m in _MERGES)
    sheet = (
        '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<dimension ref="A15:H21"/><sheetData>{rows}</sheetData>'
        f'<mergeCells count="{len(_MERGES)}">{merges}</mergeCells>'
        "</worksheet>"
    )
    workbook = (
        '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets><sheet name="{SHEET}" sheetId="1" r:id="rId1"/></sheets>'
        '<definedNames><definedName name="_xlnm.Print_Area" localSheetId="0">'
        f"{SHEET}!$A$1:$H$21</definedName></definedNames></workbook>"
    )
    out = BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr(SHEET_PATH, sheet)
        z.writestr("xl/workbook.xml", workbook)
    return out.getvalue()


def _read(data: bytes, name: str) -> str:
    with zipfile.ZipFile(BytesIO(data)) as z:
        return z.read(name).decode()


def _formulas(data: bytes) -> dict:
    xml = _read(data, SHEET_PATH)
    return {
        m.group(1): m.group(2)
        for m in re.finditer(r'<c r="([A-Z]+\d+)"[^>]*>(?:(?!</c>).)*?<f[^>]*>(.*?)</f>', xml, re.S)
    }


def _merges(data: bytes) -> list:
    return re.findall(r'<mergeCell ref="([^"]+)"/>', _read(data, SHEET_PATH))


def test_widening_a_block_extends_its_subtotal_range():
    """블록의 '끝에서 두 번째' 행을 복제하면 그 블록 소계 수식이 새 행까지 덮어야 한다."""
    grown, row_map = expand_sheet_rows(_build_xlsx(), SHEET_PATH, SHEET, [([16, 16], 16)])
    assert row_map[17] == 19 and row_map[21] == 23
    assert _formulas(grown)["H15"] == "SUM(H16:I19)", _formulas(grown)["H15"]


def test_rows_below_the_insert_point_move_down_with_their_formulas():
    grown, row_map = expand_sheet_rows(_build_xlsx(), SHEET_PATH, SHEET, [([16], 16)])
    formulas = _formulas(grown)
    assert formulas[f"H{row_map[18]}"] == f"SUM(H{row_map[19]}:I{row_map[20]})"
    assert formulas[f"H{row_map[21]}"] == f"H15+H{row_map[18]}"


def test_cloned_block_subtotal_points_at_its_own_rows():
    """블록을 통째로 복제하면 복제본의 소계 수식은 원본이 아니라 자기 행들을 합산해야 한다."""
    grown, _ = expand_sheet_rows(_build_xlsx(), SHEET_PATH, SHEET, [([18, 19, 20], 20)])
    formulas = _formulas(grown)
    assert formulas["H18"] == "SUM(H19:I20)", "원본 블록은 그대로여야 한다"
    assert formulas["H21"] == "SUM(H22:I23)", formulas["H21"]
    assert formulas["H24"] == "H15+H18", "합계 수식은 원본 블록만 가리킨 채 아래로 밀린다"


def test_merges_follow_the_rows():
    grown, _ = expand_sheet_rows(_build_xlsx(), SHEET_PATH, SHEET, [([16], 16)])
    merged = _merges(grown)
    assert "A17:B17" in merged, "복제된 행에도 같은 병합이 생겨야 한다"
    assert "A19:B19" in merged and "A22:B22" in merged, merged
    assert len(merged) == len(_MERGES) + 1


def test_print_area_grows():
    grown, row_map = expand_sheet_rows(_build_xlsx(), SHEET_PATH, SHEET, [([16, 16], 16)])
    assert f"$H${row_map[21]}" in _read(grown, "xl/workbook.xml")


def test_shared_formula_refs_do_not_double_shift_cells():
    """공유 수식(<f t="shared" si="0"/>)이 섞인 시트에서도 행 번호와 셀 좌표가 어긋나면 안 된다.

    자기닫힘 <f/>를 여는 태그로 오해하면 다음 </f>까지의 셀들이 수식 텍스트로 취급돼 좌표가
    두 번 밀린다 — 실제 테스티파이 마스터에서 표가 통째로 깨졌던 회귀(2026-08-19).
    """
    rows = {
        15: '<c r="A15"><f>SUM(H16:I17)</f><v>0</v></c>',
        16: '<c r="A16"><f t="shared" ref="A16:A17" si="0">E16*G16</f><v>0</v></c><c r="B16"><v>1</v></c>',
        17: '<c r="A17"><f t="shared" si="0"/><v>0</v></c><c r="B17"><v>1</v></c>',
        18: '<c r="A18"><v>9</v></c><c r="B18"><v>9</v></c>',
    }
    sheet = (
        '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<dimension ref="A15:B18"/><sheetData>'
        + "".join(f'<row r="{r}">{c}</row>' for r, c in sorted(rows.items()))
        + '</sheetData><mergeCells count="0"></mergeCells></worksheet>'
    )
    out = BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr(SHEET_PATH, sheet)
        z.writestr("xl/workbook.xml", '<?xml version="1.0"?><workbook><sheets/></workbook>')

    grown, _ = expand_sheet_rows(out.getvalue(), SHEET_PATH, SHEET, [([16], 16)])
    xml = _read(grown, SHEET_PATH)
    for m in re.finditer(r'<row r="(\d+)">(.*?)</row>', xml, re.S):
        row = m.group(1)
        coords = re.findall(r'<c r="([A-Z]+)(\d+)"', m.group(2))
        assert all(r == row for _c, r in coords), f"{row}행에 {coords} 좌표가 섞였다"


def test_remap_cell_map_moves_every_row_number():
    row_map = {r: (r + 2 if r > 22 else r) for r in range(1, 100)}
    cell_map = {
        "item_blocks": [{"category_label_cell": "A24", "rows": [25, 26, 27]}],
        "totals": {"subtotal_cell": "H31"},
        "columns": {"item_name": "A"},
    }
    out = remap_cell_map(cell_map, row_map)
    assert out["item_blocks"][0] == {"category_label_cell": "A26", "rows": [27, 28, 29]}
    assert out["totals"]["subtotal_cell"] == "H33"
    assert out["columns"]["item_name"] == "A", "열 문자만 있는 값은 건드리면 안 된다"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("모두 통과")