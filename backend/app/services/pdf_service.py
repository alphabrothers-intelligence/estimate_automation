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
from app.services import catalog_service, quote_pricing, template_storage, xlsx_rows

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


# ─── 셀 폭 계산 (글자 깨짐 방지) ────────────────────────────────────────────────
# 마스터 양식의 "구분(대)" 같은 칸은 폭이 한글 3~4자밖에 안 되는데 모듈명은 "자사몰 데이터 세팅"
# 처럼 길어서, wrapText만 켜두면 단어 중간이 잘려 세로로 한 글자씩 쌓이고 행 높이를 넘어가는
# 부분은 아예 잘려나갔다(2026-08-20 사용자 지적, 테스티파이·알파브라더스 양식). 칸에 실제로 몇
# 글자가 들어가는지 알아야 "줄바꿈으로 담을지 / 글자를 줄여 담을지"를 정할 수 있어서, 열 폭과
# 병합 범위를 시트 XML에서 직접 읽는다.
_DEFAULT_COL_WIDTH = 8.43  # 엑셀 기본 열 폭(문자 수 단위)
_CELL_PADDING = 1.0  # 좌우 여백 몫


def _col_index(letters: str) -> int:
    index = 0
    for ch in letters:
        index = index * 26 + (ord(ch) - 64)
    return index


def _column_widths(sheet_xml: str) -> Dict[int, float]:
    """<cols> 정의에서 열 번호 -> 폭(문자 수 단위)."""
    widths: Dict[int, float] = {}
    for tag in re.findall(r"<col\b[^>]*/>", sheet_xml):
        attrs = dict(re.findall(r'(\w+)="([^"]*)"', tag))
        if "width" not in attrs or "min" not in attrs or "max" not in attrs:
            continue
        for col in range(int(attrs["min"]), int(attrs["max"]) + 1):
            widths[col] = float(attrs["width"])
    return widths


def _merge_spans(sheet_xml: str) -> Dict[str, tuple]:
    """병합 좌상단 좌표 -> (시작 열 번호, 끝 열 번호). 병합된 칸은 그 폭을 다 쓸 수 있다."""
    return {
        f"{c1}{r1}": (_col_index(c1), _col_index(c2))
        for c1, r1, c2, _r2 in re.findall(r'<mergeCell ref="([A-Z]+)(\d+):([A-Z]+)(\d+)"/>', sheet_xml)
    }


def _text_width(text: str) -> float:
    """한글·한자·전각 문자는 폭 단위('0' 한 글자) 기준으로 대략 두 배를 차지한다."""
    return sum(2.0 if ord(ch) > 0x2E7F else 1.0 for ch in text)


def _font_size_by_style(styles_xml: str) -> tuple:
    """(스타일 인덱스 -> 글자 크기, 기본 글자 크기). 열 폭은 워크북 기본 글꼴 기준이라, 셀
    글꼴이 그보다 작으면 같은 폭에 그만큼 더 들어간다(테스티파이 마스터: 기본 11pt, 표 안 8pt →
    1.375배). 이 보정을 빼면 안 넘치는 글자까지 넘친다고 판단해 쓸데없이 줄이거나 행을 키운다."""
    fonts_block = re.search(r"<fonts\b[^>]*>(.*?)</fonts>", styles_xml, re.DOTALL)
    if not fonts_block:
        return {}, 11.0
    sizes = [
        float(sz.group(1)) if (sz := re.search(r'<sz val="([\d.]+)"', font)) else 11.0
        for font in re.findall(r"<font\b[^>]*?(?:/>|>.*?</font>)", fonts_block.group(1), re.DOTALL)
    ]
    xfs_block = re.search(r"<cellXfs\b[^>]*>(.*?)</cellXfs>", styles_xml, re.DOTALL)
    by_style: Dict[int, float] = {}
    if xfs_block:
        for idx, xf in enumerate(re.findall(r"<xf\b[^>]*?(?:/>|>.*?</xf>)", xfs_block.group(1), re.DOTALL)):
            font_id = int(m.group(1)) if (m := re.search(r'fontId="(\d+)"', xf)) else 0
            if font_id < len(sizes):
                by_style[idx] = sizes[font_id]
    return by_style, (sizes[0] if sizes else 11.0)


def _capacity_fn(sheet_xml: str, styles_xml: str):
    """좌표 -> 그 칸에 들어가는 글자 폭(문자 수 단위). 병합 폭과 셀 글꼴 크기를 함께 본다."""
    widths = _column_widths(sheet_xml)
    spans = _merge_spans(sheet_xml)
    size_by_style, base_size = _font_size_by_style(styles_xml)

    def capacity(coord: str) -> Optional[float]:
        m = re.match(r"([A-Z]+)(\d+)$", coord)
        if not m:
            return None
        start, end = spans.get(coord, (_col_index(m.group(1)), _col_index(m.group(1))))
        total = sum(widths.get(col, _DEFAULT_COL_WIDTH) for col in range(start, end + 1))
        cm = re.search(rf'<c r="{re.escape(coord)}"[^>]*?(?:/>|>)', sheet_xml)
        style = int(s.group(1)) if cm and (s := re.search(r'\ss="(\d+)"', cm.group(0))) else None
        scale = base_size / size_by_style.get(style, base_size) if style is not None else 1.0
        return max((total - _CELL_PADDING) * scale, 1.0)

    return capacity


def _wrapped_line_count(text: str, capacity: Optional[float]) -> int:
    """wrapText로 담았을 때 실제 몇 줄이 되는지 — 행 높이를 그만큼 확보하려고 센다.

    엑셀은 공백에서 우선 끊고, 한 단어가 칸보다 길면 그 안에서 잘라 다음 줄로 넘긴다.
    """
    if capacity is None:
        return text.count("\n") + 1
    lines = 0
    for paragraph in text.split("\n"):
        used, count = 0.0, 1
        for word in re.split(r"(\s+)", paragraph):
            width = _text_width(word)
            if used and used + width > capacity:
                count += 1
                used = 0.0
                if word.isspace():
                    continue
            # 단어 하나가 칸보다 길면 칸 폭만큼씩 잘려 여러 줄을 먹는다.
            while width > capacity:
                count += 1
                width -= capacity
            used += width
        lines += count
    return lines


# shrinkToFit은 글자를 줄여 한 줄에 밀어넣는다. 살짝 줄이는 건 깔끔하지만 많이 줄여야 하면
# 읽을 수 없는 크기가 된다 — 폭 4.7칸에 폭 18짜리 "퍼포먼스 광고 운영"을 넣으라고 하니 26%
# (8pt→2pt)로 찌그러져 나왔다(2026-08-21 사용자 신고, 알파브라더스 구분 칸). 이 비율 밑으로
# 줄여야 하면 차라리 줄바꿈한다. 한글은 글자 단위로 접히므로 단어 중간에서 끊겨도 읽힌다.
_MIN_SHRINK_RATIO = 0.75

# 항목 행 높이 계산(pt). 줄당 높이 + 위아래 여백, 그리고 한 줄짜리 행의 최소 높이.
_LINE_HEIGHT = 16.0
_ROW_VERTICAL_PADDING = 12.0
_MIN_ITEM_ROW_HEIGHT = 30.0


