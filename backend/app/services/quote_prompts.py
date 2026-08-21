"""본견적·비교견적 생성 프롬프트 (2026-08-21 금액 로직 재설계).

이 시스템의 정체는 금액 배분 엔진이 아니라 "AI 초안 + 사람 수정" 도구다. 실무자는 원래
본견적서를 직접 만든 뒤 비교견적서 항목명을 하나씩 살짝 바꾸고 가격을 다르게 책정하는
수작업에 시간을 다 썼고, 그걸 줄이려고 Claude 채팅창에 본견적서를 붙여넣고 짧은 프롬프트로
비교견적서를 뽑아 쓰고 있었다. 그 왕복을 앱 안으로 넣는 게 전부다 — 초안 품질이 80%면
충분하고 나머지는 사람이 표에서 고친다.

프롬프트는 "무엇을 원하는지"만 말하게 하고, 산술 검산과 단위 정리는 코드(quote_pricing)가
한다. LLM에게 산술을 맡기면 합계가 목표와 어긋나거나 단위가 안 맞는 값이 섞여 나오는 걸
반복해서 확인했다 — 2026-08-20 실측에서 10건 중 2건이 단가 단위·수식을 어겼고, 후처리가
전부 잡아냈다. 그래서 코드 후처리는 생략 불가다.
"""

from typing import Dict, List, Optional, Sequence

from app.services.quote_pricing import FormSpec

# 항목별 인상률 허용 범위의 상한 = 사용자가 지정한 인상률 + 이 값(%). 전 항목에 똑같은 %를
# 곱한 견적서는 한눈에 조작으로 보여서, 항목마다 다른 인상률을 줄 여지를 만들어 준다.
_BAND_SPREAD = 15

_REFERENCE_STYLE = """[참고: 타사 견적서 실제 표기 사례 — 어휘·구성 톤만 참고하고 내용은 위 본견적서를 따른다]
- "WEB 기획 / PM (프로젝트 전체 관리자) / 기간(day) 90"
- "웹개발 / 1. 도메인 세팅 - 도메인 연결 작업 / EA 1"
- "콘텐츠마케팅 (블로그 콘텐츠 제작) / - 콘텐츠 기획 / ea 10 / unit price 120,000"
- "제품 촬영 / 스튜디오 대관·모델 섭외·사진 촬영/편집 / 수량 1 / 소요기간 20"
- "언론 홍보 / 원고작성·원고송출 / 단가 300,000 / 수량 3"
- "현지 기업 방문 프로그램 운영비 / 투입 인력 1 / 수량 1"
- "기업 소개자료 고도화 / 투입 인력 1 / 수량 4\""""


def _form_block(form: FormSpec) -> str:
    """양식 정의 — 수식·단가 단위·이 양식에 실제로 있는 컬럼."""
    lines = [f"- {form.formula_text}", f"- 단가 단위: {form.unit_price_unit:,}원의 배수"]
    derived = {"supply_amount", "amount", "input_mm", "tax_amount"}
    for key, label in (form.labels or {}).items():
        note = " (서버가 자동 계산 — 채우지 말 것)" if key in derived else ""
        lines.append(f'- {key}: 이 양식의 컬럼명은 "{label}"{note}')
    for key in ("work_days", "quantity", "description"):
        if key not in (form.labels or {}):
            lines.append(f"- {key}: 이 양식에는 해당 컬럼이 없음 — 반드시 null 로 둘 것")
    return "\n".join(lines)


def _money(value) -> str:
    return f"{int(value or 0):,}"


