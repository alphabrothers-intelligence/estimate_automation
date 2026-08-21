"""마스터 xlsx의 항목 블록에 행을 실제로 끼워 넣는다 (PRD 4.4 — 화면/채팅으로 항목을 추가하면
PDF·xlsx에도 새 행이 생겨야 함, 2026-08-19 사용자 요청).

기존에는 cell_map의 item_blocks가 원본 파일에 물리적으로 존재하는 고정 행만 가리켰고, 항목이
그 칸 수를 넘으면 pdf_service._assign_groups_to_blocks가 422로 거절하거나 카테고리 소계 한 줄로
접어버렸다. 여기서는 Excel이 "행 삽입"할 때 하는 일을 시트 XML에 직접 한다:

- 삽입 지점 아래의 모든 행 번호와 셀 좌표를 밀고
- 수식 안의 셀 참조도 같이 밀어(=SUM(AA13:AD21) → =SUM(AA13:AD22)) 합계가 새 행을 포함하게 하고
- 병합셀·인쇄영역·이미지 앵커·하이퍼링크 좌표도 함께 밀고
- 삽입 지점 행을 통째로 복제해(서식·행높이·그 행의 병합까지) 새 행을 만든다

pdf_service가 이미 시트 XML을 문자열로 다루므로(도장 이미지 보존을 위해 openpyxl 저장을 쓰지
않음, 그 파일 상단 주석 참고) 같은 방식을 따른다.

ponytail: 수식 참조 시프트는 `[A-Z]{1,3}\\d+` 토큰 매칭이라, 수식 안 문자열 리터럴에 셀 좌표처럼
생긴 글자가 들어있으면(예: ="B31호") 같이 밀린다. 5개 법인 마스터의 실제 수식엔 그런 리터럴이
없는 걸 확인했다 — 생기면 그때 문자열 리터럴을 먼저 떼어내고 시프트할 것.
"""

import io
import re
import zipfile
from typing import Dict, List, Optional, Tuple

_ROW_TAG = re.compile(r'<row\b[^>]*\br="(\d+)"[^>]*?(?:/>|>)')
_CELL_REF_IN_FORMULA = re.compile(r"(\$?)([A-Z]{1,3})(\$?)(\d+)")

# 수식 본문이 있는 <f>...</f>만 고른다. 공유 수식 참조는 본문 없이 <f t="shared" si="0"/>로
# 자기닫힘인데, 이걸 걸러내지 않으면 `<f[^>]*>(.*?)</f>` 가 그 자기닫힘 태그를 여는 태그로 보고
# 다음 진짜 </f>까지(셀 수십 개 분량) 통째로 삼킨다 — 그 구간의 셀 좌표가 수식 텍스트로
# 취급돼 한 번 더 밀리면서 행 번호와 셀 좌표가 어긋났다(2026-08-19 재현).
_FORMULA_BODY = re.compile(r"<f\b(?![^>]*/>)[^>]*>(.*?)</f>", re.DOTALL)


def _shifter(after_row: int, count: int):
    return lambda row: row + count if row > after_row else row


def _shift_cell_refs(text: str, shift) -> str:
    """수식/좌표 문자열 안의 A1 형태 참조를 모두 옮긴다."""
    return _CELL_REF_IN_FORMULA.sub(
        lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}{shift(int(m.group(4)))}", text
    )


def _extract_row_xml(sheet_xml: str, row_num: int) -> str:
    """<row r="N">...</row> 한 덩어리를 그대로 떼어낸다 (자기닫힘 태그 포함)."""
    m = re.search(rf'<row\b[^>]*\br="{row_num}"[^>]*?(?:/>|>)', sheet_xml)
    if not m:
        raise ValueError(f"시트에 {row_num}행이 없습니다.")
    if m.group(0).endswith("/>"):
        return m.group(0)
    end = sheet_xml.index("</row>", m.end()) + len("</row>")
    return sheet_xml[m.start() : end]


def _renumber_row_xml(row_xml: str, from_row: int, to_row: int) -> str:
    """복제한 행 XML의 행 번호와 셀 좌표를 새 행 번호로 바꾼다.

    그 행 안의 수식이 자기 행을 가리키는 경우(예: AA13의 =X13*V13)도 같이 바꿔야 복제된 행이
    자기 값을 계산한다.
    """
    row_xml = re.sub(r'(<row\b[^>]*\br=")\d+(")', rf"\g<1>{to_row}\g<2>", row_xml, count=1)
    row_xml = re.sub(rf'(<c r="[A-Z]{{1,3}}){from_row}(")', rf"\g<1>{to_row}\g<2>", row_xml)
    # 수식 안의 참조는 Excel의 "행 복사"와 같이 상대 참조로 취급해 통째로 delta만큼 옮긴다.
    # 자기 행 참조만 바꾸면(예전 방식) 카테고리 소계처럼 아래 행 범위를 합산하는 수식
    # (=SUM(H29:I30))이 복제돼도 원본 블록을 계속 가리켜 엉뚱한 소계가 찍힌다(2026-08-19 확인).
    delta = to_row - from_row
    return _FORMULA_BODY.sub(
        lambda m: m.group(0).replace(m.group(1), _shift_cell_refs(m.group(1), lambda r: r + delta), 1),
        row_xml,
    )