def _fit_mode(text: str, capacity: Optional[float]) -> str:
    """넘치는 글자를 어떻게 담을지 — "shrink"(글자 줄이기) 또는 "wrap"(줄바꿈)."""
    if capacity is None:
        return "wrap"
    longest_word = max((_text_width(word) for word in text.split()), default=0.0)
    if longest_word <= capacity:
        return "wrap"  # 줄바꿈만으로 담긴다
    if _text_width(text) <= capacity / _MIN_SHRINK_RATIO:
        return "shrink"  # 조금만 줄이면 한 줄에 들어간다
    return "wrap"


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


def _ensure_alignment(sheet_xml: str, styles_xml: str, coord_attrs: Dict[str, Dict[str, str]]) -> tuple[str, str]:
    """셀별로 필요한 <alignment> 속성을 보장한다 (wrapText / shrinkToFit / horizontal / vertical).

    줄바꿈(\\n)이 들어간 값을 쓰는 셀(예: ABBG "상세내용" 칸의 세로형 개조식 목록, PRD 6.2)이
    원래 wrapText 서식이 없으면(2026-08-10 확인 — ABBG 마스터의 해당 칸이 그랬다) 한 줄로
    뭉개져 찍힌다. 그 셀의 스타일을 필요한 속성만 바꾼 새 스타일로 복제해 바꿔치기한다 — 같은
    스타일을 공유하는 다른 셀(서식이 원래대로여야 함)에는 영향을 주지 않는다.
    """
    if not coord_attrs:
        return sheet_xml, styles_xml
    m = re.search(r'(<cellXfs count=")(\d+)(">)(.*?)(</cellXfs>)', styles_xml, re.DOTALL)
    if not m:
        return sheet_xml, styles_xml
    count = int(m.group(2))
    body = m.group(4)
    xf_entries = re.findall(r'<xf\b[^>]*?(?:/>|>.*?</xf>)', body, re.DOTALL)
    new_entries: List[str] = []
    style_cache: Dict[tuple, int] = {}

    for coord, attrs in coord_attrs.items():
        cm = re.search(rf'<c r="{re.escape(coord)}"[^>]*?(?:/>|>)', sheet_xml)
        if not cm:
            continue
        s_match = re.search(r'\ss="(\d+)"', cm.group(0))
        if not s_match:
            continue
        old_idx = int(s_match.group(1))
        if old_idx >= len(xf_entries):
            continue
        xf = xf_entries[old_idx]
        # 원본이 이미 원하는 값을 다 갖고 있으면 스타일을 새로 만들 이유가 없다.
        missing = {k: v for k, v in attrs.items() if not re.search(rf'{k}="{v}"', xf)}
        if not missing:
            continue
        cache_key = (old_idx, tuple(sorted(missing.items())))
        if cache_key not in style_cache:
            align_match = re.search(r"<alignment\b[^>]*/>", xf)
            if align_match:
                align_tag = align_match.group(0)
                for key, value in missing.items():
                    # .xls에서 변환된 마스터(블렌디드랩 등)는 wrapText="false"처럼 true/false
                    # 표기를 쓴다 — "1"만 보고 없다고 판단해 속성을 또 붙이면 속성이 중복
                    # 지정된 잘못된 XML이 되어 styles.xml 전체가 깨진다(2026-08-10 발견).
                    if f"{key}=" in align_tag:
                        align_tag = re.sub(rf'{key}="[^"]*"', f'{key}="{value}"', align_tag)
                    else:
                        align_tag = align_tag[:-2] + f' {key}="{value}"/>'
                patched_xf = xf[: align_match.start()] + align_tag + xf[align_match.end() :]
            elif xf.endswith("/>"):
                attr_text = " ".join(f'{k}="{v}"' for k, v in missing.items())
                patched_xf = xf[:-2] + f"><alignment {attr_text}/></xf>"
            else:
                continue  # 이미 있는 <alignment>...</alignment> 형태는 드물어 다루지 않는다
            style_cache[cache_key] = count + len(new_entries)
            new_entries.append(patched_xf)
        new_idx = style_cache[cache_key]
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


def _block_rows(item_blocks: List[dict]) -> set:
    """항목 블록이 차지하는 모든 행 번호 — 항목 행 + 카테고리 라벨/소계/구분 칸이 있는 행."""
    rows: set = set()
    for block in item_blocks:
        rows.update(block.get("rows") or [])
        for value in block.values():
            if isinstance(value, str) and (m := re.match(r"^[A-Z]+(\d+)$", value)):
                rows.add(int(m.group(1)))
    return rows


# 가운데 정렬까지 해줄 칸 — 모듈명·구분(중)·상품명처럼 "짧은 라벨이 들어갈 좁은 칸"이다.
# (사용자 요청 2026-08-20: "가운데 정렬과 글씨가 적당히 잘려서 들어갔으면 좋겠습니다")
_CENTERED_COLUMN_KEYS = ("category", "category_mid", "item_name")


def _plan_text_fitting(
    sheet_xml: str, styles_xml: str, updates: CellUpdates, item_blocks: List[dict], columns: Dict[str, str]
) -> Dict[str, Dict[str, str]]:
    """셀에 넣는 글자가 칸을 넘칠 때 어떻게 담을지 셀별로 정한다.

    - 줄바꿈으로 담을 수 있으면 wrapText (행 높이는 _normalize_block_row_heights가 맞춘다)
    - 한 단어조차 칸보다 넓으면 wrapText로는 단어 중간이 깨지므로 shrinkToFit으로 글자를 줄인다
      (LibreOffice는 병합셀에도 shrinkToFit을 적용하지만, wrapText가 켜져 있으면 무시하므로
      반드시 함께 꺼야 한다 — 2026-08-20 실제 변환으로 확인)
    """
    capacity = _capacity_fn(sheet_xml, styles_xml)
    block_rows = _block_rows(item_blocks)
    centered_cols = {columns.get(key) for key in _CENTERED_COLUMN_KEYS if columns.get(key)}

    plan: Dict[str, Dict[str, str]] = {}
    for coord, value in updates.items():
        text = _cell_text_for_wrap(value)
        if not text:
            continue
        m = re.match(r"^([A-Z]+)(\d+)$", coord)
        in_block = bool(m) and int(m.group(2)) in block_rows
        if not in_block and "\n" not in text:
            continue  # 항목 표 밖의 한 줄짜리 값(수신처·용역명 등)은 원본 서식 그대로 둔다
        attrs: Dict[str, str] = {}
        if _fit_mode(text, capacity(coord)) == "shrink":
            attrs.update({"shrinkToFit": "1", "wrapText": "0"})
        else:
            attrs["wrapText"] = "1"
        if in_block and (m.group(1) in centered_cols or _is_category_cell(coord, item_blocks)):
            attrs.update({"horizontal": "center", "vertical": "center"})
        plan[coord] = attrs
    return plan


def _is_category_cell(coord: str, item_blocks: List[dict]) -> bool:
    return any(
        block.get(key) == coord
        for block in item_blocks
        for key in ("category_large_cell", "category_mid_cell", "category_label_cell")
    )


