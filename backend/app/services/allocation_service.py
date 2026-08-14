"""항목 자동생성 (PRD 7장) — Claude API로 총액을 카탈로그 항목별로 배분한다."""

import json
import re
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Tuple

from pydantic import BaseModel, ValidationError

from app.config import CLAUDE_MODEL, get_anthropic
from app.models.catalog import CatalogItem

SYSTEM_PROMPT = (
    "당신은 견적서 항목별 금액 배분 담당자입니다. 주어진 표준 항목 카탈로그와 과거 비중 데이터를 "
    "참고하여, 주어진 공급가액을 각 항목에 배분하세요. 반드시 JSON 객체 하나만 응답하고(설명, 마크다운 "
    '코드블록 없이), 배분된 금액(amount)의 합은 입력된 공급가액과 정확히 일치해야 합니다. 출력 형식: '
    '{"items": [{"category": "모듈명", "name": "항목명", "amount": 정수}], "subtotal": 정수}'
)


class AllocatedItem(BaseModel):
    category: str
    name: str
    amount: int
    # 채팅 수정에서만 쓰인다(edit_service.py) — 사용자가 작업일/수량/단가 중 하나를 명시적으로
    # 바꿔달라고 한 경우에만 Claude가 채우고, 나머지는 null로 둔다(2026-08-14). 항목 자동생성
    # (allocation_service._allocate_single_group)에서는 항상 null.
    unit_price: Optional[float] = None
    work_days: Optional[float] = None
    quantity: Optional[float] = None


class AllocationResult(BaseModel):
    items: List[AllocatedItem]
    subtotal: int


def _build_catalog_block(items: List[CatalogItem]) -> str:
    lines = []
    current_module = object()  # sentinel, 항상 첫 항목에서 헤더 출력
    for item in items:
        if item.module_name != current_module:
            if item.module_name:
                lines.append(f"\n[{item.module_name}]")
            current_module = item.module_name
        ratio = f" (과거 비중 {item.historical_ratio}%)" if item.historical_ratio is not None else ""
        lines.append(f"- {item.item_name}{ratio}")
    return "\n".join(lines).strip()


def extract_json(text: str) -> dict:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


def _call_claude(system: str, user_content: str) -> AllocationResult:
    client = get_anthropic()
    last_error: Optional[Exception] = None

    for attempt in range(2):
        message = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2048,
            system=system,
            messages=[{"role": "user", "content": user_content}],
        )
        text = next((b.text for b in message.content if b.type == "text"), "")
        try:
            data = extract_json(text)
            return AllocationResult.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as e:
            last_error = e
            user_content = (
                user_content
                + "\n\n[재시도] 이전 응답이 올바른 JSON이 아니었습니다. "
                + "설명 없이 JSON 객체 하나만 정확히 출력하세요."
            )

    raise RuntimeError(f"Claude 응답을 JSON으로 파싱하지 못했습니다: {last_error}")


def _reconcile_rounding(items: List[AllocatedItem], target_supply_amount: int) -> List[AllocatedItem]:
    """LLM이 반환한 금액 합이 목표 공급가액과 다르면 마지막 항목에서 차액을 흡수한다 (PRD 7.1-6)."""
    total = sum(i.amount for i in items)
    diff = target_supply_amount - total
    if diff != 0 and items:
        items[-1] = AllocatedItem(
            category=items[-1].category, name=items[-1].name, amount=items[-1].amount + diff
        )
    return items


def _allocate_single_group(items: List[CatalogItem], target_amount: int) -> List[AllocatedItem]:
    catalog_block = _build_catalog_block(items)
    user_content = (
        f"[표준 항목 카탈로그]\n{catalog_block}\n\n"
        f"[입력]\n공급가액(VAT 제외): {target_amount}원"
    )
    result = _call_claude(SYSTEM_PROMPT, user_content)
    return _reconcile_rounding(result.items, target_amount)


def _group_by_module(items: List[CatalogItem]) -> List[Tuple[Optional[str], List[CatalogItem]]]:
    """module_name이 바뀌는 지점마다 새 그룹을 만든다. 카탈로그 조회가 이미 module_name 기준으로
    정렬돼 있어(catalog_service._fetch_catalog_rows), 같은 모듈 항목은 항상 붙어 있다."""
    groups: List[Tuple[Optional[str], List[CatalogItem]]] = []
    for item in items:
        if groups and groups[-1][0] == item.module_name:
            groups[-1][1].append(item)
        else:
            groups.append((item.module_name, [item]))
    return groups


def _split_amount_evenly(total: int, n: int) -> List[int]:
    base = total // n
    shares = [base] * n
    shares[-1] += total - base * n  # 나머지는 마지막 몫이 흡수
    return shares


def allocate_items(catalog_items: List[CatalogItem], total_amount: int, vat_included: bool) -> dict:
    """총액을 항목별로 배분하고 VAT를 계산한다 (PRD 7.1 step5-7).

    여러 모듈이 조합된 경우(PRD 7장 3~4단계 — 예: 필수 "시장성 테스트" + 옵션 "설문형
    시장검증"), 각 모듈의 과거 비중(%)은 그 모듈 안에서만 100%로 정규화된 값이라 모듈들을
    합쳐 LLM에 한 번에 넘기면 모듈 간 배분 기준이 없어 한쪽 모듈에 0원을 배정하는 등
    엉뚱하게 배분하는 문제가 있었다. 이를 피하기 위해 목표 금액을 모듈 수만큼 균등 분할한
    뒤, 각 모듈은 독립적으로(기존 단일 모듈 로직 그대로) 배분한다.
    """
    if vat_included:
        supply_amount = round(total_amount / 1.1)
        vat_amount = total_amount - supply_amount
    else:
        supply_amount = total_amount
        vat_amount = round(supply_amount * 0.1)

    module_groups = _group_by_module(catalog_items)

    if len(module_groups) <= 1:
        items = _allocate_single_group(catalog_items, supply_amount)
    else:
        # 모듈별 배분은 서로 독립적인 Claude 호출이라 순서대로 기다릴 필요가 없다 — 동시에
        # 보내 전체 생성 시간을 모듈 수만큼 나눈다(견적 생성 속도 개선, 2026-07-10).
        shares = _split_amount_evenly(supply_amount, len(module_groups))
        with ThreadPoolExecutor(max_workers=len(module_groups)) as pool:
            results = list(
                pool.map(
                    lambda pair: _allocate_single_group(pair[0][1], pair[1]),
                    zip(module_groups, shares),
                )
            )
        items = [item for group_items in results for item in group_items]

    # 카탈로그의 상품구성 설명(예: 알파브라더스 "1. ... / 2. ...")을 배분 결과에 다시 붙인다 —
    # Claude 응답(AllocatedItem)엔 category/name/amount뿐이라 여기서 원본 카탈로그를 (모듈명,
    # 항목명)으로 다시 찾아 매칭한다. PDF 렌더링(pdf_service)이 "상품구성" 컬럼이 있는 양식에서
    # 이 값을 그대로 셀에 채운다.
    description_by_key = {(i.module_name, i.item_name): i.standard_description for i in catalog_items}
    line_items = []
    for item in items:
        row = item.model_dump()
        row["description"] = description_by_key.get((item.category, item.name))
        line_items.append(row)

    return {
        "line_items": line_items,
        "supply_amount": supply_amount,
        "vat_amount": vat_amount,
        "grand_total": supply_amount + vat_amount,
    }
