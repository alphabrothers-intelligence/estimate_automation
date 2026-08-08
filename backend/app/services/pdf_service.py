"""Phase 5 — 마스터 xlsx의 가변 셀만 채운 뒤 LibreOffice headless로 PDF 변환한다 (PRD 4.2, 7장).

법인 고정정보(로고·도장·사업자정보·문구)는 원본 파일 안에 이미 있으므로 절대 건드리지 않는다
(CLAUDE.md 2장). 이 서비스는 QuoteTemplate.cell_map이 가리키는 가변 셀(수신자·견적일자·용역명·
항목·단가·작업일·수량·공급가액)만 채운다. 합계/부가세처럼 원본에 수식으로 들어있는 셀은
건드리지 않고 LibreOffice 변환 시 자동 재계산되게 둔다.

openpyxl로 통째로 열고 다시 저장하면 이 파일들의 도장 이미지(DrawingML picture)가 유실되는
것을 확인했다(openpyxl 3.1.5가 이 드로잉을 읽어들이지 못함 — `ws._images`가 로드 직후부터 빈
배열). 그래서 openpyxl로 저장하지 않고, xlsx(zip) 안의 대상 시트 XML만 문자열 치환으로 직접
고쳐서 나머지 파일(도장 이미지·드로잉·다른 시트)은 원본 바이트 그대로 보존한다.
"""

import io
import re
import subprocess
import tempfile
import zipfile
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional
from xml.sax.saxutils import escape

from fastapi import HTTPException

from app.config import get_supabase
from app.services import template_storage

CellUpdates = Dict[str, Any]  # 셀 좌표("H16") -> 값(str|int|float|None). None이면 값을 비운다.


def _cell_pattern(coord: str) -> re.Pattern:
    return re.compile(rf'<c r="{re.escape(coord)}"([^>]*?)(/>|>(.*?)</c>)', re.DOTALL)


def _has_formula(inner: str) -> bool:
    return "<f>" in inner or "<f " in inner or "<f/>" in inner


def _build_cell_xml(coord: str, attrs: str, value: Any) -> str:
    style_match = re.search(r'\ss="(\d+)"', attrs)
    style_attr = f' s="{style_match.group(1)}"' if style_match else ""

    if value is None:
        return f'<c r="{coord}"{style_attr}/>'
    if isinstance(value, (int, float)):
        return f'<c r="{coord}"{style_attr}><v>{value}</v></c>'
    text = escape(str(value))
    return f'<c r="{coord}"{style_attr} t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'


def _strip_cached_formula_value(coord: str, attrs: str, inner: str) -> str:
    # <f>(공식 텍스트가 있든, t="shared" si="0"처럼 공유 공식 참조든)는 그대로 두고, 캐시된
    # <v>결과값</v>만 지운다 — 캐시를 남겨두면 LibreOffice가 재계산 없이 원본 발급 이력의
    # 이전 값(주로 0)을 그대로 PDF에 찍어내는 것을 확인했다.
    stripped = re.sub(r"<v>.*?</v>", "", inner, flags=re.DOTALL)
    return f'<c r="{coord}"{attrs}>{stripped}</c>'


def _patch_sheet_xml(xml_text: str, updates: CellUpdates) -> str:
    for coord, value in updates.items():
        m = _cell_pattern(coord).search(xml_text)
        if not m:
            raise HTTPException(status_code=500, detail=f"셀 매핑 오류: 시트에서 {coord} 셀을 찾지 못했습니다.")
        attrs, inner = m.group(1), (m.group(3) or "")
        if _has_formula(inner):
            replacement = _strip_cached_formula_value(coord, attrs, inner)
        else:
            replacement = _build_cell_xml(coord, attrs, value)
        xml_text = xml_text[: m.start()] + replacement + xml_text[m.end() :]
    return xml_text


def _sheet_internal_path(zin: zipfile.ZipFile, sheet_name: str) -> str:
    workbook_xml = zin.read("xl/workbook.xml").decode("utf-8")
    rels_xml = zin.read("xl/_rels/workbook.xml.rels").decode("utf-8")

    sheet_match = re.search(rf'<sheet[^>]*name="{re.escape(sheet_name)}"[^>]*r:id="(rId\d+)"', workbook_xml)
    if not sheet_match:
        raise HTTPException(status_code=500, detail=f"워크북에서 시트 '{sheet_name}'를 찾지 못했습니다.")
    rid = sheet_match.group(1)
    rel_match = re.search(rf'<Relationship Id="{rid}"[^>]*Target="([^"]+)"', rels_xml)
    if not rel_match:
        raise HTTPException(status_code=500, detail=f"관계 정의에서 {rid}를 찾지 못했습니다.")
    return "xl/" + rel_match.group(1).lstrip("/")