def _normalize_block_row_heights(
    sheet_xml: str, styles_xml: str, item_blocks: List[dict], updates: CellUpdates
) -> str:
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

    # 줄수는 \n 개수가 아니라 "칸 폭에 맞춰 접힌 뒤의 실제 줄수"로 센다 — \n만 세던 예전 방식은
    # 긴 한 줄이 칸 폭에서 두세 줄로 접히는 걸 몰라서 그만큼 아래가 잘렸다(2026-08-20 사용자
    # 지적, 테스티파이 "상품구성" 칸). shrinkToFit으로 줄인 칸은 한 줄이라 세지 않는다.
    capacity = _capacity_fn(sheet_xml, styles_xml)
    lines_by_row: Dict[int, int] = {}
    for coord, value in updates.items():
        text = _cell_text_for_wrap(value)
        if not text:
            continue
        m = re.match(r"^[A-Z]+(\d+)$", coord)
        if not m:
            continue
        cap = capacity(coord)
        if _fit_mode(text, cap) == "shrink":
            continue  # 글자를 줄여 한 줄에 담으므로 행 높이를 키울 필요가 없다
        row = int(m.group(1))
        lines_by_row[row] = max(lines_by_row.get(row, 1), _wrapped_line_count(text, cap))

    # 행 높이는 그 행이 실제로 담는 줄수로 정한다. 예전엔 마스터의 기존 ht를 최소값으로 깔고
    # 블록 전체를 가장 높은 행에 맞췄는데, 알파브라더스·테스티파이 마스터의 항목 행이 ht=150이라
    # 한 줄짜리 항목까지 150pt가 됐다. A4 인쇄 영역이 700pt 남짓이라 한 장에 네 행밖에 안 들어가
    # 표가 페이지 경계에서 뜯기고 앞장에 큰 여백이 남았다(2026-08-21 사용자 신고).
    # ponytail: 줄당 16pt는 폰트 메트릭 기반 정밀 측정이 아닌 고정 근사치 — 줄바꿈 셀이 잘리는
    # 사례가 나오면 실측 계산으로 교체.
    target_height_by_row: Dict[int, float] = {}
    for block in item_blocks:
        for row in block.get("rows") or []:
            lines = lines_by_row.get(row, 1)
            target_height_by_row[row] = max(
                _MIN_ITEM_ROW_HEIGHT, _LINE_HEIGHT * lines + _ROW_VERTICAL_PADDING
            )

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


def _unused_rows_before_totals(cell_map: dict, item_updates: CellUpdates) -> set:
    """항목 블록이 끝난 뒤 합계 행 사이에서, 이번 견적이 쓰지 않은 행들.

    썬데이워커 마스터에는 예전 고객 파일의 잔재가 그대로 남아 있다 — "투입 리소스" 라벨과
    세액 칸의 리터럴 0이 열 줄 넘게. 값만 비우면 빈 줄이 그대로 남아 합계가 저 아래로 밀리므로
    행 자체를 숨긴다(2026-08-21 사용자 신고). 숨은 행도 SUM 범위에는 그대로 들어가므로 합계는
    영향받지 않는다.

    grand_total_row가 있는 양식(현재 썬데이워커)에만 적용된다 — 나머지 양식은 항목 블록 바로
    아래가 합계라 사이에 낄 행이 없다.
    """
    totals_row = (cell_map.get("totals") or {}).get("grand_total_row")
    block_rows = [r for b in (cell_map.get("item_blocks") or []) for r in (b.get("rows") or [])]
    if not totals_row or not block_rows:
        return set()
    written = {
        int(m.group(1)) for coord in item_updates if (m := re.match(r"[A-Z]+(\d+)$", coord))
    }
    return {row for row in range(max(block_rows) + 1, totals_row) if row not in written}


def _plan_item_name_merges(sheet_xml: str, columns: Dict[str, str], assignments: list) -> List[tuple]:
    """품명 칸을 같은 열의 다른 행들이 쓰는 병합 폭에 맞춘다.

    썬데이워커 마스터는 머리글(B12:F12)과 아래 투입 리소스 블록(B20:F20)은 B~F로 병합돼
    있는데 정작 항목 행(13~19)만 병합이 빠져 있다. 그래서 품명이 한 열 폭(4.8 = 두 글자)에
    갇혀 "기술성 테스트 설계"가 "기술성/테스트/설계"로 접혀 나왔다(2026-08-21 사용자 신고).
    원본이 의도한 폭은 그 열에서 가장 흔한 병합 폭이라고 보고 그걸 그대로 쓴다.
    이미 같은 폭으로 병합된 양식(알파브라더스 E13:H13 등)에서는 같은 범위를 다시 만들 뿐이다.
    """
    col = columns.get("item_name")
    if not col:
        return []
    ends = Counter(re.findall(rf'<mergeCell ref="{col}\d+:([A-Z]+)\d+"/>', sheet_xml))
    if not ends:
        return []
    end_col = ends.most_common(1)[0][0]
    if _col_index(end_col) <= _col_index(col):
        return []
    rows = {row for block, _g, _o in assignments for row in (block.get("rows") or [])}
    return [(col, row, end_col, row) for row in sorted(rows)]


def _merge_end_col(sheet_xml: str, anchor: str) -> str:
    """그 칸이 원본에서 어느 열까지 가로 병합돼 있었는지(예: A13:B17 → "B")."""
    m = re.search(rf'<mergeCell ref="{anchor}:([A-Z]+)\d+"/>', sheet_xml)
    return m.group(1) if m else re.match(r"([A-Z]+)", anchor).group(1)


def _plan_category_merges(sheet_xml: str, assignments: list) -> List[tuple]:
    """블록마다 구분(대)/구분(중) 칸을 그 블록의 행 전체에 걸쳐 다시 병합한다.

    마스터에는 첫 블록의 세로 병합(알파브라더스 A13:B17, C13:D17)만 들어 있다. 카테고리가
    늘어 블록을 복제하면 가로 병합만 따라오고(xlsx_rows._single_row_merges는 한 행 안에서
    끝나는 병합만 복제한다) 이 병합은 빠진다. 그러면 둘째 블록부터 구분 칸이 한 열 폭(5.7)으로
    쪼그라들어 "그로스해킹"이 "그로/스해/킹"으로 접혀 나왔다(2026-08-21 사용자 신고).

    끝 열은 첫 블록에 남아 있는 원본 병합에서 읽어 그대로 쓴다.
    반환: [(시작열, 시작행, 끝열, 끝행), ...]
    """
    ranges: List[tuple] = []
    for key in ("category_large_cell", "category_mid_cell"):
        anchors = [block[key] for block, _g, _o in assignments if block.get(key)]
        if not anchors:
            continue
        end_col = _merge_end_col(sheet_xml, anchors[0])
        for block, _group, _offset in assignments:
            anchor = block.get(key)
            rows = block.get("rows") or []
            if not anchor or not rows:
                continue
            col = re.match(r"([A-Z]+)", anchor).group(1)
            ranges.append((col, min(rows), end_col, max(rows)))
    return ranges


