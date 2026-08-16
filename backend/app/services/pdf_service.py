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

import hashlib
import io
import itertools
import json
import re
import subprocess
import tempfile
import threading
import zipfile
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional
from xml.sax.saxutils import escape

from fastapi import HTTPException

from app.config import get_supabase
from app.services import catalog_service, template_storage

CellUpdates = Dict[str, Any]  # 셀 좌표("H16") -> 값(str|int|float|None). None이면 값을 비운다.

# 미사용 항목 행의 공급가액 등은 원본에 수식(예: =E16*F16*G16)으로 들어있어, 그냥 None을 넣으면
# _patch_sheet_xml이 "수식 셀은 캐시만 지우고 수식은 보존"하는 규칙 때문에 단가/수량 칸이
# 비어도 수식이 0으로 재계산되어 "0"이 그대로 찍힌다(2026-08-09 재현·확인). 이 값은 그 규칙을
# 무시하고 수식이 있든 없든 셀을 완전히 비우라는 표시다.
_FORCE_EMPTY = object()


def _cell_pattern(coord: str) -> re.Pattern:
    return re.compile(rf'<c r="{re.escape(coord)}"([^>]*?)(/>|>(.*?)</c>)', re.DOTALL)


def _has_formula(inner: str) -> bool:
    return "<f>" in inner or "<f " in inner or "<f/>" in inner


def _cell_text_for_wrap(value: Any) -> Optional[str]:
    """줄바꿈 유무·줄수를 판단할 때 쓸 표시 텍스트."""
    if isinstance(value, str):
        return value
    return None


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
        if value is _FORCE_EMPTY:
            replacement = _build_cell_xml(coord, attrs, None)
        elif _has_formula(inner):
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


def _strip_sheet_background_picture(sheet_xml: str) -> str:
    """ABBG 마스터는 알파브라더스 양식을 복제해 만든 흔적으로 시트 배경 서식(Format Background)에
    알파브라더스 워터마크(image1.jpeg)가 그대로 남아있다(2026-08-16 발견). Excel은 배경 서식 이미지를
    인쇄/PDF 내보내기에서 항상 제외하지만(사용자가 엑셀에서 직접 PDF로 내보내면 정상으로 보이는 이유),
    LibreOffice headless는 이를 그대로 렌더링해 잘못된 워터마크가 찍힌다. 실제 ABBG 워터마크는 별도
    VML 도형(vmlDrawing)으로 들어있어 이 배경을 지워도 영향 없다. 알파브라더스 자신은 이 배경 이미지가
    본인 워터마크이므로(2026-08-13 fix로 색공간만 수정, 유지) 이 함수는 ABBG에만 적용한다."""
    return re.sub(r"<picture[^/]*/>", "", sheet_xml)


def _strip_sheet_hyperlinks(sheet_xml: str) -> str:
    """블렌디드랩 마스터 B2("견적서" 제목) 셀에 실제 <hyperlinks> 요소가 걸려 있었다(원본 제작사
    yesform.com 템플릿 검색 페이지로 연결되는, 견적서 내용과 무관한 잔재 링크) — 진짜 하이퍼링크는
    styles.xml의 xfId/font 색상과 무관하게 LibreOffice/Excel이 자체적으로 파란 밑줄을 입혀 렌더링
    하므로, _patch_hyperlink_style_bleed로 셀 서식만 고쳐선 없어지지 않았다(2026-08-14 재확인 —
    PDF까지 직접 렌더링해서 확인). 견적서 PDF엔 어차피 무관한 외부 링크이므로 통째로 제거한다."""
    return re.sub(r"<hyperlinks>.*?</hyperlinks>", "", sheet_xml, flags=re.DOTALL)


def _patch_hyperlink_style_bleed(styles_xml: str) -> str:
    """블렌디드랩 마스터 "견적서" 제목 셀(B2)처럼, 셀 자체 서식은 굵게·검정이어야 하는데도
    LibreOffice로 PDF 변환하면 파란색 밑줄로 나오는 경우가 있었다(2026-08-13 사용자 발견). 그
    셀의 xf가 내부적으로 Excel 내장 "Hyperlink" 이름 스타일(cellStyles의 builtinId=8, 9)을
    부모로 참조하고 있어서인데, 실제 이 마스터들엔 <hyperlinks> 요소(진짜 하이퍼링크)가 없으므로
    — .xls→.xlsx 변환 중 남은 참조로 보고 — Normal(xfId=0)로 되돌린다. xfId만 고쳐도 밑줄은
    없어지지만(LibreOffice가 부모 named style을 보고 하이퍼링크로 렌더링하는 부분), 이 xf가
    applyFont="true"로 자기 fontId에 파란색을 직접 박아둔 경우 색은 그대로 남는다(재확인 —
    2026-08-13) — 그 fontId들의 색도 검정으로 되돌린다.
    """
    cellstyles_m = re.search(r"<cellStyles[^>]*>(.*?)</cellStyles>", styles_xml, re.DOTALL)
    if not cellstyles_m:
        return styles_xml
    hyperlink_xf_ids = {
        m.group(1)
        for m in re.finditer(r'<cellStyle\b[^>]*\bxfId="(\d+)"[^>]*\bbuiltinId="[89]"', cellstyles_m.group(0))
    }
    if not hyperlink_xf_ids:
        return styles_xml

    cellxfs_m = re.search(r"<cellXfs[^>]*>(.*?)</cellXfs>", styles_xml, re.DOTALL)
    if not cellxfs_m:
        return styles_xml

    direct_font_ids: set = set()

    def _fix_xf(m: re.Match) -> str:
        xf_xml = m.group(0)
        xfid_m = re.search(r'\bxfId="(\d+)"', xf_xml)
        if not xfid_m or xfid_m.group(1) not in hyperlink_xf_ids:
            return xf_xml
        font_m = re.search(r'\bfontId="(\d+)"', xf_xml)
        if font_m:
            direct_font_ids.add(font_m.group(1))
        return re.sub(r'\bxfId="\d+"', 'xfId="0"', xf_xml, count=1)

    patched_cellxfs = re.sub(r"<xf\b[^>]*(?:/>|>.*?</xf>)", _fix_xf, cellxfs_m.group(1), flags=re.DOTALL)
    styles_xml = styles_xml[: cellxfs_m.start(1)] + patched_cellxfs + styles_xml[cellxfs_m.end(1) :]

    if not direct_font_ids:
        return styles_xml
    fonts_m = re.search(r"<fonts[^>]*>(.*?)</fonts>", styles_xml, re.DOTALL)
    if not fonts_m:
        return styles_xml

    font_index = itertools.count()

    def _fix_font(m: re.Match) -> str:
        font_xml = m.group(0)
        if str(next(font_index)) not in direct_font_ids:
            return font_xml
        font_xml = re.sub(r'<color rgb="[0-9A-Fa-f]{6,8}"\s*/>', '<color rgb="FF000000"/>', font_xml, count=1)
        font_xml = re.sub(r'<u\s+val="[^"]*"\s*/>', "", font_xml, count=1)
        return font_xml

    patched_fonts = re.sub(r"<font>.*?</font>", _fix_font, fonts_m.group(1), flags=re.DOTALL)
    return styles_xml[: fonts_m.start(1)] + patched_fonts + styles_xml[fonts_m.end(1) :]


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
    # localSheetId/name 속성 순서는 파일마다 다르다(대부분의 실제 법인 원본은 name이 먼저 옴,
    # 예: <definedName name="_xlnm.Print_Area" localSheetId="1">) — 순서를 가정한 패턴은 이미
    # 정상 동작하는 인쇄영역도 "없다"고 오판해서 _fix_broken_print_area가 훨씬 큰(시트 전체
    # 사용범위 기준) 중복 인쇄영역을 추가로 만들어버리고, 결과 PDF가 그 큰 범위 기준으로
    # 축소되어 내용이 페이지 구석에 작게 찍히는 버그로 이어졌다(2026-08-09 재현·확인).
    m = re.search(
        r'<definedName\b(?=[^>]*\blocalSheetId="0")(?=[^>]*\bname="_xlnm\.Print_Area")[^>]*>([^<]*)</definedName>',
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
        r'<definedName\b(?=[^>]*\blocalSheetId="0")'
        r'(?=[^>]*\bname="(?:_xlnm\.Print_Area|Excel_BuiltIn_Print_Area)")'
        r'[^>]*>.*?</definedName>',
        "",
        workbook_xml,
        flags=re.DOTALL,
    )
    if "<definedNames>" in workbook_xml:
        return re.sub(r"</definedNames>", new_defined_name + "</definedNames>", workbook_xml, count=1)
    return re.sub(r"(</sheets>)", r"\1<definedNames>" + new_defined_name + "</definedNames>", workbook_xml, count=1)