def _remove_other_sheets(workbook_xml: str) -> tuple[str, int]:
    """지금 발급할 시트 하나만 남기고 워크북에서 나머지 <sheet> 정의를 지운다.

    <sheet>를 그대로 두고 state="veryHidden"만 주는 방식은 LibreOffice --convert-to pdf가
    숨김 시트도 그대로 내보내서 효과가 없었다 — 실제로 정의 자체를 지워야 한다. 그러면
    definedNames(예: Print_Area)의 localSheetId가 남은 시트를 가리키도록 다시 계산해야 한다
    (localSheetId는 <sheets> 목록의 0-based 인덱스라서 지운 시트 뒤로는 번호가 밀린다).
    """
    sheet_tags = re.findall(r"<sheet\b[^>]*/>", workbook_xml)
    if len(sheet_tags) <= 1:
        return workbook_xml, 0

    keep_index = 0  # 이 함수를 부르기 전에 이미 대상 시트가 첫 번째가 되도록 재배치해서 넘긴다
    kept_tag = sheet_tags[keep_index]
    workbook_xml = re.sub(r"<sheets>.*?</sheets>", f"<sheets>{kept_tag}</sheets>", workbook_xml, flags=re.DOTALL)

    def _fix_defined_name(m: re.Match) -> str:
        tag = m.group(0)
        ls_match = re.search(r'localSheetId="(\d+)"', tag)
        if not ls_match:
            return tag  # 워크북 전체 범위 이름(시트 지정 없음)은 그대로 둔다
        if int(ls_match.group(1)) != keep_index:
            return ""  # 지워진 시트를 가리키던 이름(예: 다른 시트의 Print_Area)은 함께 지운다
        return re.sub(r'localSheetId="\d+"', 'localSheetId="0"', tag)

    workbook_xml = re.sub(r"<definedName\b[^>]*>.*?</definedName>", _fix_defined_name, workbook_xml, flags=re.DOTALL)
    return workbook_xml, keep_index


def _reorder_sheet_first(workbook_xml: str, sheet_name: str) -> str:
    """대상 시트가 <sheets> 목록의 첫 번째가 되도록 순서를 바꾸고, definedName들의
    localSheetId(옛 순서 기준 0-based 인덱스)도 새 순서에 맞게 다시 계산한다.

    이 리맵을 빠뜨리면(과거 버전의 버그, 2026-08-07 발견) 뒤따르는 _remove_other_sheets가
    "localSheetId=0은 곧 대상 시트"라고 가정하는데, 대상 시트가 원래 0번째가 아니었던
    경우(예: 알파브라더스 FGI는 원래 1번째) 엉뚱하게 원래 0번째였던 시트의 인쇄영역을
    "대상 시트 것"으로 착각해 살려두고 실제 대상 시트의 정의는 지워버린다 — 결과물 워크북에
    존재하지 않는 시트 이름을 가리키는 인쇄영역이 남아, LibreOffice가 그 시트의 서식 적용을
    포기하고 날짜 등 숫자 서식 셀을 원시값 그대로 찍어내는 등 예측 불가능하게 동작한다.
    """
    sheet_tags = re.findall(r"<sheet\b[^>]*/>", workbook_xml)
    target_idx = next((i for i, t in enumerate(sheet_tags) if f'name="{sheet_name}"' in t), None)
    if target_idx is None:
        raise HTTPException(status_code=500, detail=f"워크북에서 시트 '{sheet_name}'를 찾지 못했습니다.")
    target = sheet_tags[target_idx]
    reordered = [target] + [t for i, t in enumerate(sheet_tags) if i != target_idx]
    workbook_xml = re.sub(r"<sheets>.*?</sheets>", "<sheets>" + "".join(reordered) + "</sheets>", workbook_xml, flags=re.DOTALL)

    old_to_new = {target_idx: 0}
    new_i = 1
    for old_i in range(len(sheet_tags)):
        if old_i == target_idx:
            continue
        old_to_new[old_i] = new_i
        new_i += 1

    def _remap_defined_name(m: re.Match) -> str:
        tag = m.group(0)
        ls_match = re.search(r'localSheetId="(\d+)"', tag)
        if not ls_match:
            return tag
        new_id = old_to_new.get(int(ls_match.group(1)))
        if new_id is None:
            return tag
        return re.sub(r'localSheetId="\d+"', f'localSheetId="{new_id}"', tag)

    return re.sub(r"<definedName\b[^>]*>.*?</definedName>", _remap_defined_name, workbook_xml, flags=re.DOTALL)


def _strip_calc_chain(content_types_xml: str, workbook_rels_xml: str) -> tuple[str, str]:
    # calcChain은 재계산 성능 힌트일 뿐이라 지워도 안전하고, 시트를 지운 뒤 남아있으면
    # (다른 시트의 셀을 가리키던 항목들이 있어) 파일이 깨질 위험이 있어 아예 제거한다.
    content_types_xml = re.sub(r'<Override[^>]*calcChain[^>]*/>', "", content_types_xml)
    workbook_rels_xml = re.sub(r'<Relationship[^>]*calcChain[^>]*/>', "", workbook_rels_xml)
    return content_types_xml, workbook_rels_xml


def _force_full_recalc(workbook_xml: str) -> str:
    # LibreOffice headless --convert-to pdf가 이 플래그를 실제로 지키지는 않는 것으로
    # 확인됐지만(아래 _strip_all_formula_caches가 실질적인 수정), 다른 뷰어(엑셀 등)로 열 때
    # 캐시된 값 대신 항상 재계산되도록 표준에 맞게 남겨둔다.
    if re.search(r"<calcPr\b[^>]*\bfullCalcOnLoad=", workbook_xml):
        return workbook_xml
    if "<calcPr" in workbook_xml:
        return re.sub(r"<calcPr\b", '<calcPr fullCalcOnLoad="1" ', workbook_xml, count=1)
    return re.sub(r"</workbook>", '<calcPr fullCalcOnLoad="1"/></workbook>', workbook_xml)


_ANY_CELL_PATTERN = re.compile(r'<c r="[A-Z]+\d+"([^>]*?)(/>|>(.*?)</c>)', re.DOTALL)