def _plan_mid_category_merges(sheet_xml: str, columns: Dict[str, str], assignments: list) -> List[tuple]:
    """구분(중) 칸을 "같은 값이 연달아 오는 행"끼리 하나로 병합할 범위를 계산한다.

    실제 발급본(우유곳간 260811)에서 구분(대) "런칭 마케팅" 아래 구분(중)이 자사몰 구축(1행)/
    전략수립(1행)/기본 세팅(3행)으로 묶여 있는 모양을 그대로 재현한다. 원본 파일의 병합 모양은
    그 견적서의 데이터에 맞춰진 것이라 이번 견적 항목과는 맞지 않으므로, 데이터에서 다시 만든다.
    반환: [(시작열, 시작행, 끝열, 끝행), ...]
    """
    col = columns.get("category_mid")
    if not col:
        return []
    # 이 열이 원래 어느 열까지 병합돼 있었는지 원본에서 읽는다(예: C13:D13 → D).
    m = re.search(rf'<mergeCell ref="{col}\d+:([A-Z]+)\d+"/>', sheet_xml)
    end_col = m.group(1) if m else col

    ranges: List[tuple] = []
    for block, group, row_offset in assignments:
        rows = block["rows"]
        runs: List[tuple] = []  # (값, 첫 행, 마지막 행)
        for i, item in enumerate(group["items"]):
            row_index = row_offset + i
            if row_index >= len(rows):
                break
            value = item.get("mid_category") or group["category"]
            if runs and runs[-1][0] == value:
                runs[-1] = (value, runs[-1][1], rows[row_index])
            else:
                runs.append((value, rows[row_index], rows[row_index]))
        ranges.extend((col, start, end_col, end) for _value, start, end in runs)
    return ranges


def _apply_merge_ranges(sheet_xml: str, ranges: List[tuple]) -> str:
    """지정한 범위로 병합을 다시 만든다 — 해당 행들에 걸쳐 있던 기존 병합은 먼저 걷어낸다."""
    if not ranges:
        return sheet_xml
    touched = {(col, row) for col, start, _end_col, end in ranges for row in range(start, end + 1)}
    sheet_xml = re.sub(
        r'<mergeCell ref="([A-Z]+)(\d+):[A-Z]+\d+"/>',
        lambda m: "" if (m.group(1), int(m.group(2))) in touched else m.group(0),
        sheet_xml,
    )
    return _renumber_merge_count(
        _add_merge_refs(sheet_xml, [f"{c}{s}:{ec}{e}" for c, s, ec, e in ranges])
    )


def _add_merge_refs(sheet_xml: str, refs: List[str]) -> str:
    m = re.search(r'<mergeCells[^>]*>', sheet_xml)
    if not m:
        return sheet_xml
    return sheet_xml[: m.end()] + "".join(f'<mergeCell ref="{ref}"/>' for ref in refs) + sheet_xml[m.end() :]


def _renumber_merge_count(sheet_xml: str) -> str:
    count = len(re.findall(r"<mergeCell ", sheet_xml))
    return re.sub(r'<mergeCells count="\d+"', f'<mergeCells count="{count}"', sheet_xml, count=1)


def _drop_formulas(sheet_xml: str, coords: List[str]) -> str:
    """지정한 셀의 <f>를 없애 평범한 값 셀로 만든다 — _patch_sheet_xml이 "수식 셀은 값을 덮어쓰지
    않는다"는 규칙을 갖고 있어서, 우리가 계산한 값을 꼭 써야 하는 셀은 먼저 수식을 걷어내야 한다."""
    for coord in coords:
        m = _cell_pattern(coord).search(sheet_xml)
        if not m or not _has_formula(m.group(3) or ""):
            continue
        inner = re.sub(r"<f[^>]*>.*?</f>|<f[^>]*/>", "", m.group(3) or "", flags=re.DOTALL)
        sheet_xml = sheet_xml[: m.start()] + f'<c r="{coord}"{m.group(1)}>{inner}</c>' + sheet_xml[m.end() :]
    return sheet_xml


def _patch_xlsx(
    source_bytes: bytes,
    sheet_name: str,
    updates: CellUpdates,
    dest_path: Path,
    hidden_rows: Optional[set] = None,
    item_blocks: Optional[List[dict]] = None,
    strip_background: bool = False,
    drop_formula_cells: Optional[List[str]] = None,
    merge_ranges: Optional[List[tuple]] = None,
    columns: Optional[Dict[str, str]] = None,
) -> None:
    with zipfile.ZipFile(io.BytesIO(source_bytes), "r") as zin:
        sheet_path = _sheet_internal_path(zin, sheet_name)
        sheet_xml = zin.read(sheet_path).decode("utf-8")
        # 글자 폭 계산(_capacity_fn)이 셀 글꼴 크기를 봐야 해서 스타일을 먼저 읽어둔다.
        styles_xml = zin.read("xl/styles.xml").decode("utf-8")
        styles_xml = _patch_font_substitution(styles_xml)
        styles_xml = _patch_hyperlink_style_bleed(styles_xml)
        sheet_xml = _drop_formulas(sheet_xml, drop_formula_cells or [])
        sheet_xml = _apply_merge_ranges(sheet_xml, merge_ranges or [])
        patched_sheet_xml = _patch_sheet_xml(sheet_xml, updates)
        if strip_background:
            patched_sheet_xml = _strip_sheet_background_picture(patched_sheet_xml)
        patched_sheet_xml = _strip_sheet_hyperlinks(patched_sheet_xml)
        patched_sheet_xml = _strip_all_formula_caches(patched_sheet_xml)
        patched_sheet_xml = _hide_rows(patched_sheet_xml, hidden_rows or set())
        patched_sheet_xml = _normalize_block_row_heights(patched_sheet_xml, styles_xml, item_blocks or [], updates)
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

        patched_sheet_xml, patched_styles_xml = _ensure_alignment(
            patched_sheet_xml,
            styles_xml,
            _plan_text_fitting(patched_sheet_xml, styles_xml, updates, item_blocks or [], columns or {}),
        )

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






def get_column_display(supabase, entity_id: str, task_types: List[str], selected_modules: Optional[list]) -> Dict[str, Any]:
    """미리보기 UI가 법인마다 다른 실제 원본 양식 그대로 컬럼명·순서를 보여주기 위한 정보를
    반환한다(2026-07-10 — 같은 의미라도 법인마다 명칭이 다름: 예) 작업일/소요일, 수량/작업수량).
    템플릿을 못 찾는 경우(러프 비교견적 등)는 실패시키지 않고 빈 값으로 대체한다. 과업종류를
    교차 선택한 견적서는 실제 배정 시점에야 어느 양식이 쓰일지 확정되므로(용량 초과 시 다음
    후보로 넘어감, _resolve_host_templates), 여기서는 1순위 후보 기준으로 근사해 보여준다."""
    try:
        template = _resolve_host_templates(supabase, entity_id, task_types, selected_modules)[0]
    except HTTPException:
        return {
            "column_labels": {},
            "detail_column_order": [],
            "amount_uses_work_days": False,
            "amount_uses_quantity": True,
        }
    cell_map = template["cell_map"]
    form = resolve_form_spec(supabase, entity_id, task_types, selected_modules)
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
        # 화면 편집이 발급본과 같은 식으로 금액을 계산해야 한다 — 법인마다 수식이 달라서
        # (알파브라더스 단가×작업일×수량 / 블렌디드랩 =단가) 프론트엔드가 "단가×수량"으로
        # 하드코딩하면 단가를 고치는 순간 화면과 발급본이 갈린다(2026-08-21 발견).
        **{
            "amount_uses_work_days": form.uses_work_days,
            "amount_uses_quantity": form.uses_quantity,
        },
    }