# ═══════════════════════════════════════════════════════════════════════
# 프롬프트 1 — 본견적서 항목 산정
# ═══════════════════════════════════════════════════════════════════════
PRIMARY_SYSTEM = """당신은 견적 산정 담당자입니다. 주어진 [표준 항목 카탈로그]의 항목을 하나도 빼거나 더하지 않고, 각 항목의 작업일·수량·단가를 산정해 [목표 공급가액]에 맞는 견적서를 만듭니다.

[절대 규칙]

1. 항목 고정
   카탈로그 항목을 그대로, 같은 순서로, 같은 이름으로 출력한다. 합치거나 쪼개거나 추가·삭제하지 않는다. 출력의 i번째 항목은 입력의 i번째 항목이다.

2. 금액 공식
   이 견적서 양식의 공급가액 공식은 [양식 정의]에 적힌 그대로다. amount는 반드시 그 공식으로 계산한 값이어야 한다. 공식에 등장하지 않는 컬럼(예: 공식이 단가×수량이면 작업일)은 금액에 아무 영향이 없는 정보성 값이다.

3. 단가 단위
   단가는 [양식 정의]에 적힌 단위의 배수여야 한다. 만원·천원·원 단위로 떨어지는 단가는 실무에서 발행하지 않는다.

4. 작업일·수량은 업무량이다
   카탈로그의 표준 작업일·수량을 기본값으로 쓴다. 값은 반드시 정수다. 금액을 맞추려고 작업일·수량을 조작하지 않는다. 실제 업무량이 달라지는 경우에만 바꾸고, 한 묶음으로 움직이는 항목(예: 주간 Wrap-Up 16회 / 주간 액션플랜 16회)은 반드시 수량을 같게 유지한다.

5. 상대 중요도 유지
   카탈로그의 표준 단가는 "이 항목이 다른 항목보다 얼마나 비싼가"라는 상대 가격이다. 목표 금액이 표준 합계와 다르면 전 항목에 같은 배율을 곱하는 것을 원칙으로 하고, 3번의 단위 제약 때문에 생기는 오차만 조정한다. 특정 항목만 몇 배로 키우거나 최소 단위까지 짓누르지 않는다.

6. 합계 일치
   모든 amount의 합은 목표 공급가액과 정확히 같아야 한다. 출력 전에 반드시 직접 더해서 검산한다. 단위 제약 때문에 정확히 맞출 수 없으면 [조정 항목]으로 지정된 항목의 단가만 움직여 최대한 가깝게 맞추고 subtotal에는 실제 합계를 적는다. 다른 항목을 건드려 차액을 메우지 않는다.

7. 숫자만 낸다
   항목명·구분·상품구성은 카탈로그 값을 서버가 그대로 쓴다. 다시 적지 말고 작업일·수량·단가만 낸다. i는 카탈로그의 번호이며 1번부터 빠짐없이, 순서대로 전부 포함한다.

[출력 형식] JSON 객체 하나만. 설명·마크다운 코드블록 없이.
{"items": [{"i": 정수, "work_days": 숫자 또는 null, "quantity": 숫자 또는 null, "unit_price": 정수}], "subtotal": 정수}"""


def build_primary_user(
    entity: str,
    task_type: str,
    form: FormSpec,
    catalog_rows: Sequence[dict],
    target_supply: int,
    adjust_item: Optional[str] = None,
) -> str:
    """본견적 유저 프롬프트. catalog_rows는 카탈로그 행 dict(작업일·수량·표준단가 포함)."""
    lines = []
    for i, row in enumerate(catalog_rows, 1):
        parts = [f"{i}. [{row.get('module_name') or '-'}] {row['item_name']}"]
        parts.append(f"표준 작업일 {int(row.get('work_days') or 1)}")
        parts.append(f"표준 수량 {int(row.get('quantity') or 1)}")
        if row.get("unit_price"):
            parts.append(f"표준 단가 {_money(row['unit_price'])}원")
        if row.get("historical_ratio") is not None:
            parts.append(f"모듈 내 과거 비중 {row['historical_ratio']}%")
        block = " | ".join(parts)
        if row.get("standard_description"):
            block += f"\n   상품구성: {row['standard_description']}"
        lines.append(block)

    base = sum(form.amount_of(dict(row)) for row in catalog_rows)
    # 조정 항목을 안 정해주면 AI가 매번 다른 항목으로 잔액을 흡수해 결과가 흔들린다.
    # 기본값은 표준 금액이 가장 큰 항목 — 몇 % 움직여도 상대 중요도가 덜 깨진다.
    adjust = adjust_item or (
        max(catalog_rows, key=lambda r: form.amount_of(dict(r)))["item_name"] if catalog_rows else "-"
    )
    ratio = f"{target_supply / base:.4f}" if base else "계산 불가(표준 단가 없음)"

    return f"""[견적서 발행 법인] {entity}

[과업종류] {task_type}

[양식 정의]
{_form_block(form)}

[목표 금액]
- 목표 공급가액(VAT 별도, 모든 amount의 합이 이 값과 같아야 함): {_money(target_supply)}원
- 카탈로그 표준값 그대로 계산했을 때의 합계: {_money(base)}원
- 필요한 전체 배율: {ratio}
- [조정 항목] 단위 제약으로 생기는 잔액은 "{adjust}" 항목의 단가로만 흡수한다.

[표준 항목 카탈로그] (이 목록이 곧 출력할 항목 목록이다)
{chr(10).join(lines)}"""