def _hide_rows(sheet_xml: str, row_numbers: set) -> str:
    """항목이 배정되지 않은 행을 hidden="1"로 표시해 PDF에서 아예 빠지게 한다 — 값만 비우면
    수식 재계산으로 "0"이 찍히는 문제(위 _FORCE_EMPTY)와 별개로, 빈 줄 자체가 남아 표가
    쓸데없이 길어지는 문제(2026-08-09 사용자 지적)를 없앤다."""
    if not row_numbers:
        return sheet_xml

    def _mark_hidden(m: re.Match) -> str:
        if int(m.group(1)) not in row_numbers:
            return m.group(0)
        tag = m.group(0)
        # 블렌디드랩처럼 .xls에서 변환된 파일은 hidden="false"를 명시적으로 이미 갖고 있다 —
        # 존재 여부가 아니라 값만 보고 판단하면(과거 버전의 버그, 2026-08-10 발견) 같은 태그에
        # hidden 속성이 두 번 들어가는 잘못된 XML이 만들어지고, LibreOffice가 이를 다르게
        # 해석해 인쇄 레이아웃 전체가 깨진다(표/테두리 소실, 내용이 여러 페이지로 흩어짐).
        if re.search(r'\bhidden="[^"]*"', tag):
            return re.sub(r'\bhidden="[^"]*"', 'hidden="1"', tag, count=1)
        return (tag[:-2] + ' hidden="1"/>') if tag.endswith("/>") else (tag[:-1] + ' hidden="1">')

    return re.sub(r'<row r="(\d+)"[^>]*?(?:/>|>)', _mark_hidden, sheet_xml)


def _ensure_wrap_text(sheet_xml: str, styles_xml: str, coords: set) -> tuple[str, str]:
    """줄바꿈(\\n)이 들어간 값을 쓰는 셀(예: ABBG "상세내용" 칸의 세로형 개조식 목록, PRD 6.2)이
    원래 wrapText 서식이 없으면(2026-08-10 확인 — ABBG 마스터의 해당 칸이 그랬다) 한 줄로
    뭉개져 찍힌다. 그 셀의 스타일을 wrapText=1로 복제한 새 스타일로만 바꿔치기한다 — 같은
    스타일을 공유하는 다른 셀(서식이 원래대로여야 함)에는 영향을 주지 않는다."""
    if not coords:
        return sheet_xml, styles_xml
    m = re.search(r'(<cellXfs count=")(\d+)(">)(.*?)(</cellXfs>)', styles_xml, re.DOTALL)
    if not m:
        return sheet_xml, styles_xml
    count = int(m.group(2))
    body = m.group(4)
    xf_entries = re.findall(r'<xf\b[^>]*?(?:/>|>.*?</xf>)', body, re.DOTALL)
    new_entries: List[str] = []
    wrap_cache: Dict[int, int] = {}

    for coord in coords:
        cm = re.search(rf'<c r="{re.escape(coord)}"[^>]*?(?:/>|>)', sheet_xml)
        if not cm:
            continue
        s_match = re.search(r'\ss="(\d+)"', cm.group(0))
        if not s_match:
            continue
        old_idx = int(s_match.group(1))
        if old_idx >= len(xf_entries) or re.search(r'wrapText="(1|true)"', xf_entries[old_idx]):
            continue
        if old_idx not in wrap_cache:
            xf = xf_entries[old_idx]
            align_match = re.search(r"<alignment\b[^>]*/>", xf)
            if align_match:
                align_tag = align_match.group(0)
                # .xls에서 변환된 마스터(블렌디드랩 등)는 wrapText="false"처럼 true/false
                # 표기를 쓴다 — "1"만 보고 없다고 판단해 속성을 또 붙이면 wrapText가 중복
                # 지정된 잘못된 XML이 되어 styles.xml 전체가 깨진다(2026-08-10 발견).
                if "wrapText=" in align_tag:
                    new_align_tag = re.sub(r'wrapText="[^"]*"', 'wrapText="1"', align_tag)
                else:
                    new_align_tag = align_tag[:-2] + ' wrapText="1"/>'
                wrapped_xf = xf[: align_match.start()] + new_align_tag + xf[align_match.end() :]
            elif xf.endswith("/>"):
                wrapped_xf = xf[:-2] + '><alignment wrapText="1"/></xf>'
            else:
                continue  # 이미 있는 <alignment>...</alignment> 형태는 드물어 다루지 않는다
            wrap_cache[old_idx] = count + len(new_entries)
            new_entries.append(wrapped_xf)
        new_idx = wrap_cache[old_idx]
        sheet_xml = sheet_xml[: cm.start()] + cm.group(0).replace(f's="{old_idx}"', f's="{new_idx}"', 1) + sheet_xml[cm.end() :]

    if not new_entries:
        return sheet_xml, styles_xml
    new_count = count + len(new_entries)
    styles_xml = (
        styles_xml[: m.start()]
        + f'<cellXfs count="{new_count}">'
        + body
        + "".join(new_entries)
        + "</cellXfs>"
        + styles_xml[m.end() :]
    )
    return sheet_xml, styles_xml