def resolve_form_spec(
    supabase, entity_id: str, task_types: List[str], selected_modules: Optional[list]
) -> quote_pricing.FormSpec:
    """이 견적서가 쓸 양식의 금액 규칙(FormSpec)을 마스터 xlsx에서 직접 읽어 온다.

    생성 시점에 필요하다 — AI에게 "이 양식의 공급가액은 단가×수량이다"라고 알려주고, 받은
    결과를 같은 규칙으로 검산해야 화면 총액과 발급본 총액이 갈리지 않는다(2026-08-21 재설계).
    과업종류를 교차 선택한 견적서는 실제 배정 시점에야 어느 시트가 쓰일지 확정되므로
    get_column_display와 같은 기준(1순위 후보)으로 근사한다 — 후보들끼리 수식이 다른 경우는
    알파브라더스 통합 패키지뿐이고, 그건 모듈 선택으로 이미 갈린다.

    템플릿을 못 찾거나 시트를 못 읽으면 기본값(단가×수량)으로 대체한다. 다섯 법인 중 넷이
    그 규칙이라 최악의 경우에도 발급본이 깨지지 않고, 미리보기가 생성 자체를 막지 않는다.
    """
    try:
        template = _resolve_host_templates(supabase, entity_id, task_types, selected_modules)[0]
        cell_map = template["cell_map"]
        blocks = cell_map.get("item_blocks") or []
        source = template_storage.download(template["storage_path"])
        sheet_xml = _read_sheet_xml(source, template["sheet_name"])
    except (HTTPException, KeyError, IndexError, ValueError):
        return quote_pricing.FormSpec()
    return quote_pricing.detect_form(
        sheet_xml,
        cell_map.get("columns", {}),
        blocks[0]["rows"][0],
        labels=cell_map.get("column_labels", {}),
    )


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
            # 아직 안 적었으면 칸을 통째로 비운다(원본 플레이스홀더 "OOO 귀하"가 찍히면 안 되고,
            # 이름 없는 " 귀하"도 보기 흉하다). 나중에 채우면 그때 정상 표기된다.
            updates[coord] = f"{quote['recipient_name']} 귀하" if quote.get("recipient_name") else ""
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
            # 패턴) — 값만 쓰면 라벨이 지워진다(2026-08-13 사용자 발견). 용역명도 선택 입력이라
            # 비어 있으면 라벨만 덩그러니 남기지 않고 칸을 비운다.
            updates[coord] = f"용역명: {quote['service_name']}" if quote.get("service_name") else ""
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


def _is_name_only_form(columns: Dict[str, str], blocks: List[dict]) -> bool:
    """품명 한 칸에 모든 걸 담아야 하는 양식인가 (블렌디드랩·썬데이워커).

    구분(대)/구분(중) 칸도, 상품구성 칸도 없으면 세부 항목을 따로 적을 자리가 없다. 이런
    양식에 세부 항목을 행으로 늘려 담으면 "위클리 성과 리뷰 세션" 같은 낱개 이름만 죽 나열되어
    무슨 묶음인지 알 수 없다 — 실제 발급본은 "퍼포먼스 그로스 운영 (위클리 성과 리뷰 세션 /
    주간 실행 태스크 처리)"처럼 구분명 뒤 괄호에 세부를 넣는다(2026-08-21 사용자 지적).
    """
    if "description" in columns or "category_mid" in columns:
        return False
    return not any(b.get("category_large_cell") or b.get("category_mid_cell") for b in blocks)


def _rollup_to_category_totals(
    groups: List[Dict[str, Any]], inline_names: bool = False
) -> List[Dict[str, Any]]:
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
    def folded(g: Dict[str, Any]) -> Dict[str, Any]:
        names = [it["name"] for it in g["items"]]
        # 상품구성 칸이 없는 양식은 세부를 적을 데가 여기뿐이라 품명 뒤 괄호에 넣는다.
        # 괄호는 반드시 **다음 줄**에서 시작한다 — 품명 옆에 바로 붙으면 어디까지가 품명인지
        # 구분이 안 됐다(2026-08-21 사용자 지적). 칸 폭을 넘치면 _plan_text_fitting이 괄호
        # 안에서 다시 줄을 바꿔 담고 행 높이를 늘린다.
        name = f"{g['category']}\n({' / '.join(names)})" if inline_names else g["category"]
        return {
            "category": g["category"],
            "amount": g["amount"],
            "items": [{
                "category": g["category"],
                "name": name,
                "amount": g["amount"],
                # 묶음 한 줄에는 대표 단가가 없지만, 양식의 공급가액 칸은 대부분 수식이라
                # (블렌디드랩 AB=+W, 썬데이워커 R=N*K, 알파브라더스 AA=SUM(T*V*X)) 단가를
                # 비워두면 LibreOffice 재계산에서 금액도 합계도 0으로 나간다(2026-08-21 신고).
                # 작업일·수량 1, 단가=묶음 총액이면 위 세 수식 모두 정확히 총액이 된다.
                "unit_price": g["amount"],
                "work_days": 1,
                "quantity": 1,
                # 그룹 안 항목은 전부 같은 category(=module_name)라 같은 과업종류에 속한다.
                "task_type": g["items"][0].get("task_type") if g["items"] else None,
                "description": None if inline_names else "\n".join(
                    f"{i + 1}. {it['name']}" for i, it in enumerate(g["items"])
                ),
            }],
        }

    return [g if len(g["items"]) <= 1 else folded(g) for g in groups]


def _description_parts(text: Optional[str]) -> List[str]:
    """상품구성("1. A\n2. B")을 괄호 안에 슬래시로 이어 붙일 조각으로 쪼갠다. 번호는 뗀다."""
    if not text:
        return []
    return [
        stripped
        for line in text.splitlines()
        if (stripped := re.sub(r"^\s*\d{1,2}[.)]\s*", "", line).strip())
    ]