# ═══════════════════════════════════════════════════════════════════════
# 프롬프트 2 — 비교견적서 리라이팅
# ═══════════════════════════════════════════════════════════════════════
COMPARISON_SYSTEM = """당신은 여러 대행사의 견적서를 검토해 온 견적 산정 전문가입니다. 입력으로 [확정된 본견적서] 1건, [비교견적서를 발행할 법인의 양식 정의], [목표 금액]을 받습니다. 당신의 일은 "같은 과업을, 다른 업체가 자기 방식으로 산정해 발행한 견적서"를 만드는 것입니다.

[절대 규칙]

1. 1:1 대응
   본견적서 항목 수와 순서를 그대로 유지한다. 항목을 합치거나 쪼개거나 추가·삭제하지 않는다. 출력의 i번째 항목은 입력의 i번째 항목에 대응하며, source_name에 대응하는 본견적 항목명을 그대로 적는다.

2. 다른 표현, 같은 내용
   모든 구분명(category)·항목명(name)·상세설명(description)은 본견적서와 다른 용어로 다시 쓴다. 본견적서와 같은 문자열을 쓰거나 조사·띄어쓰기·어순만 바꾸는 것은 실패다. 그러나 가리키는 산출물과 업무 범위는 본견적 항목과 완전히 같아야 하며, 담당자가 두 견적서를 나란히 놓고 봤을 때 "같은 일을 다른 회사가 다르게 부른 것"임을 알아볼 수 있어야 한다. 카탈로그에 없는 업무를 지어내지 않는다.
   - 표준 약어(FGI, GA4, GTM, SEO, MVP, BM, NPS 등)는 그 업계 공통어라 그대로 써도 된다. 대신 앞뒤 수식어를 바꾼다.
   - 구분명도 반드시 바꾼다. 예: "통합 패키지" → "종합 검증 프로그램", "온라인 광고" → "퍼포먼스 광고 운영".

3. 금액은 항상 본견적보다 높다
   모든 항목의 금액은 대응하는 본견적 항목보다 커야 한다. 같거나 작은 항목이 하나라도 있으면 실패다.

4. 인상률은 항목마다 다르게
   전 항목에 똑같은 %를 곱한 견적서는 한눈에 조작으로 보인다. [목표 금액]에 적힌 항목별 허용 범위 안에서 항목마다 다른 인상률을 준다. 다른 업체라면 더 비싸게 볼 만한 항목(운영·인력 투입이 많은 항목)을 더 올리고, 산출물이 단순한 항목은 덜 올린다.

5. 금액 공식과 단가 단위
   amount는 [양식 정의]의 공급가액 공식으로 계산한 값이어야 하고, 단가는 그 양식의 단가 단위 배수여야 한다. 공식에 등장하지 않는 컬럼은 금액에 영향이 없다.

6. 작업일·수량은 그 업체의 산정 방식이다
   본견적과 똑같이 베낄 필요가 없다. 다른 업체는 같은 일을 다른 기간·다른 인원으로 잡는다. 본견적 대비 0.7~1.5배 범위의 **정수**로 조정하되(며칠·몇 회·몇 인이라 소수가 될 수 없다), 그 값이 항목명·상세설명과 모순되지 않아야 한다(예: 상세에 "6인 모집"이라 써놓고 수량 2를 적지 않는다). 양식에 그 컬럼이 없으면 null.

7. 합계 일치
   각 항목의 금액은 [양식 정의]의 공식으로 계산되며, 그 합이 목표 공급가액과 정확히 같아야 한다. 출력 전에 반드시 직접 더해서 검산하고 subtotal에 그 합계를 적는다. amount는 서버가 공식으로 다시 계산하므로 적지 않는다. i는 대응하는 본견적 항목 번호이며 1번부터 순서대로 전부 포함한다.

8. 상세설명 형식
   상세설명(description)은 세로형 개조식으로 쓴다 — "1. 첫째 항목\n2. 둘째 항목\n3. 셋째 항목"처럼 번호를 매기고 줄바꿈(\n)으로 나눈다. 한 줄에 이어 붙이거나 슬래시로 구분하지 않는다. 발급 양식의 상품구성 칸이 세로 나열을 전제로 만들어져 있다.

[출력 형식] JSON 객체 하나만. 설명·마크다운 코드블록 없이.
{"items": [{"i": 정수, "category": "비교견적 구분명", "name": "비교견적 항목명", "description": "세로형 개조식 상세설명(줄바꿈 포함) 또는 null", "work_days": 숫자 또는 null, "quantity": 숫자 또는 null, "unit_price": 정수}], "subtotal": 정수}"""


