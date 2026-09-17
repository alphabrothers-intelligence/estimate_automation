"""인쇄영역이 도장을 덮는지 자체 점검 — `python backend/tests/test_print_area_drawings.py`.

셀 내용만 보고 인쇄영역을 정하면, 셀 바깥으로 튀어나온 도장이 PDF에서 잘린다(블렌디드랩
직인이 오른쪽 절반을 잃은 사고, 2026-09-17). 고객에게 그대로 나가는 부분이라 여기가 깨지면
바로 사고다.

실제 법인 마스터 대신 같은 구조의 최소 파일을 만들어 쓴다 — 마스터는 Storage에 있고 계속
손보는 중이라 테스트가 그 파일의 현재 모양에 매이면 안 된다.
"""

import io
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.pdf_service import _drawing_bounds, _fix_broken_print_area

# 셀 내용은 AF(32열)에서 끝나지만 도장은 AF~AH에 걸쳐 있는 시트 — 블렌디드랩 마스터와 같은 모양.
SHEET_XML = (
    '<worksheet><sheetData><row r="7"><c r="AF7" t="s"><v>0</v></c></row></sheetData>'
    '<drawing r:id="rId1"/></worksheet>'
)
SHEET_RELS = (
    '<Relationships><Relationship Id="rId1" Target="../drawings/drawing1.xml"/></Relationships>'
)
# .xls에서 변환되며 인쇄영역이 NA()로 깨진 워크북.
WORKBOOK_XML = (
    '<workbook><sheets><sheet name="견적서" sheetId="1" r:id="rId3"/></sheets><definedNames>'
    '<definedName localSheetId="0" name="Excel_BuiltIn_Print_Area">NA()</definedName>'
    "</definedNames></workbook>"
)


def _drawing_xml(to_col: int, col_off: int) -> str:
    return (
        "<xdr:wsDr><xdr:twoCellAnchor>"
        "<xdr:from><xdr:col>31</xdr:col><xdr:colOff>0</xdr:colOff>"
        "<xdr:row>6</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:from>"
        f"<xdr:to><xdr:col>{to_col}</xdr:col><xdr:colOff>{col_off}</xdr:colOff>"
        "<xdr:row>7</xdr:row><xdr:rowOff>259560</xdr:rowOff></xdr:to>"
        "</xdr:twoCellAnchor></xdr:wsDr>"
    )


def _zip_with(drawing_xml: str) -> zipfile.ZipFile:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/worksheets/sheet1.xml", SHEET_XML)
        z.writestr("xl/worksheets/_rels/sheet1.xml.rels", SHEET_RELS)
        z.writestr("xl/drawings/drawing1.xml", drawing_xml)
    return zipfile.ZipFile(buf)


def test_stamp_columns_are_inside_print_area():
    with _zip_with(_drawing_xml(to_col=33, col_off=360)) as z:
        bounds = _drawing_bounds(z, "xl/worksheets/sheet1.xml")

    # 도장이 AG(33열)까지 덮는다 — 끝 오프셋 360 EMU(0.01mm)는 AH 경계에 붙은 반올림 찌꺼기라
    # AH까지 끌어들이지 않는다(빈 열이 붙으면 fitToWidth가 견적서를 그만큼 축소한다).
    assert bounds == (33, 8), bounds

    fixed = _fix_broken_print_area(WORKBOOK_XML, SHEET_XML, "견적서", bounds)
    area = re.search(r'name="_xlnm\.Print_Area"[^>]*>([^<]*)<', fixed).group(1)
    assert area == "'견적서'!$A$1:$AG$8", area


def test_offset_past_a_pixel_pulls_in_the_next_column():
    # 도장이 AH 안쪽으로 눈에 띄게 들어와 있으면 그 열까지 인쇄영역에 넣는다.
    with _zip_with(_drawing_xml(to_col=33, col_off=200000)) as z:
        assert _drawing_bounds(z, "xl/worksheets/sheet1.xml") == (34, 8)


def test_sheet_without_drawing_changes_nothing():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/worksheets/sheet1.xml", "<worksheet><sheetData/></worksheet>")
    with zipfile.ZipFile(buf) as z:
        assert _drawing_bounds(z, "xl/worksheets/sheet1.xml") == (0, 0)


if __name__ == "__main__":
    test_stamp_columns_are_inside_print_area()
    test_offset_past_a_pixel_pulls_in_the_next_column()
    test_sheet_without_drawing_changes_nothing()
    print("ok")