def _strip_all_formula_caches(sheet_xml: str) -> str:
    # fullCalcOnLoad로도 LibreOffice headless 변환이 수식을 재계산하지 않는 걸 확인했다 —
    # 우리가 직접 값을 써넣은 셀만이 아니라, 그 셀을 참조하는 다른 수식(예: 총계 행의
    # SUM(R13:T22)처럼 터치한 셀 범위를 합산하는 수식)도 캐시된 값을 그대로 PDF에 찍어낸다.
    # 그래서 대상 시트의 모든 수식 셀의 캐시를 지워, 어떤 수식이든 강제로 재계산되게 한다.
    def _strip(m: re.Match) -> str:
        coord_match = re.match(r'<c r="([A-Z]+\d+)"', m.group(0))
        coord = coord_match.group(1)
        attrs, inner = m.group(1), (m.group(3) or "")
        if not _has_formula(inner):
            return m.group(0)
        return _strip_cached_formula_value(coord, attrs, inner)

    return _ANY_CELL_PATTERN.sub(_strip, sheet_xml)


# 2026-08-08: 진짜 맑은고딕(MS Office 번들의 malgun.ttf 등)을 /Library/Fonts에 시스템 전역
# 설치했다(사용자 결정 — 이전에는 ~/Library/Fonts 사용자 폰트로만 설치했다가 LibreOffice가
# 못 찾는 걸 확인해서 재설치). 그런데도 테스티파이 마스터만 여전히 못 찾는 걸 재확인했고,
# 원인을 찾아보니 이 파일의 <font> 정의가 <family val="2"/>(Swiss/고딕류 힌트)인데 실제로
# 문제없이 찾아지는 다른 법인 파일들은 <family val="3"/>(Modern)이었다 — family 힌트를
# 3으로 맞춰주면 LibreOffice가 정상적으로 실제 맑은고딕을 찾는 걸 직접 확인했다. 그래서 이제
# 폰트 이름 자체는 치환하지 않고(진짜 맑은고딕을 그대로 씀), 이 family 힌트만 정규화한다.
# "바탕"/"바탕체"(Batang, Windows 전용 명조체)는 이 Mac에 실제 폰트가 없어 macOS 기본
# 명조 폰트(AppleMyungjo)로 이름을 치환하는 것만 그대로 유지한다.
_BATANG_SUBSTITUTIONS = {"바탕체": "AppleMyungjo", "바탕": "AppleMyungjo"}
_FONT_ELEMENT_PATTERN = re.compile(r"<font>.*?</font>", re.DOTALL)
_FONT_NAME_PATTERN = re.compile(r'<name val="([^"]*)"/>')


def _patch_font_substitution(styles_xml: str) -> str:
    def _fix_font(m: re.Match) -> str:
        font_xml = m.group(0)
        name_match = _FONT_NAME_PATTERN.search(font_xml)
        if not name_match:
            return font_xml
        original = name_match.group(1)
        if original.startswith("맑은 고딕"):
            # family 힌트만 3(Modern)으로 맞춘다 — 이름은 실제 설치된 폰트와 동일하게 유지.
            return re.sub(r'family val="\d"', 'family val="3"', font_xml, count=1)
        for prefix, replacement in _BATANG_SUBSTITUTIONS.items():
            if original.startswith(prefix):
                return font_xml.replace(f'<name val="{original}"/>', f'<name val="{replacement}"/>')
        return font_xml

    return _FONT_ELEMENT_PATTERN.sub(_fix_font, styles_xml)


def _force_fit_to_page(sheet_xml: str) -> str:
    # 블렌디드랩 마스터처럼 pageSetup에 fitToWidth/fitToHeight=1은 있는데 정작 sheetPr의
    # fitToPage가 false라 무시되고, 인쇄영역도 안 잡혀 있어 시트 전체 폭(B:GG 등)이 여러 장으로
    # 쪼개져 나오는 경우가 있었다(2026-07-10). 회사 고정정보(로고·도장·문구)와 무관한 순수
    # 인쇄 레이아웃 설정이라, 항상 한 페이지에 맞게 축소 출력되도록 강제한다.
    if re.search(r"<pageSetUpPr\b[^>]*\bfitToPage=\"true\"", sheet_xml):
        return sheet_xml
    if re.search(r"<pageSetUpPr\b", sheet_xml):
        return re.sub(r'fitToPage="false"', 'fitToPage="true"', sheet_xml, count=1)
    if re.search(r"<sheetPr\b[^>]*>", sheet_xml) and "<pageSetUpPr" not in sheet_xml:
        return re.sub(
            r"(<sheetPr\b[^>]*>)", r'\1<pageSetUpPr fitToPage="true"/>', sheet_xml, count=1
        )
    if "<sheetPr" not in sheet_xml:
        return re.sub(
            r"(<worksheet\b[^>]*>)",
            r'\1<sheetPr><pageSetUpPr fitToPage="true"/></sheetPr>',
            sheet_xml,
            count=1,
        )
    return sheet_xml


def _compute_content_bounds(sheet_xml: str) -> tuple[int, int]:
    """실제 내용이 있는 셀들의 최대 열/행을 계산한다. 나머지 내용과 10열 이상 떨어진 낙오 셀은
    (예: 블렌디드랩 마스터의 GG1 — 실제 내용은 ~AF열까지인데 189번째 열에 의미 없는 글자 하나가
    남아있었음) 인쇄 레이아웃을 깨뜨리는 노이즈로 보고 제외한다."""
    refs = re.findall(r'<c r="([A-Z]+)(\d+)"', sheet_xml)

    def _colnum(col: str) -> int:
        n = 0
        for ch in col:
            n = n * 26 + (ord(ch) - 64)
        return n

    cols = sorted(set(_colnum(c) for c, _ in refs))
    max_col = cols[0] if cols else 1
    for c in cols:
        if c - max_col > 10:
            break
        max_col = c
    rows = [int(r) for c, r in refs if _colnum(c) <= max_col]
    return max_col, (max(rows) if rows else 1)