def _normalize_block_row_heights(sheet_xml: str, item_blocks: List[dict], updates: CellUpdates) -> str:
    """항목 블록(카테고리 하나) 안의 행 높이를 통일한다 — 원본 마스터에 원인 불명의 들쭉날쭉한
    ht 값이 그대로 남아있는 경우가 있고(예: 테스티파이, 2026-08-11 사용자 지적), 실제 채워
    넣는 내용이 줄바꿈(\\n)으로 여러 줄이 되면 그 행만 커지고 나머지는 그대로라 표가 깨져
    보인다. 블록의 기준 높이(그 블록에서 가장 흔한 ht)를 구하고, 이번에 채우는 내용 중
    가장 많은 줄수를 요구하는 행 기준으로 필요하면 기준 높이를 올린 뒤, 블록의 모든 행에
    똑같이 적용한다."""
    if not item_blocks:
        return sheet_xml

    row_heights: Dict[int, float] = {}
    for m in re.finditer(r'<row r="(\d+)"[^>]*\bht="([\d.]+)"', sheet_xml):
        row_heights[int(m.group(1))] = float(m.group(2))

    lines_by_row: Dict[int, int] = {}
    for coord, value in updates.items():
        text = _cell_text_for_wrap(value)
        if text is None or "\n" not in text:
            continue
        m = re.match(r"^[A-Z]+(\d+)$", coord)
        if not m:
            continue
        row = int(m.group(1))
        lines_by_row[row] = max(lines_by_row.get(row, 1), text.count("\n") + 1)

    target_height_by_row: Dict[int, float] = {}
    for block in item_blocks:
        rows = block.get("rows") or []
        heights = [row_heights[r] for r in rows if r in row_heights]
        if not heights:
            continue
        base_height = Counter(heights).most_common(1)[0][0]
        max_lines = max((lines_by_row.get(r, 1) for r in rows), default=1)
        # base_height를 줄당 높이로 보고 곱하면(예전 방식) 알파브라더스처럼 애초에 여러 줄을
        # 감안해 크게 잡아둔 마스터(ht=150, 2026-08-13 발견)에서 150*4줄=600처럼 터무니없이
        # 커져 fit-to-page가 전체를 확 축소해버린다. base_height는 "이미 확보된 여유"로 보고,
        # 실제 필요한 높이(줄당 16pt 근사치 × 줄수)가 그걸 넘을 때만 키운다.
        # ponytail: 16pt는 폰트 크기·자간 기반 정밀 측정 아닌 고정 근사치 — 줄바꿈 셀이 잘리는
        # 사례가 나오면 폰트 메트릭 기반 계산으로 교체.
        block_height = max(base_height, 16 * max_lines)
        for row in rows:
            target_height_by_row[row] = block_height

    if not target_height_by_row:
        return sheet_xml

    def _apply_height(m: re.Match) -> str:
        row_num = int(m.group(1))
        if row_num not in target_height_by_row:
            return m.group(0)
        tag = m.group(0)
        new_height = target_height_by_row[row_num]
        if re.search(r'\bht="[\d.]+"', tag):
            tag = re.sub(r'\bht="[\d.]+"', f'ht="{new_height}"', tag, count=1)
        elif tag.endswith("/>"):
            tag = tag[:-2] + f' ht="{new_height}"/>'
        else:
            tag = tag[:-1] + f' ht="{new_height}">'
        if "customHeight=" not in tag:
            tag = tag[:-2] + ' customHeight="1"/>' if tag.endswith("/>") else tag[:-1] + ' customHeight="1">'
        return tag

    return re.sub(r'<row r="(\d+)"[^>]*?(?:/>|>)', _apply_height, sheet_xml)


def _normalize_block_cell_styles(sheet_xml: str, item_blocks: List[dict]) -> str:
    """항목 블록 안의 "가운데" 행들(첫 행·마지막 행 제외)은 서식이 전부 같아야 하는데, 원본
    마스터에 원인 불명으로 한 행만 다른 서식이 남아있는 경우가 있다(예: 블렌디드랩 마스터
    "견적서 (2)" 시트 15행 AC~AF열만 다른 행과 달리 오른쪽 테두리가 있는 스타일이라, 발급 PDF에서
    그 행만 오른쪽 끝에 없어야 할 구분선이 보임, 2026-08-13 사용자 발견). 첫/마지막 행은 표를
    여닫는 의도적인 테두리가 있을 수 있어 제외하고, 가운데 행끼리 열별로 가장 흔한 스타일로 맞춘다.
    """
    for block in item_blocks:
        rows = block.get("rows") or []
        interior_rows = rows[1:-1]
        if len(interior_rows) < 2:
            continue
        style_by_col_row: Dict[str, Dict[int, str]] = {}
        for row in interior_rows:
            for m in re.finditer(rf'<c r="([A-Z]+){row}" s="(\d+)"', sheet_xml):
                style_by_col_row.setdefault(m.group(1), {})[row] = m.group(2)
        for col, by_row in style_by_col_row.items():
            majority = Counter(by_row.values()).most_common(1)[0][0]
            for row, style in by_row.items():
                if style != majority:
                    sheet_xml = re.sub(
                        rf'(<c r="{col}{row}" s=")\d+(")', rf'\g<1>{majority}\g<2>', sheet_xml, count=1
                    )
    return sheet_xml


def _patch_xlsx(
    source_bytes: bytes,
    sheet_name: str,
    updates: CellUpdates,
    dest_path: Path,
    hidden_rows: Optional[set] = None,
    item_blocks: Optional[List[dict]] = None,
    strip_background: bool = False,
) -> None:
    with zipfile.ZipFile(io.BytesIO(source_bytes), "r") as zin:
        sheet_path = _sheet_internal_path(zin, sheet_name)
        sheet_xml = zin.read(sheet_path).decode("utf-8")
        patched_sheet_xml = _patch_sheet_xml(sheet_xml, updates)
        if strip_background:
            patched_sheet_xml = _strip_sheet_background_picture(patched_sheet_xml)
        patched_sheet_xml = _strip_sheet_hyperlinks(patched_sheet_xml)
        patched_sheet_xml = _strip_all_formula_caches(patched_sheet_xml)
        patched_sheet_xml = _hide_rows(patched_sheet_xml, hidden_rows or set())
        patched_sheet_xml = _normalize_block_row_heights(patched_sheet_xml, item_blocks or [], updates)
        patched_sheet_xml = _normalize_block_cell_styles(patched_sheet_xml, item_blocks or [])
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
        styles_xml = _patch_font_substitution(styles_xml)
        styles_xml = _patch_hyperlink_style_bleed(styles_xml)
        wrap_coords = {
            coord
            for coord, value in updates.items()
            if (text := _cell_text_for_wrap(value)) is not None and "\n" in text
        }
        patched_sheet_xml, patched_styles_xml = _ensure_wrap_text(patched_sheet_xml, styles_xml, wrap_coords)

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


def _fetch_work_days_quantity_map(supabase, catalog_entity_id: str, task_type: str) -> Dict[str, List[dict]]:
    """item_name -> 그 이름을 가진 카탈로그 행 목록(같은 이름이 여러 모듈에 있을 수 있어 리스트).
    항목마다 Supabase에 따로 조회하면 왕복이 항목 수만큼 쌓여 눈에 띄게 느려진다(2026-08-09
    실측 — 12개 항목 순차 조회에 약 2.4초, Claude 호출 1번과 맞먹는 시간) — 견적 1건당
    (법인×과업종류) 카탈로그를 한 번만 통째로 가져와 메모리에서 찾는다."""
    res = (
        supabase.table("item_catalogs")
        .select("module_name, item_name, work_days, quantity")
        .eq("entity_id", catalog_entity_id)
        .eq("task_type", task_type)
        .eq("is_current", True)
        .execute()
    )
    by_name: Dict[str, List[dict]] = {}
    for row in res.data:
        by_name.setdefault(row["item_name"], []).append(row)
    return by_name


def _lookup_work_days_quantity(
    catalog_map: Dict[str, List[dict]], module_name: str, item_name: str
) -> tuple[float, float]:
    rows = catalog_map.get(item_name)
    if not rows:
        return 1.0, 1.0
    exact = [r for r in rows if r["module_name"] == module_name]
    row = exact[0] if exact else rows[0]
    return float(row["work_days"]), float(row["quantity"])