def build_comparison_user(
    entity: str,
    task_type: str,
    form: FormSpec,
    primary_entity: str,
    primary_items: Sequence[dict],
    primary_supply: int,
    markup: float,
) -> str:
    """비교견적 유저 프롬프트. primary_items는 확정된 본견적의 line_items."""
    target = round(primary_supply * (1 + markup))
    pct = round(markup * 100)

    lines = []
    for i, it in enumerate(primary_items, 1):
        block = (
            f"{i}. [{it.get('category') or '-'}] {it['name']}"
            f" | 작업일 {it.get('work_days')} | 수량 {it.get('quantity')}"
            f" | 단가 {_money(it.get('unit_price'))}원 | 금액 {_money(it.get('amount'))}원"
        )
        if it.get("description"):
            block += f"\n   상품구성: {it['description']}"
        lines.append(block)

    return f"""[비교견적서 발행 법인] {entity}

[과업종류] {task_type}

[양식 정의]
{_form_block(form)}

[목표 금액]
- 확정된 본견적 공급가액: {_money(primary_supply)}원
- 사용자가 지정한 인상률: +{pct}%
- 목표 공급가액(모든 amount의 합이 이 값과 같아야 함): {_money(target)}원
- 항목별 인상률 허용 범위: +3% ~ +{pct + _BAND_SPREAD}%

[확정된 본견적서] (발행 법인: {primary_entity} / 과업: {task_type})
{chr(10).join(lines)}

{_REFERENCE_STYLE}"""


def extract_json(text: str, require_key: Optional[str] = None) -> dict:
    """응답에서 JSON 객체를 꺼낸다.

    "가장 바깥 { 부터 마지막 } 까지"를 자르던 예전 방식(allocation_service.extract_json)은
    모델이 설명 문단에 중괄호를 쓰면 통째로 깨진다 — 2026-08-20 비교견적 생성에서 실제로
    JSONDecodeError로 실패했다. 모든 '{' 위치에서 raw_decode를 시도해 가장 큰 객체를 고른다.

    require_key를 주면 그 키를 가진 객체만 후보로 본다. 호출부마다 응답 모양이 다르므로
    (견적 생성은 items, 모듈 선택은 selected) 필수 키를 호출부가 정한다 — 여기에 "items"를
    박아두었다가 모듈 선택이 항상 실패했다(2026-08-21 재현).
    """
    import json

    decoder = json.JSONDecoder()
    best: Optional[dict] = None
    for i, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(text[i:])
        except ValueError:
            continue
        if not isinstance(obj, dict) or (require_key and require_key not in obj):
            continue
        if best is None or len(obj) > len(best):
            best = obj
    if best is None:
        raise json.JSONDecodeError(
            f"JSON 객체를 찾지 못했습니다{f' (필수 키: {require_key})' if require_key else ''}", text, 0
        )
    return best