def _colname(n: int) -> str:
    s = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        s = chr(65 + rem) + s
    return s


def _has_working_print_area(workbook_xml: str) -> bool:
    m = re.search(
        r'<definedName\b[^>]*localSheetId="0"[^>]*name="_xlnm\.Print_Area"[^>]*>([^<]*)</definedName>',
        workbook_xml,
    )
    return bool(m and m.group(1).strip() and m.group(1).strip() != "NA()")


def _fix_broken_print_area(workbook_xml: str, sheet_xml: str, sheet_name: str) -> str:
    """정상 동작하는 인쇄영역이 있으면 손대지 않는다(대부분의 법인 원본 xlsx는 이미 제대로 된
    _xlnm.Print_Area를 갖고 있음). 블렌디드랩처럼 .xls에서 변환되면서 인쇄영역이
    "Excel_BuiltIn_Print_Area"라는 이름에 값이 NA()로 깨진 채로 남은 경우에만, 실제 내용 범위로
    새 인쇄영역을 지정한다 — 이게 없으면 LibreOffice가 낙오 셀까지 포함한 시트 전체 사용범위를
    한 페이지에 욱여넣으려다 내용이 구석에 작게 찍히고 빈 페이지가 추가로 생긴다."""
    if _has_working_print_area(workbook_xml):
        return workbook_xml

    max_col, max_row = _compute_content_bounds(sheet_xml)
    quoted_name = sheet_name.replace("'", "''")
    print_range = f"'{quoted_name}'!$A$1:${_colname(max_col)}${max_row}"
    new_defined_name = (
        f'<definedName function="false" hidden="false" localSheetId="0" '
        f'name="_xlnm.Print_Area" vbProcedure="false">{escape(print_range)}</definedName>'
    )

    # 이 시트를 가리키던 기존 Print_Area류 정의(정상/깨짐 상관없이)는 지우고 하나만 새로 넣는다.
    workbook_xml = re.sub(
        r'<definedName\b[^>]*localSheetId="0"[^>]*name="(?:_xlnm\.Print_Area|Excel_BuiltIn_Print_Area)"'
        r'[^>]*>.*?</definedName>',
        "",
        workbook_xml,
        flags=re.DOTALL,
    )
    if "<definedNames>" in workbook_xml:
        return re.sub(r"</definedNames>", new_defined_name + "</definedNames>", workbook_xml, count=1)
    return re.sub(r"(</sheets>)", r"\1<definedNames>" + new_defined_name + "</definedNames>", workbook_xml, count=1)