def _fold_name_only(groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """품명 한 칸짜리 양식(블렌디드랩·썬데이워커)의 기본 표시 방식.

    항목에 상품구성이 있으면 **항목마다 한 줄**을 쓰고 그 항목의 상품구성을 괄호에 넣는다:
    "MVP 제작\n(MVP 상세페이지 디자인 작업 / MVP별 랜딩페이지 구축 / GA 등 분석 Tool 구축)".
    본견적(테스티파이)의 상품명이 이 양식의 품명이 되고, 상품구성이 그 아래 괄호에 들어간다
    — 2026-08-24 실무자 지적("품목이 안 쪼개지고 하나에 다 들어감").

    상품구성이 없는 카탈로그(마케팅류)는 괄호에 넣을 게 없으니 예전처럼 카테고리당 한 줄로
    묶고 항목명을 괄호에 넣는다. 낱개 이름만 죽 나열하면 무슨 묶음인지 안 보이기 때문이다.

    항목마다 한 줄이면 각 줄이 자기 단가·수량을 그대로 들고 가므로, 묶음 줄에 단가가 없어
    양식 수식이 금액을 0으로 재계산하던 문제(2026-08-21)는 애초에 생기지 않는다.
    """
    folded: List[Dict[str, Any]] = []
    for group in groups:
        if not any(item.get("description") for item in group["items"]):
            folded.append(_rollup_to_category_totals([group], inline_names=True)[0])
            continue
        items = []
        for item in group["items"]:
            parts = _description_parts(item.get("description"))
            items.append(dict(item, name=f"{item['name']}\n({' / '.join(parts)})" if parts else item["name"]))
        folded.append({**group, "items": items})
    return folded


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


def _assign_groups_to_blocks(
    groups: List[Dict[str, Any]], blocks: List[dict], columns: Dict[str, str], allow_rollup: bool = True
) -> List[tuple]:
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
    elif _is_name_only_form(columns, blocks):
        # 품명 한 칸짜리 양식(블렌디드랩·썬데이워커)은 세부를 적을 다른 칸이 없어 품명 아래
        # 괄호에 넣는 게 기본 표시 방식이다. 상품구성이 있으면 항목당 한 줄, 없으면 카테고리당
        # 한 줄로 묶는다 — 자세한 건 _fold_name_only.
        groups = _fold_name_only(groups)

    # 카테고리 전용 블록 — 카테고리 라벨 칸이든 구분(대) 칸이든, 그 블록이 카테고리 하나를
    # 통째로 담는다는 뜻이라 똑같이 "그룹 1개 = 블록 1개"로 배정한다. 구분(대)에 모듈명을 넣게
    # 되면서(2026-08-19) 예전의 "과업종류 하나당 블록 하나"(_try_assign_flat_by_task_type)는
    # 성립하지 않는다 — 한 블록에 모듈 여럿을 몰아넣으면 구분(대) 칸이 마지막 모듈명으로
    # 덮어써지기 때문.
    category_blocks = [b for b in blocks if b.get("category_label_cell") or b.get("category_large_cell")]
    flat_blocks = [b for b in blocks if b not in category_blocks]

    if flat_blocks and not category_blocks:
        assignments = _try_assign_flat(groups, flat_blocks)
        if assignments is not None:
            return assignments
        if allow_rollup:
            # 품명 한 칸짜리 양식(블렌디드랩·썬데이워커)은 세부를 적을 다른 칸이 없어
            # 품명 뒤 괄호에 넣는다: "퍼포먼스 그로스 운영 (위클리 성과 리뷰 / 주간 실행)".
            assignments = _try_assign_flat(
                _rollup_to_category_totals(groups, inline_names=_is_name_only_form(columns, blocks)),
                flat_blocks,
            )
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
    if len(groups) > len(category_blocks):
        raise HTTPException(
            status_code=422,
            detail=f"이 양식은 카테고리 {len(category_blocks)}개까지만 담을 수 있는데 항목이 {len(groups)}개 카테고리로 나뉘어 있습니다.",
        )
    assignments = _try_assign_labeled(groups, blocks)
    if assignments is not None:
        return assignments
    if not allow_rollup:
        # 접기 전에 먼저 행을 늘려 보라는 뜻 — 호출부(_resolve_assignment)가 양식을 키운 뒤
        # 다시 부른다(2026-08-19). 여기서 접어버리면 세부 항목이 소계 한 줄로 사라진다.
        raise HTTPException(status_code=422, detail="양식 블록에 항목을 그대로 담을 자리가 부족합니다.")
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


def _plan_row_growth(groups: List[Dict[str, Any]], blocks: List[dict]) -> List[tuple]:
    """항목이 양식의 고정 행 수를 넘을 때, 어느 행을 몇 개 복제해 끼워 넣을지 계획한다.

    2026-08-19 사용자 요청 — 화면/채팅으로 항목을 추가하면 PDF·xlsx에도 실제로 새 행이 생겨야
    한다. 그전에는 여기서 422로 막거나 카테고리 소계 한 줄로 접어 세부 항목을 잃었다.

    남는 행은 어차피 _hide_rows가 숨기므로 넉넉히 늘려도 출력에는 영향이 없다 — 그래서 배정
    전략(_try_assign_labeled / _try_assign_flat)을 그대로 다시
    구현하지 않고, 어떤 전략이 뽑히든 성립하도록 블록마다 "필요한 최대치"로 늘린다.

    복제 원본은 블록의 "끝에서 두 번째" 행을 쓴다 — 마지막 행을 복제하면 삽입 지점이 블록
    합산 수식(=SUM(H29:I30))의 범위 밖이라 그 수식이 새 행을 포함하도록 늘어나지 않는다
    (2026-08-19 재현). 첫 행은 표를 여는 테두리 서식이 다를 수 있어 피한다.
    """
    if not blocks or not groups:
        return []
    category_blocks = [b for b in blocks if b.get("category_label_cell") or b.get("category_large_cell")]
    if category_blocks:
        # 블록 하나가 카테고리 하나를 통째로 담으므로, 가장 큰 카테고리가 들어갈 만큼 늘린다.
        needed = max(len(g["items"]) for g in groups)
    else:
        # 플랫 양식은 카테고리 구분 없이 이어 담으므로 전체 항목 수만큼 자리가 있으면 된다.
        needed = sum(len(g["items"]) for g in groups)

    plan = []
    for block in blocks:
        rows = block["rows"]
        if needed > len(rows):
            clone_row = rows[-2] if len(rows) > 1 else rows[0]
            plan.append(([clone_row] * (needed - len(rows)), clone_row))
    return plan


def _row_of(coord: str) -> int:
    return int(re.match(r"[A-Z]+(\d+)", coord).group(1))


def _block_source_rows(block: dict) -> List[int]:
    """블록을 통째로 복제할 때 함께 복제해야 하는 행 — 카테고리 라벨/소계가 항목 행 위의 별도
    행에 있는 양식(테스티파이 구양식 등)은 그 행까지 포함해야 새 블록이 온전하다."""
    rows = set(block["rows"])
    for key in ("category_label_cell", "category_subtotal_cell"):
        if block.get(key):
            rows.add(_row_of(block[key]))
    return sorted(rows)


def _plan_block_growth(groups: List[Dict[str, Any]], blocks: List[dict]) -> Optional[tuple]:
    """카테고리 칸(블록) 자체가 모자라면 마지막 블록을 통째로 복제할 계획을 세운다.
    반환: (복제 원본 행 목록, 삽입 위치 행, 추가 블록 수) 또는 None."""
    category_blocks = [b for b in blocks if b.get("category_label_cell") or b.get("category_large_cell")]
    if not category_blocks or len(groups) <= len(category_blocks):
        return None
    source_rows = _block_source_rows(category_blocks[-1])
    return source_rows, max(source_rows), len(groups) - len(category_blocks)


def _appended_blocks(template_block: dict, source_rows: List[int], after_row: int, copies: int) -> List[dict]:
    """복제로 새로 생긴 블록들의 cell_map 항목을 만든다. 원본 블록의 셀 좌표를 그대로 쓰되
    행 번호만 복제본 위치로 바꾼다."""
    size = len(source_rows)
    new_blocks = []
    for copy_index in range(copies):
        offset = after_row + copy_index * size
        row_of_source = {src: offset + i + 1 for i, src in enumerate(source_rows)}
        block = {"rows": [row_of_source[r] for r in template_block["rows"]]}
        for key in ("category_label_cell", "category_subtotal_cell", "category_large_cell", "category_mid_cell"):
            if template_block.get(key):
                coord = template_block[key]
                block[key] = re.sub(r"\d+", str(row_of_source[_row_of(coord)]), coord)
        new_blocks.append(block)
    return new_blocks


def _grow_template(template: dict, source_bytes: bytes, groups: List[Dict[str, Any]]) -> Optional[tuple]:
    """부족한 만큼 시트에 행·블록을 실제로 끼워 넣은 (template, source_bytes, sheet_xml)을
    돌려준다. 늘릴 게 없으면 None — 호출부가 기존 동작(접기/422)으로 넘어간다."""
    with zipfile.ZipFile(io.BytesIO(source_bytes), "r") as zin:
        sheet_path = _sheet_internal_path(zin, template["sheet_name"])

    def apply(current_bytes: bytes, current_map: dict, jobs: list) -> tuple:
        grown_bytes, row_map = xlsx_rows.expand_sheet_rows(
            current_bytes, sheet_path, template["sheet_name"], jobs
        )
        return grown_bytes, xlsx_rows.remap_cell_map(current_map, row_map), row_map

    cell_map = template["cell_map"]
    changed = False

    # 1단계: 기존 블록의 행 수를 모자란 만큼 늘린다.
    blocks = [b for b in cell_map.get("item_blocks", []) if b.get("role") != "labor_fte"]
    row_plan = _plan_row_growth(groups, blocks)
    if row_plan:
        source_bytes, new_cell_map, row_map = apply(source_bytes, cell_map, row_plan)
        # 새로 끼워 넣은 행은 원본에 없던 번호라 remap_cell_map이 모른다 — 복제 원본 바로 아래
        # 연속된 번호이므로 여기서 직접 채워 넣는다.
        for original, grown in zip(cell_map.get("item_blocks", []), new_cell_map.get("item_blocks", [])):
            added = [
                r
                for rows, after in row_plan
                if after in original["rows"]
                for r in range(row_map[after] + 1, row_map[after] + 1 + len(rows))
            ]
            grown["rows"] = sorted(set(grown["rows"]) | set(added))
        cell_map, changed = new_cell_map, True

    # 2단계: 카테고리 칸(블록) 수가 모자라면, 1단계로 이미 넓어진 마지막 블록을 통째로 복제한다.
    blocks = [b for b in cell_map.get("item_blocks", []) if b.get("role") != "labor_fte"]
    block_plan = _plan_block_growth(groups, blocks)
    if block_plan:
        source_rows, after_row, copies = block_plan
        template_block = [b for b in blocks if b.get("category_label_cell") or b.get("category_large_cell")][-1]
        source_bytes, new_cell_map, _row_map = apply(
            source_bytes, cell_map, [(source_rows * copies, after_row)]
        )
        new_cell_map["item_blocks"] = new_cell_map.get("item_blocks", []) + _appended_blocks(
            template_block, source_rows, after_row, copies
        )
        cell_map, changed = new_cell_map, True

    if not changed:
        return None
    # 소계·합계 셀은 원본에 수식으로 들어있는데(예: 합계 = H15+H28+H20+H24) 그 수식은 원본
    # 블록 개수를 손으로 나열한 것이라, 블록을 복제해 늘리면 새 블록의 소계가 빠진 채 계산된다.
    # 늘린 시트에서는 이 셀들의 수식을 걷어내고 우리가 계산한 값을 그대로 쓴다(2026-08-19) —
    # 항목 행의 공급가액 수식(=E16*F16*G16)은 단가 역산 로직이 의존하므로 그대로 둔다.
    cell_map = {
        **cell_map,
        "drop_formula_cells": sorted(
            # totals에는 셀 좌표뿐 아니라 행 번호(썬데이워커 grand_total_row: 35)도 섞여 있다 —
            # 좌표만 걸러내지 않으면 str과 int를 함께 정렬하다 TypeError로 발급이 죽는다
            # (2026-08-20, 썬데이워커 마케팅에서 행을 늘릴 때 재현).
            {value for value in cell_map.get("totals", {}).values() if isinstance(value, str)}
            | {b["category_subtotal_cell"] for b in cell_map.get("item_blocks", []) if b.get("category_subtotal_cell")}
        ),
    }
    return (
        {**template, "cell_map": cell_map},
        source_bytes,
        _read_sheet_xml(source_bytes, template["sheet_name"]),
    )


def _assignment_attempts(template: dict, source_bytes: bytes, sheet_xml: str, groups: List[Dict[str, Any]]):
    """(양식, 파일bytes, 시트xml, 접기허용) 후보를 순서대로 내놓는다.

    1) 원본 그대로 — 들어가면 기존 견적서 출력이 그대로 유지된다.
    2) 행·블록을 실제로 끼워 넣어 늘린 양식 — 항목을 하나도 잃지 않는다.
    3) 그래도 안 되면 원본에 카테고리 소계로 접어 담는다(예전 최후 수단 그대로).

    2번을 3번보다 먼저 두는 게 핵심이다 — 순서가 반대면 자리가 모자랄 때 조용히 접혀서
    세부 항목(상품명·상품구성)이 소계 한 줄로 사라진다(2026-08-19 재현).
    """
    columns = template["cell_map"].get("columns", {})
    blocks = template["cell_map"].get("item_blocks", [])
    yield template, source_bytes, sheet_xml, False
    # 품명 한 칸짜리 양식은 _assign_groups_to_blocks가 같은 방식으로 묶으므로, 늘릴 줄 수도
    # 묶은 뒤의 줄 수를 기준으로 센다 — 안 그러면 쓰지도 않을 행만 끼워 넣고 숨기게 된다.
    if _is_name_only_form(columns, blocks):
        groups = _fold_name_only(groups)
    grown = _grow_template(template, source_bytes, groups)
    if grown is not None:
        yield (*grown, False)
    yield template, source_bytes, sheet_xml, True


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
            columns = template["cell_map"].get("columns", {})
            try:
                source_bytes = template_storage.download(storage_path)
                sheet_xml = _read_sheet_xml(source_bytes, template["sheet_name"])
            except HTTPException as e:
                last_error = e
                continue

            # 원본 행 수 그대로 담기면 그대로 쓴다 — 기존 견적서의 출력이 달라지지 않게, 행
            # 삽입은 정말 자리가 모자랄 때만 한다(2026-08-19).
            for candidate_template, candidate_bytes, candidate_sheet_xml, allow_rollup in _assignment_attempts(
                template, source_bytes, sheet_xml, groups
            ):
                blocks = [
                    b for b in candidate_template["cell_map"].get("item_blocks", [])
                    if b.get("role") != "labor_fte"
                ]
                try:
                    assignments = _assign_groups_to_blocks(groups, blocks, columns, allow_rollup)
                except HTTPException as e:
                    last_error = e
                    continue
                return candidate_template, candidate_bytes, candidate_sheet_xml, columns, assignments
    raise last_error or HTTPException(status_code=422, detail="이 견적서를 담을 수 있는 양식을 찾지 못했습니다.")








def _collect_item_block_updates(
    supabase,
    item_blocks: List[dict],
    columns: Dict[str, str],
    assignments: list,
    sheet_xml: str,
) -> tuple[CellUpdates, set]:
    blocks = [b for b in item_blocks if b.get("role") != "labor_fte"]
    updates: CellUpdates = {}
    hidden_rows: set = set()

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
        # 구분(대)에는 모듈명(=group["category"], 예: "런칭 마케팅"/"퍼포먼스")을 넣는다
        # (2026-08-19 사용자 결정 — 이전엔 구분(대)/구분(중) 둘 다 과업종류명("마케팅")을 넣어
        # 두 칸이 같은 값으로 중복됐다). 구분(중)은 항목마다 다를 수 있어(런칭 마케팅 안의
        # 자사몰 구축/전략수립/기본 세팅) 블록 단위 셀이 아니라 아래 행별 컬럼으로 채운다.
        if block.get("category_large_cell"):
            updates[block["category_large_cell"]] = group["category"]
        if block.get("category_mid_cell"):
            # 구분(중) 전용 컬럼이 없는 옛 양식(알파브라더스)은 블록 셀 하나뿐이라, 그 블록
            # 항목들의 구분(중)이 모두 같을 때만 의미가 있다 — 섞여 있으면 모듈명으로 대체한다.
            mids = {item.get("mid_category") for item in group["items"]}
            updates[block["category_mid_cell"]] = mids.pop() if len(mids) == 1 and None not in mids else group["category"]

        for i, item in enumerate(group["items"]):
            row_index = row_offset + i
            if row_index >= len(rows):
                continue
            row = rows[row_index]
            # 저장된 값을 그대로 쓴다. 생성·수정 시점에 quote_pricing.finalize가 양식 수식으로
            # 금액을 확정하고 저장 관문(assert_storable)이 검사하므로, 발급 시점에 카탈로그를
            # 다시 뒤져 역산할 이유가 없다 — 그렇게 하면 화면에서 본 값과 발급본이 갈린다
            # (2026-08-21 재설계로 구 경로 삭제).
            unit_price = item.get("unit_price") or 0
            work_days = item.get("work_days") or 1
            quantity = item.get("quantity") or 1

            if "category_mid" in columns:
                # 구분(중)은 같은 값이 이어지는 행끼리 아래에서 병합하므로(_plan_mid_category_merges)
                # 여기서는 모든 행에 값을 채운다 — 병합되면 첫 행 값만 보인다.
                updates[f"{columns['category_mid']}{row}"] = item.get("mid_category") or group["category"]
            if "item_name" in columns:
                updates[f"{columns['item_name']}{row}"] = item["name"]
            # 상품구성(번호 매긴 세부항목) 전용 컬럼은 알파브라더스/ABBG 원본에만 있다 — 그
            # 컬럼이 없는 법인(테스티파이/블렌디드랩/썬데이워커)은 품명 칸에 접어 넣지 않고
            # 아예 표시하지 않는다(2026-08-14 사용자 결정 — 원본 양식에 없는 칸이면 괄호로도
            # 만들어 넣지 않는다).
            if "description" in columns and item.get("description"):
                # 카탈로그마다 "1. A / 2. B"(알파브라더스)와 줄바꿈형(테스티파이)이 섞여 있어
                # 여기서 세로형 개조식으로 통일한다(PRD 6.2, 2026-08-21 사용자 지적).
                updates[f"{columns['description']}{row}"] = catalog_service.normalize_description(
                    item["description"]
                )
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
    # 수신자·용역명이 비어도 발급을 막지 않는다(2026-08-20 사용자 결정) — 이 두 칸은 선택
    # 입력이고, 발급 후 "정보 수정"에서 채우면 그때 PDF에 반영된다. 예전엔 여기서 422가 나서
    # 이름을 안 적었다는 이유만으로 미리보기조차 안 떴다.

    # 소계·부가세·합계는 항목 금액의 합에서 직접 뽑는다 — 표에 찍히는 행들이 실제로 더해지는
    # 값이라 어긋날 수가 없다. 예전에는 estimate_sets.vat_included로 갈라 total_amount에서
    # 역산했는데, vat_included는 "생성할 때 입력한 총액이 부가세 포함이었나"라는 입력 플래그일
    # 뿐이고 저장된 total_amount는 항상 부가세 포함이라(estimate_service.update_line_items가
    # 두 경우 모두 소계×1.1로 저장) vat_included=false면 소계 칸에 총합계가 들어갔다.
    # 대부분의 양식은 이 칸들이 수식이라 우리가 쓴 값을 무시하고 행에서 다시 계산해 겉으로는
    # 드러나지 않았지만, 행을 늘린 시트(_grow_template)는 수식을 걷어내고 이 값을 그대로 쓴다
    # (2026-08-19 발견).
    supply_amount = sum(item["amount"] for item in quote["line_items"])
    vat_amount = round(supply_amount * 0.1)
    grand_total = supply_amount + vat_amount

    entity_name = quote["entity_templates"]["name"]
    task_types = quote["task_types"]

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
        sheet_xml,
    )
    hidden_rows |= _unused_rows_before_totals(cell_map, item_updates)

    # 항목 행의 "입력" 칸(상품명·상품구성·단가·작업일·수량·구분(중))에 수식이 남아 있으면
    # _patch_sheet_xml이 "수식 셀은 값을 덮어쓰지 않는다"는 규칙 때문에 우리가 계산한 값을
    # 무시한다. 실제로 테스티파이 신양식 마스터의 단가 칸 하나(Meta 광고 운영 = 실비의 10%)에
    # 견적별 수식이 남아 있어 총액이 1,100원 어긋났다(2026-08-19).
    # 공급가액 칸도 여기 포함한다(2026-08-21). 금액 규칙을 "단가 × 수량"으로 통일했는데
    # 마스터 원본 수식은 양식마다 다르다 — 알파브라더스 모듈 시트 SUM(작업일×수량×단가),
    # 블렌디드랩 =단가. 수식을 그대로 두면 엑셀이 우리 값을 무시하고 자기 식으로 다시 계산해
    # 화면과 발급본이 갈린다. 원본 파일을 고치는 대신 이 칸의 수식만 지우고 값을 쓴다.
    # 합계·부가세 수식은 이 칸들을 SUM하므로 그대로 두어도 맞는다.
    input_columns = [
        columns[key]
        for key in ("category_mid", "item_name", "description", "unit_price", "work_days",
                    "quantity", "supply_amount", "amount")
        if key in columns
    ]
    item_input_cells = [
        f"{col}{row}"
        for block in cell_map.get("item_blocks", [])
        for row in block["rows"]
        for col in input_columns
    ]

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
        drop_formula_cells=list(cell_map.get("drop_formula_cells") or []) + item_input_cells,
        merge_ranges=_plan_category_merges(sheet_xml, assignments)
        + _plan_item_name_merges(sheet_xml, columns, assignments)
        + _plan_mid_category_merges(sheet_xml, columns, assignments),
        columns=columns,
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