def get_column_display(supabase, entity_id: str, task_types: List[str], selected_modules: Optional[list]) -> Dict[str, Any]:
    """미리보기 UI가 법인마다 다른 실제 원본 양식 그대로 컬럼명·순서를 보여주기 위한 정보를
    반환한다(2026-07-10 — 같은 의미라도 법인마다 명칭이 다름: 예) 작업일/소요일, 수량/작업수량).
    템플릿을 못 찾는 경우(러프 비교견적 등)는 실패시키지 않고 빈 값으로 대체한다. 과업종류를
    교차 선택한 견적서는 실제 배정 시점에야 어느 양식이 쓰일지 확정되므로(용량 초과 시 다음
    후보로 넘어감, _resolve_host_templates), 여기서는 1순위 후보 기준으로 근사해 보여준다."""
    try:
        template = _resolve_host_templates(supabase, entity_id, task_types, selected_modules)[0]
    except HTTPException:
        return {"column_labels": {}, "detail_column_order": []}
    cell_map = template["cell_map"]
    order = list(cell_map.get("detail_column_order", []))
    columns = cell_map.get("columns", {})
    if "description" in columns and "description" not in order:
        order = ["description"] + order
    for extra_key in ("input_mm", "tax_amount"):
        if extra_key in columns and extra_key not in order:
            order.append(extra_key)
    return {
        "column_labels": cell_map.get("column_labels", {}),
        "detail_column_order": order,
        "show_category_split": any(
            block.get("category_large_cell") for block in cell_map.get("item_blocks", [])
        ),
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


def _find_shared_template(supabase, entity_id: str, task_types: List[str]) -> Optional[dict]:
    """과업종류를 2개 이상 교차 선택했을 때, 과업종류별 전용 블록을 이미 갖춘 시트(예: 알파브라더스
    "견적서" 시트, 034 마이그레이션)가 있으면 그 시트를 반환한다. 없으면 None(호출부가 과업종류별
    전용 시트 방식으로 넘어감).

    entity_id의 quote_templates 행 중 어떤 task_type으로 등록돼 있든 상관없이(그 행의 cell_map ·
    storage_path · sheet_name만 실제로 쓰이므로) item_blocks 개수가 과업종류 수 이상인 행을
    찾는다 — 개별 모듈 전용 시트(FGI/사용성테스트 등)는 블록이 1개뿐이라 걸러진다(그런 시트에
    여러 과업종류를 억지로 한 블록에 몰아넣으면 구분(대)/구분(중) 라벨이 나중 그룹 값으로
    덮어써지는 문제가 있었다, 2026-08-10 발견). 등록된 task_type이 실제 요청한 task_types와
    겹치는 행을 우선한다."""
    res = supabase.table("quote_templates").select("*").eq("entity_id", entity_id).execute()
    candidates = [row for row in res.data if len(row["cell_map"].get("item_blocks", [])) >= len(task_types)]
    if not candidates:
        return None
    matching = [row for row in candidates if row["task_type"] in task_types]
    return (matching or candidates)[0]


def _resolve_host_templates(supabase, entity_id: str, task_types: List[str], selected_modules: Optional[list]) -> List[dict]:
    """과업종류를 교차 선택한 견적서를 담을 물리 시트 후보 목록을 반환한다.

    ABBG/블렌디드랩/썬데이워커는 마케팅·시장검증이 원래 같은 시트(같은 원본 파일의 "견적서" 등
    범용 양식)라 후보가 1개로 자연스럽게 좁혀진다. 테스티파이·알파브라더스처럼 과업종류마다
    전용 시트가 따로 있으면 여러 후보가 남는데, 어느 시트를 써도 되므로 task_types에 준 순서를
    우선순위로 삼는다(첫 번째로 선택된 과업종류의 양식을 먼저 시도). 항목이 그 시트의 칸 수를
    넘으면(_assign_groups_to_blocks가 422) 호출부가 다음 후보로 넘어간다.

    과업종류가 2개 이상이면, 그 전부를 한 시트로 감당할 수 있는 공용 시트(_find_shared_template)가
    있는지 먼저 확인해 최우선 후보로 넣는다 — 알파브라더스가 딱 이 경우다."""
    candidates: List[dict] = []
    seen: set = set()
    if len(task_types) > 1:
        shared = _find_shared_template(supabase, entity_id, task_types)
        if shared:
            candidates.append(shared)
            seen.add((shared["storage_path"], shared["sheet_name"]))
    last_error: Optional[HTTPException] = None
    for task_type in task_types:
        try:
            template = _find_quote_template(supabase, entity_id, task_type, selected_modules)
        except HTTPException as e:
            last_error = e
            continue
        key = (template["storage_path"], template["sheet_name"])
        if key not in seen:
            seen.add(key)
            candidates.append(template)
    if not candidates:
        raise last_error or HTTPException(status_code=404, detail="이 법인·과업종류 조합에 대한 견적서 양식을 찾을 수 없습니다.")
    return candidates


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
        elif field == "client_contact":
            updates[coord] = quote.get("recipient_contact") or ""
        elif field == "client_phone":
            updates[coord] = quote.get("recipient_phone") or ""
        elif field == "client_email":
            updates[coord] = quote.get("recipient_email") or ""
        elif field == "service_name":
            # 테스티파이 마스터는 이 셀 자체가 "용역명: " 라벨이다(recipient_name의 "귀하"와 같은
            # 패턴) — 값만 쓰면 라벨이 지워진다(2026-08-13 사용자 발견).
            updates[coord] = f"용역명: {quote.get('service_name') or ''}"
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
    최후 수단이다 — 세부 항목 대신 카테고리 소계만이라도 담는다. 접힌 세부 항목명은 "상품구성"
    컬럼이 있는 양식(알파브라더스·ABBG 등, PRD 6.2 "상품구성에 세부항목을 세로형 개조식(1. 2. 3.)으로
    나열")을 위해 description으로 합쳐 둔다 — 줄바꿈으로 세로 나열한다(PRD가 명시한 "세로형").
    컬럼이 없는 양식에서는 그냥 무시된다.

    그룹에 항목이 이미 1개뿐이면 그대로 둔다 — Claude가 항목 생성 시 이미 그 항목 자체의
    description을 채워둔 경우(2026-08, 마케팅+시장검증 교차선택 등)가 있는데, 여기서 "1. 그
    항목명" 한 줄로 다시 합치면 원래 있던 더 풍부한 설명을 지워버리게 된다(2026-08-10 발견).
    "묶을 세부 항목"이 실제로 여러 개일 때만(예: 통합 패키지의 5개 하위 모듈) 합친다."""
    return [
        g if len(g["items"]) <= 1 else {
            "category": g["category"],
            "amount": g["amount"],
            "items": [{
                "category": g["category"],
                "name": g["category"],
                "amount": g["amount"],
                # 그룹 안 항목은 전부 같은 category(=module_name)라 같은 과업종류에 속한다.
                "task_type": g["items"][0].get("task_type") if g["items"] else None,
                "description": "\n".join(f"{i + 1}. {it['name']}" for i, it in enumerate(g["items"])),
            }],
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


def _try_assign_flat_by_task_type(groups: List[Dict[str, Any]], flat_blocks: List[dict]) -> Optional[List[tuple]]:
    """알파브라더스처럼 블록마다 구분(대)/구분(중)이 있으면(034 마이그레이션), 과업종류 하나당
    전용 블록 하나씩 배정한다 — 마케팅과 시장검증이 같은 블록에 섞여 구분(대) 라벨을 하나로
    억지로 합치는 일이 없게 한다. 과업종류가 1개뿐이면 자연히 첫 블록만 쓰이고 나머지 블록은
    (호출부가) 미사용으로 비워 숨긴다. 블록 수보다 과업종류가 많거나, 이 표시용 라벨 자체가
    없는 양식(대부분)이면 None을 돌려줘 기존 방식(_try_assign_flat)으로 넘어가게 한다."""
    if not flat_blocks or not all(b.get("category_large_cell") for b in flat_blocks):
        return None
    groups_by_task_type: Dict[Optional[str], List[Dict[str, Any]]] = {}
    order: List[Optional[str]] = []
    for g in groups:
        tt = g["items"][0].get("task_type") if g["items"] else None
        if tt not in groups_by_task_type:
            groups_by_task_type[tt] = []
            order.append(tt)
        groups_by_task_type[tt].append(g)
    if len(order) > len(flat_blocks):
        return None
    assignments: List[tuple] = []
    for block, tt in zip(flat_blocks, order):
        sub = _try_assign_flat(groups_by_task_type[tt], [block])
        if sub is None:
            return None
        assignments.extend(sub)
    return assignments


def _assign_groups_to_blocks(groups: List[Dict[str, Any]], blocks: List[dict], columns: Dict[str, str]) -> List[tuple]:
    """카테고리(그룹)를 양식 블록의 행에 배정한다. 반환값: [(block, group, row_offset), ...]

    category_label_cell이 있는 블록은 원본 양식이 카테고리별 전용 영역(헤더+소계)을 갖는다는
    뜻이라 카테고리 1개당 블록 1개씩 배정한다(기존 동작). 헤더 셀이 없는 "플랫" 블록(예:
    블렌디드랩 — 카테고리 구분 없이 항목을 그냥 나열하는 양식)은 여러 카테고리를 같은 블록 행에
    순서대로 나눠 채운다(그룹을 블록 경계에서 쪼개지는 않는다 — 실제 데이터에서 한 카테고리가
    플랫 블록 하나의 남은 자리보다 커서 쪼개야 했던 사례가 없어 그 경우까지는 다루지 않는다).
    세부 항목 그대로 넣으면 자리가 모자랄 땐(예: 썬데이워커) 카테고리 소계 한 줄로 줄여 재시도한다.

    "상품구성"(description) 컬럼이 있는 양식(알파브라더스·ABBG, PRD 6.2)은 처음부터 카테고리(=
    모듈) 하나당 한 줄만 쓴다 — 상품명=모듈명, 상품구성=세부 항목 세로형 개조식. 자리가 모자랄
    때만 쓰는 최후 수단이 아니라 이 양식들의 기본 표시 방식이라 여기서 먼저 적용해 둔다.
    """
    if columns.get("description"):
        # 항목 자체에 이미 개별 description이 있는 그룹(예: 통합 패키지의 5개 하위 모듈,
        # 마이그레이션 008/032)은 접지 않고 그대로 여러 줄로 배정한다 — 롤업은 항목에
        # description이 없는 마케팅류 카탈로그(PRD 6.2)에만 적용되는 최후 수단이다.
        groups = [
            g if any(it.get("description") for it in g["items"]) else _rollup_to_category_totals([g])[0]
            for g in groups
        ]

    labeled_blocks = [b for b in blocks if b.get("category_label_cell")]
    flat_blocks = [b for b in blocks if not b.get("category_label_cell")]

    if flat_blocks and not labeled_blocks:
        assignments = _try_assign_flat_by_task_type(groups, flat_blocks)
        if assignments is not None:
            return assignments
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
    assignments = _try_assign_labeled(groups, blocks)
    if assignments is not None:
        return assignments
    # 카테고리별 세부 항목 그대로는 블록 자리다툼(예: 4행짜리 블록이 하나뿐인데 4개 이상인
    # 카테고리가 둘 이상)으로 못 담을 수 있다. 전부 소계로 접으면 자리다툼이 없는 카테고리까지
    # 세부 항목을 잃으므로, 자리를 가장 많이 차지하는 카테고리부터 하나씩만 접어가며 다시
    # 시도해 꼭 필요한 만큼만 접는다(각 블록은 어차피 카테고리당 1줄 소계 셀을 이미 갖고 있음).
    working = list(groups)
    for idx in sorted(range(len(working)), key=lambda i: len(working[i]["items"]), reverse=True):
        if len(working[idx]["items"]) <= 1:
            continue
        working[idx] = _rollup_to_category_totals([working[idx]])[0]
        assignments = _try_assign_labeled(working, blocks)
        if assignments is not None:
            return assignments
    biggest = max(groups, key=lambda g: len(g["items"]))
    raise HTTPException(
        status_code=422,
        detail=f"'{biggest['category']}' 항목이 {len(biggest['items'])}개인데 카테고리 소계로 접어도 남은 양식 블록 중 담을 수 있는 곳이 없습니다.",
    )


def _try_assign_labeled(groups: List[Dict[str, Any]], blocks: List[dict]) -> Optional[List[tuple]]:
    remaining_blocks = list(blocks)
    assignments = []
    for group in sorted(groups, key=lambda g: len(g["items"]), reverse=True):
        candidates = [b for b in remaining_blocks if len(b["rows"]) >= len(group["items"])]
        if not candidates:
            return None
        best = min(candidates, key=lambda b: len(b["rows"]))
        assignments.append((best, group, 0))
        remaining_blocks.remove(best)
    return assignments


def _compute_item_pricing(
    catalog_map: Dict[str, List[dict]],
    columns: Dict[str, str],
    sheet_xml: str,
    category: str,
    item: dict,
    row: int,
) -> tuple:
    if item.get("unit_price") is not None and item.get("work_days") is not None and item.get("quantity") is not None:
        # 사용자가 화면에서 직접 입력·수정했거나 생성 시 계산해 저장해둔 값을 그대로 쓴다 —
        # 발급 시점에 카탈로그 기준으로 다시 역산하면 화면에서 본 값과 실제 PDF가 달라질 수
        # 있다(2026-08-09, 직접편집 대상을 단가/작업일/투입인력까지 확장하며 추가).
        return item["unit_price"], item["work_days"], item["quantity"]
    work_days, quantity = _lookup_work_days_quantity(catalog_map, category, item["name"])
    uses_work_days = "supply_amount" in columns and "work_days" in columns and _formula_references_column(
        sheet_xml, f"{columns['supply_amount']}{row}", columns["work_days"]
    )
    divisor = quantity * (work_days if uses_work_days else 1)
    # 반올림하면 안 된다 — 이 단가 셀 자체는 그냥 값이어도, 같은 행의 공급가액 셀은 원본에
    # 수식(=단가*작업일*수량 등)으로 들어있어 우리가 넣은 amount를 무시하고 이 단가로 다시
    # 계산한다(_patch_sheet_xml이 수식 셀은 캐시만 지우고 값은 안 덮어씀). round()로 단가가
    # 살짝 어긋나면 그 오차가 공급가액→카테고리 소계→합계까지 그대로 누적돼, 화면(웹) 총액과
    # 실제 PDF 총액이 달라지는 원인이었다(2026-08-11 확인). 나눗셈이 딱 안 떨어지면 정수가
    # 아닌 값을 그대로 쓴다 — 셀 서식이 화면에는 반올림해 보여주므로 표시는 그대로다.
    unit_price = item["amount"] / divisor if divisor else item["amount"]
    return unit_price, work_days, quantity


def _derive_extra_columns(columns: Dict[str, str], amount: float, work_days: float, quantity: float) -> Dict[str, float]:
    """input_mm/tax_amount처럼 카탈로그에 없어 파생식으로 채우는 컬럼들. PDF 발급
    (_collect_item_block_updates)과 미리보기(compute_line_item_pricing)가 같은 값을 쓰도록 여기
    한 곳에 모아둔다."""
    extra: Dict[str, float] = {}
    if "tax_amount" in columns:
        extra["tax_amount"] = round(amount * 0.1)
    if "input_mm" in columns:
        # ponytail: 실제 "역할별 투입 MM" 데이터가 카탈로그에 없어서 작업일×수량을 20영업일로
        # 나눈 근사치(PRD 7.4) — 정확한 값이 아니라 사용자가 이후 직접 고치는 걸 전제로 한 임시값.
        extra["input_mm"] = round(work_days * quantity / 20, 2)
    return extra


def _build_catalog_maps(supabase, catalog_entity_id_by_task_type: Dict[str, str]) -> Dict[str, Dict[str, List[dict]]]:
    return {
        task_type: _fetch_work_days_quantity_map(supabase, catalog_entity_id, task_type)
        for task_type, catalog_entity_id in catalog_entity_id_by_task_type.items()
    }


def _collapse_by_task_type(line_items: List[dict], task_types: List[str]) -> List[dict]:
    """과업종류를 교차 선택한 견적서가 카테고리 전용 블록 수를 넘으면(예: 테스티파이는 마케팅
    카테고리 슬롯이 2개뿐인데 마케팅 4개 모듈 + 시장검증 모듈이 겹치는 경우), 과업종류 하나당
    한 줄(소계)로 접어서 마지막으로 재시도한다 — _rollup_to_category_totals(모듈 하나 안의 세부
    항목을 접음)의 한 단계 더 큰 버전. 과업종류가 1개뿐이면 기존 동작과 같아야 하므로 호출하지
    않는다(단일 과업종류에 새로운 축약 동작을 끼워넣지 않으려고)."""
    by_type: Dict[str, List[dict]] = {}
    for item in line_items:
        by_type.setdefault(item.get("task_type") or task_types[0], []).append(item)
    collapsed = []
    for task_type in task_types:
        items = by_type.get(task_type)
        if not items:
            continue
        collapsed.append({
            "category": task_type,
            "name": task_type,
            "amount": sum(i["amount"] for i in items),
            "task_type": task_type,
            "description": "\n".join(f"{i + 1}. {it['category']} - {it['name']}" for i, it in enumerate(items)),
        })
    return collapsed


def _resolve_assignment(
    supabase, entity_id: str, task_types: List[str], selected_modules: Optional[list], line_items: List[dict]
) -> tuple[dict, bytes, str, Dict[str, str], list]:
    """호스트 양식 후보와 항목 배정을 함께 찾는다. 실제 항목 그대로 안 들어가면(카테고리가
    블록 수를 넘음) 과업종류별 소계로 접어서 한 번 더 시도한다(_collapse_by_task_type, 교차
    선택한 견적서에서만 의미 있음). 반환: (template, source_bytes, sheet_xml, columns, assignments).
    전부 실패하면 HTTPException을 그대로 올린다."""
    candidates = _resolve_host_templates(supabase, entity_id, task_types, selected_modules)
    variants = [line_items]
    if len(task_types) > 1:
        variants.append(_collapse_by_task_type(line_items, task_types))

    last_error: Optional[HTTPException] = None
    for variant in variants:
        groups = _group_line_items(variant)
        for template in candidates:
            storage_path = template["storage_path"]
            if not storage_path.lower().endswith(".xlsx"):
                last_error = HTTPException(
                    status_code=500,
                    detail=f"{Path(storage_path).name}은(는) 구형 포맷이라 아직 PDF 발급을 지원하지 않습니다 (.xlsx로 변환 필요).",
                )
                continue
            cell_map = template["cell_map"]
            columns = cell_map.get("columns", {})
            try:
                source_bytes = template_storage.download(storage_path)
                sheet_xml = _read_sheet_xml(source_bytes, template["sheet_name"])
                blocks = [b for b in cell_map.get("item_blocks", []) if b.get("role") != "labor_fte"]
                assignments = _assign_groups_to_blocks(groups, blocks, columns)
            except HTTPException as e:
                last_error = e
                continue
            return template, source_bytes, sheet_xml, columns, assignments
    raise last_error or HTTPException(status_code=422, detail="이 견적서를 담을 수 있는 양식을 찾지 못했습니다.")


def compute_line_item_pricing(
    supabase,
    entity_id: str,
    task_types: List[str],
    selected_modules: Optional[list],
    catalog_entity_id_by_task_type: Dict[str, str],
    line_items: List[dict],
) -> List[dict]:
    """line_items(name/amount/category, 각 항목에 task_type 포함)에 unit_price/work_days/quantity를
    채워 반환한다.

    미리보기 UI와 PDF 발급이 이 함수 하나로 계산해 서로 다른 값이 나오지 않게 한다(2026-07-10,
    미리보기 컬럼 확장). 템플릿을 아직 못 찾거나(구형 .xls 등) 항목이 양식 행 수를 넘는 등
    계산이 안 되는 경우엔 미리보기가 생성 자체를 막으면 안 되므로, 실패시키지 않고
    단가=배분금액·작업일=수량=1로 대체한다 — 실제 PDF 발급 시의 엄격한 검증(_collect_item_block_updates)과는
    다르다.
    """
    try:
        _template, _source_bytes, sheet_xml, columns, assignments = _resolve_assignment(
            supabase, entity_id, task_types, selected_modules, line_items
        )
    except HTTPException:
        return [{**item, "unit_price": item["amount"], "work_days": 1.0, "quantity": 1.0} for item in line_items]

    catalog_maps = _build_catalog_maps(supabase, catalog_entity_id_by_task_type)
    enriched: List[dict] = []
    for block, group, row_offset in assignments:
        rows = block["rows"]
        for i, item in enumerate(group["items"]):
            row_index = row_offset + i
            if row_index >= len(rows):
                enriched.append({**item, "unit_price": item["amount"], "work_days": 1.0, "quantity": 1.0})
                continue
            catalog_map = catalog_maps.get(item.get("task_type"), {})
            unit_price, work_days, quantity = _compute_item_pricing(
                catalog_map, columns, sheet_xml, group["category"], item, rows[row_index]
            )
            extra = _derive_extra_columns(columns, item["amount"], work_days, quantity)
            enriched.append({**item, "unit_price": unit_price, "work_days": work_days, "quantity": quantity, **extra})
    return enriched


def _collect_item_block_updates(
    supabase,
    item_blocks: List[dict],
    columns: Dict[str, str],
    assignments: list,
    catalog_entity_id_by_task_type: Dict[str, str],
    sheet_xml: str,
) -> tuple[CellUpdates, set]:
    blocks = [b for b in item_blocks if b.get("role") != "labor_fte"]
    updates: CellUpdates = {}
    hidden_rows: set = set()
    catalog_maps = _build_catalog_maps(supabase, catalog_entity_id_by_task_type)

    # "인건비" 전용 블록(role=labor_fte)은 지금 카탈로그 데이터 모델에 없는 항목이라 채우지
    # 않지만, 마스터 원본 파일에는 예전 실제 고객의 인건비 실수치가 그대로 남아있어 그냥 두면
    # 합계 수식(예: SUM(R13:T22))에 섞여 들어간다. 그래서 이 블록은 항상 완전히 비우고 숨긴다.
    for block in item_blocks:
        if block.get("role") != "labor_fte":
            continue
        for row in block["rows"]:
            hidden_rows.add(row)
            for key, col in columns.items():
                if key != "note":
                    updates[f"{col}{row}"] = _FORCE_EMPTY

    used_rows_by_block: Dict[int, set] = {id(b): set() for b in blocks}
    for block, group, row_offset in assignments:
        rows = block["rows"]
        for i in range(len(group["items"])):
            row_index = row_offset + i
            if row_index < len(rows):
                used_rows_by_block[id(block)].add(rows[row_index])

    # 블록은 전부(할당 여부와 무관하게) 한 번씩 전체 행 + 카테고리 라벨/소계 셀을 비운다.
    # 카테고리가 이 견적에서 아예 안 쓰이는 블록도 있을 수 있는데(예: 항목이 1개 카테고리뿐인
    # 견적서 — 2번째 카테고리 블록은 assignments에 안 나타남), 그런 블록을 그냥 두면 마스터
    # 원본에 남아있는 이전 발급 이력이나 "볼드체로 작성" 같은 빈 템플릿의 안내 문구가 그대로
    # 찍혀 나온다. 실제로 항목이 배정되지 않은 행은 값만 비우는 게 아니라 숨긴다(hidden_rows) —
    # 공급가액 칸이 수식(예: =E16*F16*G16)이라 값만 비우면 0으로 재계산되어 빈 줄에 "0"이 죽
    # 찍히는 문제가 있었다(2026-08-09 사용자 지적·재현).
    for block in blocks:
        block_used_rows = used_rows_by_block[id(block)]
        if block.get("category_label_cell"):
            updates[block["category_label_cell"]] = _FORCE_EMPTY
            if not block_used_rows:
                hidden_rows.add(int(re.match(r"[A-Z]+(\d+)", block["category_label_cell"]).group(1)))
        if block.get("category_subtotal_cell"):
            updates[block["category_subtotal_cell"]] = _FORCE_EMPTY
            if not block_used_rows:
                hidden_rows.add(int(re.match(r"[A-Z]+(\d+)", block["category_subtotal_cell"]).group(1)))
        # 알파브라더스처럼 블록마다 구분(대)/구분(중) 라벨 셀이 따로 있으면(034 마이그레이션) 우선
        # 비워둔다 — 이 셀들은 block["rows"] 첫 행 안에 있어서 블록이 미사용이면 아래 for문이
        # 그 행을 hidden_rows에 넣어 같이 숨겨진다(따로 hidden_rows.add 할 필요 없음).
        if block.get("category_large_cell"):
            updates[block["category_large_cell"]] = _FORCE_EMPTY
        if block.get("category_mid_cell"):
            updates[block["category_mid_cell"]] = _FORCE_EMPTY
        for row in block["rows"]:
            if row not in block_used_rows:
                hidden_rows.add(row)
            for key, col in columns.items():
                if key != "note":
                    updates[f"{col}{row}"] = _FORCE_EMPTY  # 우선 비워서 이전 발급 이력의 leftover를 지운다

    for block, group, row_offset in assignments:
        rows = block["rows"]
        if block.get("category_label_cell"):
            updates[block["category_label_cell"]] = group["category"]
        if block.get("category_subtotal_cell"):
            updates[block["category_subtotal_cell"]] = group["amount"]
        # 구분(대)/구분(중) — 지금은 둘 다 과업종류명을 그대로 쓴다(예: "마케팅"/"마케팅",
        # 실제 알파브라더스 원본 샘플의 "시장검증"/"시장검증" 표기와 동일한 방식, PRD 6.2).
        group_task_type = group["items"][0].get("task_type") if group["items"] else None
        if group_task_type:
            if block.get("category_large_cell"):
                updates[block["category_large_cell"]] = group_task_type
            if block.get("category_mid_cell"):
                updates[block["category_mid_cell"]] = group_task_type

        for i, item in enumerate(group["items"]):
            row_index = row_offset + i
            if row_index >= len(rows):
                continue
            row = rows[row_index]
            catalog_map = catalog_maps.get(item.get("task_type"), {})
            unit_price, work_days, quantity = _compute_item_pricing(
                catalog_map, columns, sheet_xml, group["category"], item, row
            )

            if "item_name" in columns:
                updates[f"{columns['item_name']}{row}"] = item["name"]
            # 상품구성(번호 매긴 세부항목) 전용 컬럼은 알파브라더스/ABBG 원본에만 있다 — 그
            # 컬럼이 없는 법인(테스티파이/블렌디드랩/썬데이워커)은 품명 칸에 접어 넣지 않고
            # 아예 표시하지 않는다(2026-08-14 사용자 결정 — 원본 양식에 없는 칸이면 괄호로도
            # 만들어 넣지 않는다).
            if "description" in columns and item.get("description"):
                updates[f"{columns['description']}{row}"] = item["description"]
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
            # 썬데이워커 세액(V열)은 항목별 표시 칸일 뿐 합계 수식(V35=R35*0.1)과는 무관해서
            # 그냥 공급가액의 10%를 직접 써도 총합계엔 영향 없다(2026-08-11 원본 수식 확인).
            for extra_key, extra_value in _derive_extra_columns(columns, item["amount"], work_days, quantity).items():
                updates[f"{columns[extra_key]}{row}"] = extra_value
            if "note" in columns and item.get("note"):
                updates[f"{columns['note']}{row}"] = item["note"]
    return updates, hidden_rows


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


def resolve_catalog_entity_id(supabase, entity_id: str, entity_name: str, task_type: str) -> str:
    """이 법인×과업종류가 실제 카탈로그가 없어 다른 법인 것을 차용하는 조합이면(부록 B), 그
    출처 법인 id를 반환한다 — work_days/quantity를 그 출처 카탈로그에서 찾아야 하기 때문."""
    _, is_borrowed, source_name = catalog_service._resolve_catalog_rows(entity_id, entity_name, task_type)
    if not is_borrowed:
        return entity_id
    src = supabase.table("entity_templates").select("id").eq("name", source_name).execute()
    return src.data[0]["id"] if src.data else entity_id


def _fetch_quote_row(entity_quote_id: str) -> dict:
    quote_res = (
        get_supabase()
        .table("entity_quotes")
        .select(
            "id, entity_id, task_types, recipient_name, recipient_contact, recipient_phone, recipient_email, "
            "quote_date, service_name, total_amount, "
            "line_items, selected_modules, "
            "estimate_sets(vat_included), entity_templates(name)"
        )
        .eq("id", entity_quote_id)
        .execute()
    )
    if not quote_res.data:
        raise HTTPException(status_code=404, detail="견적서를 찾을 수 없습니다.")
    return quote_res.data[0]


def _quote_content_hash(quote: dict) -> str:
    return hashlib.sha256(json.dumps(quote, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _build_filled_xlsx_from_quote(quote: dict, filled_path: Path) -> None:
    """법인 마스터 xlsx의 가변 셀만 채워 filled_path에 저장한다. PDF 발급과 xlsx 다운로드가
    이 함수 하나를 공유해 두 파일의 내용이 항상 일치한다(2026-07-10)."""
    supabase = get_supabase()

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

    entity_name = quote["entity_templates"]["name"]
    task_types = quote["task_types"]
    catalog_entity_id_by_task_type = {
        task_type: resolve_catalog_entity_id(supabase, quote["entity_id"], entity_name, task_type)
        for task_type in task_types
    }

    # 과업종류를 교차 선택한 견적서는 시트 후보·항목 축약 단계가 여러 개일 수 있다 — 1순위가
    # 칸 수를 넘으면(_assign_groups_to_blocks의 422) 다음 후보/축약 단계로 넘어간다(_resolve_assignment).
    template, source_bytes, sheet_xml, columns, assignments = _resolve_assignment(
        supabase, quote["entity_id"], task_types, quote["selected_modules"], quote["line_items"]
    )
    cell_map = template["cell_map"]

    item_updates, hidden_rows = _collect_item_block_updates(
        supabase,
        cell_map.get("item_blocks", []),
        columns,
        assignments,
        catalog_entity_id_by_task_type,
        sheet_xml,
    )

    updates: CellUpdates = {}
    updates.update(_collect_header_updates(cell_map.get("header_fields", {}), quote))
    updates.update(item_updates)
    updates.update(_collect_totals_updates(cell_map.get("totals", {}), grand_total, vat_amount, supply_amount))
    for coord in cell_map.get("always_clear_cells", []):
        updates[coord] = None

    _patch_xlsx(
        source_bytes,
        template["sheet_name"],
        updates,
        filled_path,
        hidden_rows=hidden_rows,
        item_blocks=[b for b in cell_map.get("item_blocks", []) if b.get("role") != "labor_fte"],
        strip_background=(entity_name == "ABBG"),
    )


def render_entity_quote_xlsx(entity_quote_id: str) -> bytes:
    """마스터 xlsx의 가변 셀만 채운 결과를 변환 없이 그대로 xlsx bytes로 반환한다."""
    quote = _fetch_quote_row(entity_quote_id)
    with tempfile.TemporaryDirectory() as tmp_dir:
        filled_path = Path(tmp_dir) / "filled.xlsx"
        _build_filled_xlsx_from_quote(quote, filled_path)
        return filled_path.read_bytes()


# 같은 LibreOffice 프로필 디렉터리(아래 _PROFILE_DIR)를 동시에 여러 요청이 열면 조용히 lock
# 충돌이 나서 변환이 실패하는 걸 확인했다(2026-08-09 — 화면에 비교견적 카드 여러 개가 동시에
# PDF 미리보기를 요청할 때 재현. stderr/stdout 없이 그냥 실패). 이 서버 프로세스 안에서는
# 변환을 한 번에 하나씩만 실행하도록 직렬화하고, 그래도 실패하면(락이 풀리는 타이밍에 다시
# 겹치는 등) 1회 재시도한다.
_LIBREOFFICE_LOCK = threading.Lock()

# 요청마다 새 프로필을 쓰면 폰트 캐시가 매번 콜드 스타트라 렌더링이 깨지는 걸 확인했다(같은
# 파일을 재변환하면 정상으로 돌아옴 — 캐시가 데워진 뒤엔 문제 없음). 그렇다고 이 컴퓨터에서
# 실행 중일 수 있는 다른 LibreOffice(GUI 앱 등)와 프로필을 공유해 잠금 충돌이 나는 것도 피하고
# 싶어서, 이 서비스 전용으로 고정된 프로필 디렉터리를 한 번만 만들고 계속 재사용한다. 프로젝트
# 경로 자체에 공백이 있어 file:// URI가 깨지므로, 공백 없는 시스템 임시 경로에 둔다.
_PROFILE_DIR = Path(tempfile.gettempdir()) / "estimate_automation_lo_profile"

_lo_listener: Optional[subprocess.Popen] = None


def start_lo_listener() -> None:
    """LibreOffice를 서버 기동 시 미리 백그라운드로 띄워둔다.

    요청마다 soffice 프로세스를 새로 켜면 오피스 코어 콜드 부팅에 2~8초가 걸리는데, 같은
    UserInstallation 프로필로 상주 인스턴스를 하나 켜두면 이후 --convert-to 요청이 LibreOffice의
    "같은 프로필=단일 인스턴스" 동작으로 그 인스턴스에 붙어서 처리돼 1초 이내로 줄어드는 걸
    확인했다(2026-08-10 로컬 벤치마크: 콜드 3.06s → 리스너 사용 시 0.76s).
    # ponytail: 리스너가 중간에 죽어도 자동 재기동하지 않는다 — 아래 convert_cmd는 리스너 유무와
    # 무관하게 항상 동작하므로(없으면 콜드 스타트로 그냥 느려질 뿐) 정확성엔 영향 없음. 서버
    # 재시작 전까지 계속 느려지는 게 체감되면 그때 헬스체크+재기동을 추가한다.
    """
    global _lo_listener
    if _lo_listener is not None and _lo_listener.poll() is None:
        return
    try:
        _lo_listener = subprocess.Popen(
            [
                "soffice",
                f"-env:UserInstallation=file://{_PROFILE_DIR}",
                "--headless",
                "--invisible",
                "--nologo",
                "--norestore",
                "--accept=socket,host=127.0.0.1,port=2002;urp;",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        _lo_listener = None


def stop_lo_listener() -> None:
    global _lo_listener
    if _lo_listener is None:
        return
    # soffice 실행 파일은 실제로는 셸 래퍼라 자식으로 진짜 LibreOffice 바이너리(soffice.bin)를
    # fork/exec하고 래퍼 자신은 곧바로 끝나버린다. 그래서 Popen이 돌려준 pid/pgid로는(래퍼가 이미
    # 죽고 없어서) 진짜 바이너리를 못 찾는 경우가 있는 걸 확인했다(2026-08-10, os.killpg가
    # ProcessLookupError). pid 대신 이 서비스 전용 프로필 경로로 명령행을 매칭해 죽이면 래퍼가
    # 먼저 죽어 있어도 실제 바이너리를 확실히 잡는다.
    subprocess.run(["pkill", "-f", f"UserInstallation=file://{_PROFILE_DIR}"], capture_output=True)
    _lo_listener = None


# entity_quote_id -> (content_hash, pdf_bytes). 견적 내용(항목·금액·용역명 등)이 바뀌지 않았으면
# LibreOffice 변환(5~6초)을 매 조회마다 반복할 이유가 없다 — quote row 전체를 해시해 키로 쓰므로
# 채팅 수정이든 직접편집이든 내용이 실제로 바뀐 시점에만 자동으로 캐시가 무효화된다. 프로세스
# 재시작 시 비워지는 건 의도된 동작(사용자 1인·단일 프로세스라 별도 저장소 불필요).
_pdf_cache: Dict[str, tuple[str, bytes]] = {}


def render_entity_quote_pdf(entity_quote_id: str) -> bytes:
    quote = _fetch_quote_row(entity_quote_id)
    content_hash = _quote_content_hash(quote)
    cached = _pdf_cache.get(entity_quote_id)
    if cached and cached[0] == content_hash:
        return cached[1]

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_dir_path = Path(tmp_dir)
        filled_path = tmp_dir_path / "filled.xlsx"
        _build_filled_xlsx_from_quote(quote, filled_path)

        convert_cmd = [
            "soffice",
            f"-env:UserInstallation=file://{_PROFILE_DIR}",
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(tmp_dir_path),
            str(filled_path),
        ]
        pdf_path = filled_path.with_suffix(".pdf")
        last_error = ""
        with _LIBREOFFICE_LOCK:
            for attempt in range(2):
                result = subprocess.run(convert_cmd, capture_output=True, text=True, timeout=60)
                if result.returncode == 0 and pdf_path.exists():
                    pdf_bytes = pdf_path.read_bytes()
                    _pdf_cache[entity_quote_id] = (content_hash, pdf_bytes)
                    return pdf_bytes
                last_error = result.stderr or result.stdout

        raise HTTPException(
            status_code=500,
            detail=f"PDF 변환에 실패했습니다: {last_error}",
        )