def _patch_xlsx(source_bytes: bytes, sheet_name: str, updates: CellUpdates, dest_path: Path) -> None:
    with zipfile.ZipFile(io.BytesIO(source_bytes), "r") as zin:
        sheet_path = _sheet_internal_path(zin, sheet_name)
        sheet_xml = zin.read(sheet_path).decode("utf-8")
        patched_sheet_xml = _patch_sheet_xml(sheet_xml, updates)
        patched_sheet_xml = _strip_all_formula_caches(patched_sheet_xml)
        patched_sheet_xml = _force_fit_to_page(patched_sheet_xml)

        workbook_xml = zin.read("xl/workbook.xml").decode("utf-8")
        workbook_xml = _reorder_sheet_first(workbook_xml, sheet_name)
        workbook_xml, _ = _remove_other_sheets(workbook_xml)
        workbook_xml = _fix_broken_print_area(workbook_xml, patched_sheet_xml, sheet_name)
        patched_workbook_xml = _force_full_recalc(workbook_xml)

        content_types_xml = zin.read("[Content_Types].xml").decode("utf-8")
        workbook_rels_xml = zin.read("xl/_rels/workbook.xml.rels").decode("utf-8")
        patched_content_types, patched_workbook_rels = _strip_calc_chain(content_types_xml, workbook_rels_xml)

        styles_xml = zin.read("xl/styles.xml").decode("utf-8")
        patched_styles_xml = _patch_font_substitution(styles_xml)

        skip_files = {"xl/calcChain.xml"}
        with zipfile.ZipFile(dest_path, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                if item.filename in skip_files:
                    continue
                data = zin.read(item.filename)
                if item.filename == sheet_path:
                    data = patched_sheet_xml.encode("utf-8")
                elif item.filename == "xl/workbook.xml":
                    data = patched_workbook_xml.encode("utf-8")
                elif item.filename == "[Content_Types].xml":
                    data = patched_content_types.encode("utf-8")
                elif item.filename == "xl/_rels/workbook.xml.rels":
                    data = patched_workbook_rels.encode("utf-8")
                elif item.filename == "xl/styles.xml":
                    data = patched_styles_xml.encode("utf-8")
                zout.writestr(item, data)


def _read_sheet_xml(source_bytes: bytes, sheet_name: str) -> str:
    with zipfile.ZipFile(io.BytesIO(source_bytes), "r") as zin:
        sheet_path = _sheet_internal_path(zin, sheet_name)
        return zin.read(sheet_path).decode("utf-8")


def _formula_references_column(sheet_xml: str, coord: str, col_letter: str) -> bool:
    # 같은 "공급가액" 수식이라도 시트마다 SUM(T13*V13*X13)(작업일*수량*단가)이거나
    # SUM(V13*X13)(수량*단가, 작업일 제외)일 수 있다 — 알파브라더스는 개별 모듈 시트(FGI 등)는
    # 작업일을 곱하지만 "통합 패키지" 요약 시트는 작업일을 곱하지 않는다(원본 마스터 파일의
    # 실제 수식 차이, 데이터 오류 아님). 그래서 단가를 역산할 때 실제 수식이 어느 컬럼을
    # 참조하는지 직접 읽어서 나눗셈 인자를 맞춘다.
    if not col_letter:
        return False
    m = _cell_pattern(coord).search(sheet_xml)
    if not m:
        return False
    inner = m.group(3) or ""
    f_match = re.search(r"<f[^>]*>(.*?)</f>", inner, re.DOTALL)
    if not f_match:
        return False
    return bool(re.search(rf"\b{re.escape(col_letter)}\d+\b", f_match.group(1)))


def _lookup_work_days_quantity(
    supabase, catalog_entity_id: str, task_type: str, module_name: str, item_name: str
) -> tuple[float, float]:
    res = (
        supabase.table("item_catalogs")
        .select("module_name, work_days, quantity")
        .eq("entity_id", catalog_entity_id)
        .eq("task_type", task_type)
        .eq("item_name", item_name)
        .eq("is_current", True)
        .execute()
    )
    if not res.data:
        return 1.0, 1.0
    exact = [r for r in res.data if r["module_name"] == module_name]
    row = exact[0] if exact else res.data[0]
    return float(row["work_days"]), float(row["quantity"])


def get_column_display(supabase, entity_id: str, task_type: str, selected_modules: Optional[list]) -> Dict[str, Any]:
    """미리보기 UI가 법인마다 다른 실제 원본 양식 그대로 컬럼명·순서를 보여주기 위한 정보를
    반환한다(2026-07-10 — 같은 의미라도 법인마다 명칭이 다름: 예) 작업일/소요일, 수량/작업수량).
    템플릿을 못 찾는 경우(러프 비교견적 등)는 실패시키지 않고 빈 값으로 대체한다."""
    try:
        template = _find_quote_template(supabase, entity_id, task_type, selected_modules)
    except HTTPException:
        return {"column_labels": {}, "detail_column_order": []}
    cell_map = template["cell_map"]
    return {
        "column_labels": cell_map.get("column_labels", {}),
        "detail_column_order": cell_map.get("detail_column_order", []),
    }


def _find_quote_template(supabase, entity_id: str, task_type: str, selected_modules: Optional[list]) -> dict:
    res = (
        supabase.table("quote_templates")
        .select("*")
        .eq("entity_id", entity_id)
        .eq("task_type", task_type)
        .execute()
    )
    rows = res.data
    if not rows:
        raise HTTPException(status_code=404, detail="이 법인·과업종류에 대한 견적서 양식을 찾을 수 없습니다.")
    if len(rows) == 1:
        return rows[0]
    selected_set = set(selected_modules or [])
    for row in rows:
        if row["module_name"] and row["module_name"] in selected_set:
            return row
    return rows[0]


def _collect_header_updates(header_fields: Dict[str, str], quote: dict) -> CellUpdates:
    updates: CellUpdates = {}
    quote_date = quote.get("quote_date")
    if isinstance(quote_date, str):
        quote_date = date.fromisoformat(quote_date)
    quote_date = quote_date or date.today()

    for field, coord in header_fields.items():
        if field == "quote_year":
            # 테스티파이 마스터는 이 셀 자체가 "년"으로 끝나는 문구다("2026년") — 숫자만 쓰면
            # 접미사가 지워진다.
            updates[coord] = f"{quote_date.year}년"
        elif field == "quote_month":
            updates[coord] = f"{quote_date.month}월"
        elif field == "quote_day":
            updates[coord] = f"{quote_date.day}일"
        elif field == "quote_date":
            # ABBG 마스터는 이 셀이 "YYYY-MM-DD" 형태의 텍스트 플레이스홀더라 ISO 문자열이 맞다.
            updates[coord] = quote_date.isoformat()
        elif field == "quote_date_serial":
            # 알파브라더스·썬데이워커 마스터는 이 셀이 엑셀 날짜 일련번호(숫자)이고, 셀 서식이
            # 알아서 "2024-07-15"처럼 보여준다 — 문자열을 쓰면 서식이 무시되고 그대로 찍힌다.
            updates[coord] = (quote_date - date(1899, 12, 30)).days
        elif field == "quote_code":
            updates[coord] = f"{quote_date:%Y%m%d}-{quote['id'][:6].upper()}"
        elif field == "recipient_name":
            # 테스티파이 마스터는 이 셀 자체가 "OOO 귀하" 형태다 — 이름만 쓰면 "귀하"가 지워진다.
            updates[coord] = f"{quote.get('recipient_name') or ''} 귀하"
        elif field in ("client_name", "client_company"):
            updates[coord] = quote.get("recipient_name") or ""
        elif field == "service_name":
            updates[coord] = quote.get("service_name") or ""
        elif field == "recipient_block":
            updates[coord] = (
                f"수신자 : {quote.get('recipient_name') or ''}\n\n아래와 같이 견적서를 발송합니다.\n\n"
                f"{quote_date.year}년 {quote_date.month}월 {quote_date.day}일"
            )
        # validity_text 등 우리 데이터에 대응 값이 없는 필드는 건드리지 않는다(원본 값 유지)
    return updates


def _group_line_items(line_items: List[dict]) -> List[Dict[str, Any]]:
    groups: List[Dict[str, Any]] = []
    for item in line_items:
        if groups and groups[-1]["category"] == item["category"]:
            groups[-1]["items"].append(item)
            groups[-1]["amount"] += item["amount"]
        else:
            groups.append({"category": item["category"], "amount": item["amount"], "items": [item]})
    return groups


def _rollup_to_category_totals(groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """카테고리별 세부 항목을 카테고리당 한 줄(소계)로 합친다.

    썬데이워커 마케팅처럼 카탈로그가 테스티파이 것을 그대로 빌려써서 세부 항목이 12개인데
    실제 양식(플랫 블록)은 6줄뿐인 경우처럼, 세부 항목 그대로는 절대 못 담는 조합에 대한
    최후 수단이다 — 세부 항목 대신 카테고리 소계만이라도 담는다."""
    return [
        {
            "category": g["category"],
            "amount": g["amount"],
            "items": [{"category": g["category"], "name": g["category"], "amount": g["amount"]}],
        }
        for g in groups
    ]


def _try_assign_flat(groups: List[Dict[str, Any]], flat_blocks: List[dict]) -> Optional[List[tuple]]:
    assignments: List[tuple] = []
    block_idx = 0
    row_offset = 0
    for group in groups:
        while block_idx < len(flat_blocks) and row_offset + len(group["items"]) > len(flat_blocks[block_idx]["rows"]):
            block_idx += 1
            row_offset = 0
        if block_idx >= len(flat_blocks):
            return None
        assignments.append((flat_blocks[block_idx], group, row_offset))
        row_offset += len(group["items"])
    return assignments


def _assign_groups_to_blocks(groups: List[Dict[str, Any]], blocks: List[dict]) -> List[tuple]:
    """카테고리(그룹)를 양식 블록의 행에 배정한다. 반환값: [(block, group, row_offset), ...]

    category_label_cell이 있는 블록은 원본 양식이 카테고리별 전용 영역(헤더+소계)을 갖는다는
    뜻이라 카테고리 1개당 블록 1개씩 배정한다(기존 동작). 헤더 셀이 없는 "플랫" 블록(예:
    블렌디드랩 — 카테고리 구분 없이 항목을 그냥 나열하는 양식)은 여러 카테고리를 같은 블록 행에
    순서대로 나눠 채운다(그룹을 블록 경계에서 쪼개지는 않는다 — 실제 데이터에서 한 카테고리가
    플랫 블록 하나의 남은 자리보다 커서 쪼개야 했던 사례가 없어 그 경우까지는 다루지 않는다).
    세부 항목 그대로 넣으면 자리가 모자랄 땐(예: 썬데이워커) 카테고리 소계 한 줄로 줄여 재시도한다.
    """
    labeled_blocks = [b for b in blocks if b.get("category_label_cell")]
    flat_blocks = [b for b in blocks if not b.get("category_label_cell")]

    if flat_blocks and not labeled_blocks:
        assignments = _try_assign_flat(groups, flat_blocks)
        if assignments is not None:
            return assignments
        rolled_up = _rollup_to_category_totals(groups)
        assignments = _try_assign_flat(rolled_up, flat_blocks)
        if assignments is not None:
            return assignments
        total_capacity = sum(len(b["rows"]) for b in flat_blocks)
        raise HTTPException(
            status_code=422,
            detail=f"이 양식은 항목을 최대 {total_capacity}개(또는 카테고리 소계 {len(flat_blocks)}줄)까지만 담을 수 있는데 카테고리가 {len(groups)}개입니다.",
        )

    # Claude가 응답한 카테고리 순서는 양식의 고정 행 배치 순서와 무관하다(예: 카탈로그 조회가
    # module_name 가나다순이라 "설문형 시장검증"이 "시장성 테스트"보다 먼저 오는 경우가 흔함).
    # 그래서 순서대로 짝짓지 않고, 줄 수가 가장 큰 그룹부터 담을 수 있는 블록 중 가장 딱 맞는
    # (여유가 가장 적은) 블록에 배정한다.
    if len(groups) > len(blocks):
        raise HTTPException(
            status_code=422,
            detail=f"이 양식은 카테고리 {len(blocks)}개까지만 담을 수 있는데 항목이 {len(groups)}개 카테고리로 나뉘어 있습니다.",
        )
    remaining_blocks = list(blocks)
    assignments = []
    for group in sorted(groups, key=lambda g: len(g["items"]), reverse=True):
        candidates = [b for b in remaining_blocks if len(b["rows"]) >= len(group["items"])]
        if not candidates:
            raise HTTPException(
                status_code=422,
                detail=f"'{group['category']}' 항목이 {len(group['items'])}개인데 남은 양식 블록 중 담을 수 있는 곳이 없습니다.",
            )
        best = min(candidates, key=lambda b: len(b["rows"]))
        assignments.append((best, group, 0))
        remaining_blocks.remove(best)
    return assignments


def _compute_item_pricing(
    supabase,
    catalog_entity_id: str,
    task_type: str,
    columns: Dict[str, str],
    sheet_xml: str,
    category: str,
    item: dict,
    row: int,
) -> tuple:
    work_days, quantity = _lookup_work_days_quantity(supabase, catalog_entity_id, task_type, category, item["name"])
    uses_work_days = "supply_amount" in columns and "work_days" in columns and _formula_references_column(
        sheet_xml, f"{columns['supply_amount']}{row}", columns["work_days"]
    )
    divisor = quantity * (work_days if uses_work_days else 1)
    unit_price = round(item["amount"] / divisor) if divisor else item["amount"]
    return unit_price, work_days, quantity


def compute_line_item_pricing(
    supabase,
    entity_id: str,
    task_type: str,
    selected_modules: Optional[list],
    catalog_entity_id: str,
    line_items: List[dict],
) -> List[dict]:
    """line_items(name/amount/category)에 unit_price/work_days/quantity를 채워 반환한다.

    미리보기 UI와 PDF 발급이 이 함수 하나로 계산해 서로 다른 값이 나오지 않게 한다(2026-07-10,
    미리보기 컬럼 확장). 템플릿을 아직 못 찾거나(구형 .xls 등) 항목이 양식 행 수를 넘는 등
    계산이 안 되는 경우엔 미리보기가 생성 자체를 막으면 안 되므로, 실패시키지 않고
    단가=배분금액·작업일=수량=1로 대체한다 — 실제 PDF 발급 시의 엄격한 검증(_collect_item_block_updates)과는
    다르다.
    """

    def _fallback() -> List[dict]:
        return [{**item, "unit_price": item["amount"], "work_days": 1.0, "quantity": 1.0} for item in line_items]

    try:
        template = _find_quote_template(supabase, entity_id, task_type, selected_modules)
        cell_map = template["cell_map"]
        storage_path = template["storage_path"]
        if not storage_path.lower().endswith(".xlsx"):
            return _fallback()
        source_bytes = template_storage.download(storage_path)
        sheet_xml = _read_sheet_xml(source_bytes, template["sheet_name"])

        columns = cell_map.get("columns", {})
        blocks = [b for b in cell_map.get("item_blocks", []) if b.get("role") != "labor_fte"]
        groups = _group_line_items(line_items)
        assignments = _assign_groups_to_blocks(groups, blocks)
    except HTTPException:
        return _fallback()

    enriched: List[dict] = []
    for block, group, row_offset in assignments:
        rows = block["rows"]
        for i, item in enumerate(group["items"]):
            row_index = row_offset + i
            if row_index >= len(rows):
                enriched.append({**item, "unit_price": item["amount"], "work_days": 1.0, "quantity": 1.0})
                continue
            unit_price, work_days, quantity = _compute_item_pricing(
                supabase, catalog_entity_id, task_type, columns, sheet_xml, group["category"], item, rows[row_index]
            )
            enriched.append({**item, "unit_price": unit_price, "work_days": work_days, "quantity": quantity})
    return enriched


def _collect_item_block_updates(
    supabase,
    item_blocks: List[dict],
    columns: Dict[str, str],
    line_items: List[dict],
    catalog_entity_id: str,
    task_type: str,
    sheet_xml: str,
) -> CellUpdates:
    groups = _group_line_items(line_items)
    blocks = [b for b in item_blocks if b.get("role") != "labor_fte"]
    updates: CellUpdates = {}

    # "인건비" 전용 블록(role=labor_fte)은 지금 카탈로그 데이터 모델에 없는 항목이라 채우지
    # 않지만, 마스터 원본 파일에는 예전 실제 고객의 인건비 실수치가 그대로 남아있어 그냥 두면
    # 합계 수식(예: SUM(R13:T22))에 섞여 들어간다. 그래서 이 블록은 항상 빈 값으로 지운다.
    for block in item_blocks:
        if block.get("role") != "labor_fte":
            continue
        for row in block["rows"]:
            for key, col in columns.items():
                if key != "note":
                    updates[f"{col}{row}"] = None

    assignments = _assign_groups_to_blocks(groups, blocks)

    # 블록은 전부(할당 여부와 무관하게) 한 번씩 전체 행 + 카테고리 라벨/소계 셀을 비운다.
    # 카테고리가 이 견적에서 아예 안 쓰이는 블록도 있을 수 있는데(예: 항목이 1개 카테고리뿐인
    # 견적서 — 2번째 카테고리 블록은 assignments에 안 나타남), 그런 블록을 그냥 두면 마스터
    # 원본에 남아있는 이전 발급 이력이나 "볼드체로 작성" 같은 빈 템플릿의 안내 문구가 그대로
    # 찍혀 나온다.
    for block in blocks:
        if block.get("category_label_cell"):
            updates[block["category_label_cell"]] = None
        if block.get("category_subtotal_cell"):
            updates[block["category_subtotal_cell"]] = None
        for row in block["rows"]:
            for key, col in columns.items():
                if key != "note":
                    updates[f"{col}{row}"] = None  # 우선 비워서 이전 발급 이력의 leftover를 지운다

    for block, group, row_offset in assignments:
        rows = block["rows"]
        if block.get("category_label_cell"):
            updates[block["category_label_cell"]] = group["category"]
        if block.get("category_subtotal_cell"):
            updates[block["category_subtotal_cell"]] = group["amount"]

        for i, item in enumerate(group["items"]):
            row_index = row_offset + i
            if row_index >= len(rows):
                continue
            row = rows[row_index]
            unit_price, work_days, quantity = _compute_item_pricing(
                supabase, catalog_entity_id, task_type, columns, sheet_xml, group["category"], item, row
            )

            if "item_name" in columns:
                updates[f"{columns['item_name']}{row}"] = item["name"]
            if "unit_price" in columns:
                updates[f"{columns['unit_price']}{row}"] = unit_price
            if "work_days" in columns:
                updates[f"{columns['work_days']}{row}"] = work_days
            if "quantity" in columns:
                updates[f"{columns['quantity']}{row}"] = quantity
            if "supply_amount" in columns:
                updates[f"{columns['supply_amount']}{row}"] = item["amount"]
            if "amount" in columns:  # 블렌디드랩: 부가세 별도 금액 컬럼명이 amount
                updates[f"{columns['amount']}{row}"] = item["amount"]
    return updates


def _collect_totals_updates(totals: Dict[str, str], grand_total: float, vat_amount: float, supply_amount: float) -> CellUpdates:
    updates: CellUpdates = {}
    if "top_display_cell" in totals:
        updates[totals["top_display_cell"]] = grand_total
    if "subtotal_cell" in totals:
        updates[totals["subtotal_cell"]] = supply_amount
    if "supply_total_cell" in totals:
        updates[totals["supply_total_cell"]] = supply_amount
    if "vat_cell" in totals:
        updates[totals["vat_cell"]] = vat_amount
    if "grand_total_cell" in totals:
        updates[totals["grand_total_cell"]] = grand_total
    return updates


def _build_filled_xlsx(entity_quote_id: str, filled_path: Path) -> None:
    """법인 마스터 xlsx의 가변 셀만 채워 filled_path에 저장한다. PDF 발급과 xlsx 다운로드가
    이 함수 하나를 공유해 두 파일의 내용이 항상 일치한다(2026-07-10)."""
    supabase = get_supabase()

    quote_res = (
        supabase.table("entity_quotes")
        .select(
            "id, entity_id, task_type, recipient_name, quote_date, service_name, total_amount, "
            "line_items, is_catalog_borrowed, catalog_source_entity_name, selected_modules, "
            "estimate_sets(vat_included), entity_templates(name)"
        )
        .eq("id", entity_quote_id)
        .execute()
    )
    if not quote_res.data:
        raise HTTPException(status_code=404, detail="견적서를 찾을 수 없습니다.")
    quote = quote_res.data[0]

    if not quote["line_items"]:
        raise HTTPException(status_code=422, detail="항목이 아직 생성되지 않았습니다. 먼저 항목·금액을 생성하세요.")
    if not quote["recipient_name"]:
        raise HTTPException(status_code=422, detail="수신자(고객사명)가 없습니다.")

    vat_included = quote["estimate_sets"]["vat_included"]
    grand_total = float(quote["total_amount"])
    if vat_included:
        supply_amount = round(grand_total / 1.1)
        vat_amount = grand_total - supply_amount
    else:
        supply_amount = grand_total
        vat_amount = round(supply_amount * 0.1)

    # 카탈로그를 다른 법인에서 차용한 경우, work_days/quantity도 그 출처 법인 카탈로그에서 찾는다.
    catalog_entity_id = quote["entity_id"]
    if quote["is_catalog_borrowed"] and quote["catalog_source_entity_name"]:
        src = (
            supabase.table("entity_templates")
            .select("id")
            .eq("name", quote["catalog_source_entity_name"])
            .execute()
        )
        if src.data:
            catalog_entity_id = src.data[0]["id"]

    template = _find_quote_template(supabase, quote["entity_id"], quote["task_type"], quote["selected_modules"])
    cell_map = template["cell_map"]
    storage_path = template["storage_path"]
    if not storage_path.lower().endswith(".xlsx"):
        raise HTTPException(
            status_code=500,
            detail=f"{Path(storage_path).name}은(는) 구형 포맷이라 아직 PDF 발급을 지원하지 않습니다 (.xlsx로 변환 필요).",
        )
    source_bytes = template_storage.download(storage_path)

    sheet_xml = _read_sheet_xml(source_bytes, template["sheet_name"])

    updates: CellUpdates = {}
    updates.update(_collect_header_updates(cell_map.get("header_fields", {}), quote))
    updates.update(
        _collect_item_block_updates(
            supabase,
            cell_map.get("item_blocks", []),
            cell_map.get("columns", {}),
            quote["line_items"],
            catalog_entity_id,
            quote["task_type"],
            sheet_xml,
        )
    )
    updates.update(_collect_totals_updates(cell_map.get("totals", {}), grand_total, vat_amount, supply_amount))
    for coord in cell_map.get("always_clear_cells", []):
        updates[coord] = None

    _patch_xlsx(source_bytes, template["sheet_name"], updates, filled_path)


def render_entity_quote_xlsx(entity_quote_id: str) -> bytes:
    """마스터 xlsx의 가변 셀만 채운 결과를 변환 없이 그대로 xlsx bytes로 반환한다."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        filled_path = Path(tmp_dir) / "filled.xlsx"
        _build_filled_xlsx(entity_quote_id, filled_path)
        return filled_path.read_bytes()


def render_entity_quote_pdf(entity_quote_id: str) -> bytes:
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_dir_path = Path(tmp_dir)
        filled_path = tmp_dir_path / "filled.xlsx"
        _build_filled_xlsx(entity_quote_id, filled_path)

        # 요청마다 새 프로필을 쓰면 폰트 캐시가 매번 콜드 스타트라 렌더링이 깨지는 걸 확인했다
        # (같은 파일을 재변환하면 정상으로 돌아옴 — 캐시가 데워진 뒤엔 문제 없음). 그렇다고 이
        # 컴퓨터에서 실행 중일 수 있는 다른 LibreOffice(GUI 앱 등)와 프로필을 공유해 잠금 충돌이
        # 나는 것도 피하고 싶어서, 이 서비스 전용으로 고정된 프로필 디렉터리를 한 번만 만들고
        # 계속 재사용한다. 프로젝트 경로 자체에 공백이 있어 file:// URI가 깨지므로, 공백 없는
        # 시스템 임시 경로에 둔다.
        profile_dir = Path(tempfile.gettempdir()) / "estimate_automation_lo_profile"
        convert_cmd = [
            "soffice",
            f"-env:UserInstallation=file://{profile_dir}",
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(tmp_dir_path),
            str(filled_path),
        ]
        result = subprocess.run(convert_cmd, capture_output=True, text=True, timeout=60)
        pdf_path = filled_path.with_suffix(".pdf")
        if result.returncode != 0 or not pdf_path.exists():
            raise HTTPException(
                status_code=500,
                detail=f"PDF 변환에 실패했습니다: {result.stderr or result.stdout}",
            )
        return pdf_path.read_bytes()