def _shift_sheet_rows(sheet_xml: str, shift) -> str:
    """sheetData의 모든 <row>/<c> 좌표와 수식 참조를 옮긴다."""

    def fix_row(m: re.Match) -> str:
        tag = m.group(0)
        return re.sub(r'(\br=")\d+(")', rf"\g<1>{shift(int(m.group(1)))}\g<2>", tag, count=1)

    sheet_xml = _ROW_TAG.sub(fix_row, sheet_xml)
    sheet_xml = re.sub(
        r'<c r="([A-Z]{1,3})(\d+)"',
        lambda m: f'<c r="{m.group(1)}{shift(int(m.group(2)))}"',
        sheet_xml,
    )
    return _FORMULA_BODY.sub(
        lambda m: m.group(0).replace(m.group(1), _shift_cell_refs(m.group(1), shift), 1), sheet_xml
    )


def _shift_merges(sheet_xml: str, after_row: int, count: int) -> str:
    """병합 범위를 옮긴다. 삽입 지점을 걸치고 있는 병합(예: 구분(대)의 A13:B17에 14행 삽입)은
    끝 행만 밀려서 새 행까지 덮도록 자연히 늘어난다 — Excel의 행 삽입과 같은 동작."""
    shift = _shifter(after_row, count)

    def fix(m: re.Match) -> str:
        return f'ref="{_shift_cell_refs(m.group(1), shift)}"'

    return re.sub(r'ref="([A-Z$0-9:]+)"', fix, sheet_xml)


def _single_row_merges(sheet_xml: str, row_num: int) -> List[str]:
    """그 행 안에서 끝나는(가로 방향) 병합만 골라낸다 — 복제 행에 그대로 다시 만들어 줘야
    상품명·상품구성 칸이 원본과 같은 폭을 갖는다."""
    merges = re.findall(r'<mergeCell ref="([A-Z]{1,3})(\d+):([A-Z]{1,3})(\d+)"/>', sheet_xml)
    return [
        f"{c1}{{row}}:{c2}{{row}}"
        for c1, r1, c2, r2 in merges
        if int(r1) == row_num and int(r2) == row_num
    ]


def _add_merges(sheet_xml: str, refs: List[str]) -> str:
    if not refs:
        return sheet_xml
    m = re.search(r'<mergeCells count="(\d+)">', sheet_xml)
    if not m:
        return sheet_xml
    added = "".join(f'<mergeCell ref="{ref}"/>' for ref in refs)
    sheet_xml = sheet_xml[: m.end()] + added + sheet_xml[m.end() :]
    return re.sub(
        r'<mergeCells count="\d+">',
        f'<mergeCells count="{int(m.group(1)) + len(refs)}">',
        sheet_xml,
        count=1,
    )


def clone_rows(sheet_xml: str, source_rows: List[int], after_row: int) -> str:
    """source_rows를 순서대로 복제해 after_row 바로 아래에 끼워 넣는다.

    - 항목 행 늘리기: source_rows=[가운데행]*n, after_row=그 가운데행
    - 카테고리 블록 통째로 추가: source_rows=[라벨행, 항목행...], after_row=그 블록의 마지막 행

    복제 원본으로 "블록의 첫 행"이 아니라 가운데 행을 쓰면 표를 여닫는 테두리 서식을 건드리지
    않고, 블록 전체를 합산하는 수식(=SUM(AA13:AD21))도 삽입 지점이 범위 안이라 자동으로 늘어난다.
    source_rows는 모두 after_row 이하여야 한다(그래야 시프트에 휘둘리지 않는다).
    """
    if not source_rows:
        return sheet_xml
    count = len(source_rows)
    templates = [(_extract_row_xml(sheet_xml, r), _single_row_merges(sheet_xml, r), r) for r in source_rows]

    shift = _shifter(after_row, count)
    sheet_xml = _shift_merges(sheet_xml, after_row, count)
    sheet_xml = _shift_sheet_rows(sheet_xml, shift)

    new_rows = "".join(
        _renumber_row_xml(row_xml, src, after_row + i + 1) for i, (row_xml, _m, src) in enumerate(templates)
    )
    anchor = _extract_row_xml(sheet_xml, after_row)
    idx = sheet_xml.index(anchor) + len(anchor)
    sheet_xml = sheet_xml[:idx] + new_rows + sheet_xml[idx:]

    return _add_merges(
        sheet_xml,
        [ref.format(row=after_row + i + 1) for i, (_x, merges, _s) in enumerate(templates) for ref in merges],
    )


def _shift_drawing(drawing_xml: str, clone_row: int, count: int) -> str:
    """도장·로고 이미지 앵커를 밀어 원래 있던 셀 위에 그대로 남게 한다.
    xdr:row는 0-based라 (행번호-1) 기준으로 비교한다."""
    return re.sub(
        r"<xdr:row>(\d+)</xdr:row>",
        lambda m: f"<xdr:row>{int(m.group(1)) + count if int(m.group(1)) + 1 > clone_row else int(m.group(1))}</xdr:row>",
        drawing_xml,
    )


def _shift_defined_names(workbook_xml: str, sheet_name: str, clone_row: int, count: int) -> str:
    """인쇄영역(_xlnm.Print_Area)이 새 행까지 포함하도록 늘린다 — 안 늘리면 삽입된 행이
    PDF에서 잘려 나간다."""
    shift = _shifter(clone_row, count)

    def fix(m: re.Match) -> str:
        body = m.group(2)
        if sheet_name not in body:
            return m.group(0)
        return m.group(1) + _shift_cell_refs(body, shift) + m.group(3)

    return re.sub(
        r"(<definedName\b[^>]*>)(.*?)(</definedName>)", fix, workbook_xml, flags=re.DOTALL
    )


def expand_sheet_rows(
    source_bytes: bytes,
    sheet_path: str,
    sheet_name: str,
    jobs: List[Tuple[List[int], int]],
) -> Tuple[bytes, Dict[int, int]]:
    """xlsx 전체(zip)를 열어 지정한 시트에 행을 끼워 넣은 새 xlsx bytes를 돌려준다.

    jobs: [(복제할 원본 행 목록, 삽입 위치 행), ...]. 여러 곳에 삽입할 때 앞쪽 삽입이 뒤쪽 행
    번호를 밀어버리므로, 삽입 위치가 큰 곳부터 처리해 나머지 좌표가 흔들리지 않게 한다.

    반환하는 row_map은 "원본 행 번호 -> 삽입 후 행 번호"라, 호출부가 cell_map의 좌표를 그대로
    다시 계산할 수 있다.
    """
    jobs = [(rows, after) for rows, after in jobs if rows]

    with zipfile.ZipFile(io.BytesIO(source_bytes), "r") as zin:
        sheet_xml = zin.read(sheet_path).decode("utf-8")
        names = zin.namelist()
        workbook_xml = zin.read("xl/workbook.xml").decode("utf-8")
        drawing_paths = [n for n in names if re.fullmatch(r"xl/drawings/drawing\d+\.xml", n)]
        drawings = {p: zin.read(p).decode("utf-8") for p in drawing_paths}

        row_map = {r: r for r in range(1, 2000)}
        for source_rows, after_row in sorted(jobs, key=lambda j: j[1], reverse=True):
            n = len(source_rows)
            sheet_xml = clone_rows(sheet_xml, source_rows, after_row)
            workbook_xml = _shift_defined_names(workbook_xml, sheet_name, after_row, n)
            drawings = {p: _shift_drawing(x, after_row, n) for p, x in drawings.items()}
            shift = _shifter(after_row, n)
            row_map = {orig: shift(cur) for orig, cur in row_map.items()}

        sheet_xml = _fix_dimension(sheet_xml)

        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename == sheet_path:
                    data = sheet_xml.encode("utf-8")
                elif item.filename == "xl/workbook.xml":
                    data = workbook_xml.encode("utf-8")
                elif item.filename in drawings:
                    data = drawings[item.filename].encode("utf-8")
                zout.writestr(item, data)
    return out.getvalue(), row_map


def _fix_dimension(sheet_xml: str) -> str:
    rows = [int(m.group(1)) for m in _ROW_TAG.finditer(sheet_xml)]
    if not rows:
        return sheet_xml
    return re.sub(
        r'(<dimension ref="[A-Z]+\d+:[A-Z]+)\d+(")', rf"\g<1>{max(rows)}\g<2>", sheet_xml, count=1
    )


def remap_cell_map(cell_map: dict, row_map: Dict[int, int]) -> dict:
    """cell_map 안의 모든 행 번호를 삽입 후 좌표로 바꾼다."""

    def remap_coord(coord: str) -> str:
        m = re.fullmatch(r"([A-Z]{1,3})(\d+)", coord)
        return f"{m.group(1)}{row_map.get(int(m.group(2)), int(m.group(2)))}" if m else coord

    def walk(node):
        if isinstance(node, dict):
            return {k: (walk(v) if k != "rows" else [row_map.get(r, r) for r in v]) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v) for v in node]
        if isinstance(node, str):
            return remap_coord(node)
        return node

    return walk(cell_map)
