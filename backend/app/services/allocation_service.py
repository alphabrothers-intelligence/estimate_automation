"""항목 자동생성 (PRD 7장) — Claude API로 총액을 카탈로그 항목별로 배분한다."""

import json
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Tuple

from fastapi import HTTPException
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
    """응답에서 가장 바깥 { } 구간만 잘라 파싱한다.

    "설명 없이 JSON만" 이라고 시켜도 요청이 복잡하면(예: "소계는 유지하고 1만원 단위로 맞춰줘")
    계산 과정을 먼저 서술하고 그 뒤에 JSON을 붙여 보내는 걸 확인했다(2026-08-19 재현) — 응답
    전체를 json.loads하던 예전 방식은 그때마다 JSONDecodeError가 나서 재시도까지 실패하고
    채팅 수정이 통째로 500으로 죽었다. 코드블록(```json) 울타리도 중괄호 바깥이라 함께 잘린다.
    """
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        raise json.JSONDecodeError("응답에서 JSON 객체를 찾지 못했습니다", text, 0)
    return json.loads(text[start : end + 1])


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

    # RuntimeError로 올리면 Starlette가 CORSMiddleware 바깥(ServerErrorMiddleware)에서 500을
    # 만들어 CORS 헤더 없이 응답한다 — 브라우저가 이를 네트워크 오류로 처리해 프론트엔드엔
    # 실패 사유가 하나도 안 남고 "수정에 실패했습니다."만 떴다(2026-08-19 원인 규명).
    # HTTPException은 CORS 안쪽에서 처리되므로 사용자가 실제 사유를 볼 수 있다.
    raise HTTPException(status_code=502, detail=f"AI 응답을 해석하지 못했습니다: {last_error}")


# 견적 금액은 10만원 단위로 떨어지는 게 기본이다(2026-08-20 사용자 결정 — 그 전엔 1만원
# 단위였는데도 266,250원·6,222,727원 같은 값이 계속 발급됐다). 목표 금액 자체가 이 단위로 안
# 떨어지면 나머지는 가장 큰 항목이 흡수한다.
AMOUNT_UNIT = 100_000

# 단가가 떨어져야 하는 단위. 사용자가 정답으로 제시한 참고 견적서(data/(테스티파이) 우유곳간,
# 자사몰 그로스해킹 마케팅 견적서_260811.pdf)의 단가는 3,000,000 / 1,000,000 / 900,000 /
# 600,000 / 500,000 / 300,000 / 100,000 — 전부 10만원의 배수다.
UNIT_PRICE_UNIT = 100_000

# 비교견적서 전용 단위. 실무자는 마크업이 적용된 비교견적서를 100만원 단위 미만(만원/1000원/100원/
# 1원 단위)으로는 절대 발급하지 않는다(2026-08-20 사용자 요구) — 본견적서는 실제 참고 견적서의
# 단가 그대로(10만원 단위)를 유지해야 하므로 이 단위는 비교견적서에만 적용한다
# (pdf_service.compute_line_item_pricing, sync_service._scale_items_to_supply).
COMPARISON_AMOUNT_UNIT = 1_000_000


def reconcile_amounts(amounts: List[int], target: int, unit: int = 0) -> List[int]:
    """금액 목록을 목표 합계에 정확히 맞추고, unit이 주어지면 각 금액을 그 단위로 떨어뜨린다.

    LLM에게 산술을 맡기면 합계가 목표와 어긋나거나 요청한 단위가 안 지켜진 값이 섞여 나온다
    (PRD 7.1-6, 2026-08-19 채팅 수정에서 재현) — LLM은 "무엇을 원하는지"(목표 합계·단위)만
    뽑고 실제 계산은 항상 여기서 한다. 항목 자동생성(_reconcile_rounding)과 채팅 수정
    (edit_service)이 이 함수 하나를 공유해 두 경로의 결과 규칙이 같다.
    """
    if not amounts:
        return amounts

    def absorb_diff(values: List[int]) -> List[int]:
        # 남는 차액은 가장 큰 항목이 흡수한다 — target이 unit의 배수면 그 항목도 배수로 남는다.
        values = list(values)
        diff = target - sum(values)
        if diff:
            values[max(range(len(values)), key=lambda i: values[i])] += diff
        return values

    current = sum(amounts)
    scaled = [round(a * target / current) for a in amounts] if current > 0 and target != current else list(amounts)

    # 단위 반올림은 "단위 × 항목수"만큼의 여유가 있을 때만 시도한다 — 그보다 target이 작으면
    # 모든 항목을 최소 1단위로 올린 합이 target을 넘어 차액 흡수 시 음수가 나온다.
    if unit > 1 and target >= unit * len(scaled):
        fixed = absorb_diff([max(unit, round(a / unit) * unit) if a > 0 else 0 for a in scaled])
        if min(fixed) >= 0:
            return fixed
    return absorb_diff(scaled)


def grand_total(supply_amount: float, vat_included: bool) -> int:
    """공급가액 소계 -> VAT 포함 총액. 같은 식이 4개 서비스에 흩어져 있던 걸 모았다(2026-08-20)."""
    return round(supply_amount * 1.1) if vat_included else round(supply_amount + round(supply_amount * 0.1))


def amount_unit_for(is_primary: bool) -> int:
    """이 견적서의 단가가 떨어져야 하는 단위 — 본견적 10만원, 비교견적 100만원."""
    return UNIT_PRICE_UNIT if is_primary else COMPARISON_AMOUNT_UNIT


def snap_unit_price(amount: float, unit_price: Optional[float], unit: int = UNIT_PRICE_UNIT) -> tuple:
    """단가를 unit 배수로 떨어뜨리고, 공급가액을 그 단가에 맞춰 다시 계산한다.

    공급가액만 단위에 맞춰봐야 소용이 없다 — 단가는 공급가액÷(수량×작업일)로 역산되므로
    (pdf_service._compute_item_pricing), 수량이 16이면 4,260,000원짜리 항목의 단가가
    266,250원이 되어 발급본에 그대로 찍혔다(2026-08-20 사용자 지적). 그래서 단위를 맞추는
    기준을 공급가액이 아니라 단가로 뒤집는다: 단가를 10만원 배수로 스냅하고 공급가액을
    단가×배수로 되돌리면 둘 다 떨어진다(500,000 × 16 = 8,000,000).

    배수(수량×작업일)는 amount÷unit_price로 되찾는다 — 그 관계는 호출부가 이미 그렇게 만들어
    넘기므로, 여기서 수량·작업일을 따로 받지 않아도 값이 어긋나지 않는다.
    """
    if not unit_price or unit_price <= 0 or amount <= 0:
        return round(amount), unit_price
    divisor = amount / unit_price
    snapped = max(unit, round(unit_price / unit) * unit)
    return round(snapped * divisor), float(snapped)


def reconcile_snapped_items(items: List[dict], target_supply: int, unit: int) -> List[dict]:
    """항목 금액의 합을 목표 공급가액으로 정확히 되돌린다 — 조정 수단은 단가뿐이다.

    수량·작업일은 카탈로그가 정한 업무량(예: 주간 Wrap-Up 16회 = 4개월)이라 금액을 맞추려고
    건드리지 않는다. 예전에 수량으로 차액을 흡수했더니 한 묶음이어야 할 "주간 Wrap-Up 16회 /
    주간 액션플랜 16회"가 18회/19회로 어긋났다(2026-08-20 사용자 지적).

    한 걸음은 단가 1단위(=금액 unit×수량×작업일)다. 걸음이 크고 금액이 큰 항목부터 잔액을
    흡수시킨다 — 작은 항목에 나눠 담으면 100,000원짜리 항목이 200,000원(2배)이 되어 항목 간
    상대 중요도가 깨진다(2026-08-20 사용자 요구). 큰 항목이 몇 % 움직이는 쪽이 덜 왜곡된다.
    unit으로 못 맞춘 잔액은 더 잔 단위(10만원)로 한 번 더 흡수한다: 비교견적서 100만원 단위를
    끝까지 고집하면(단가 하한이 100만원이라) 목표에 아예 못 닿는 구성이 나온다.

    locked=True인 항목은 사용자가 채팅/화면에서 직접 지정한 금액이라 흡수 대상에서 뺀다 —
    "이 항목 단가 55만원" 이라고 콕 집어 말했는데 다른 항목 잔액을 메우느라 그 단가가 다시
    움직이면 안 된다(2026-08-20 사용자 지적).
    """
    items = [dict(item) for item in items]

    def divisor(item: dict) -> float:
        """수량×작업일 — 단가를 1원 올리면 공급가액이 이만큼 오른다."""
        unit_price = item.get("unit_price") or 0
        return item["amount"] / unit_price if unit_price > 0 else 0.0

    for step_unit in (unit, UNIT_PRICE_UNIT):
        diff = target_supply - sum(item["amount"] for item in items)
        if not diff:
            break
        for item in sorted(items, key=lambda i: (step_unit * divisor(i), i["amount"]), reverse=True):
            if item.get("locked"):
                continue
            d = divisor(item)
            step = step_unit * d
            if step <= 0:
                continue
            steps = int(diff / step)  # 0 쪽으로 버림 — 목표를 넘어서지 않는다
            if steps < 0:
                # 내릴 때만 하한을 건다 — 단가가 0 이하로 내려가면 안 된다. 예전엔 이 클램프를
                # max()로 무조건 걸어서, 단가가 step_unit보다 작은 항목(사용성 테스트 "일반테스터
                # 모집" 10,000원 같은 만원 단위 표준 단가)을 차액과 무관하게 한 단위 끌어올렸다 —
                # 수량이 100이라 그 한 걸음이 곧바로 +1,000만원이었다(2026-08-20 재현).
                steps = max(steps, -int((item["unit_price"] - 1) // step_unit))
            if not steps:
                continue
            item["unit_price"] += steps * step_unit
            before, item["amount"] = item["amount"], round(item["unit_price"] * d)
            diff -= item["amount"] - before
    return items


def _reconcile_rounding(items: List[AllocatedItem], target_supply_amount: int) -> List[AllocatedItem]:
    amounts = reconcile_amounts([i.amount for i in items], target_supply_amount, AMOUNT_UNIT)
    return [i.model_copy(update={"amount": a}) for i, a in zip(items, amounts)]


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
    # 몫 자체를 1만원 단위로 떨어뜨린다 — 그러지 않으면 모듈별 목표가 애매한 값이 되어
    # 모듈 안에서 아무리 단위를 맞춰도 한 항목이 그 나머지를 떠안는다(2026-08-19).
    base = (total // n // AMOUNT_UNIT) * AMOUNT_UNIT if total >= n * AMOUNT_UNIT else total // n
    shares = [base] * n
    shares[-1] += total - base * n  # 나머지는 마지막 몫이 흡수
    return shares


def _split_amount_weighted(total: int, module_groups: List[Tuple[Optional[str], List[CatalogItem]]]) -> List[int]:
    """모듈 사이 배분을 module_weight(참고 견적서 실제 공급가액) 비율로 나눈다.

    한 모듈이라도 module_weight가 없으면(카탈로그에 아직 실제 참고 데이터를 못 채운 경우)
    전체를 균등분배로 폴백한다 — 일부만 실제 비중, 나머지는 균등으로 섞으면 그 경계가
    자의적이라 오히려 더 이상해진다(2026-08-19).
    """
    n = len(module_groups)
    weights = [items[0].module_weight for _, items in module_groups]
    if any(w is None or w <= 0 for w in weights):
        return _split_amount_evenly(total, n)

    weight_sum = sum(weights)
    shares = [round(total * w / weight_sum / AMOUNT_UNIT) * AMOUNT_UNIT for w in weights]
    shares[max(range(n), key=lambda i: shares[i])] += total - sum(shares)  # 반올림 오차는 최댓값이 흡수
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
        shares = _split_amount_weighted(supply_amount, module_groups)
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
    catalog_by_key = {(i.module_name, i.item_name): i for i in catalog_items}
    line_items = []
    for item in items:
        row = item.model_dump()
        source = catalog_by_key.get((item.category, item.name))
        row["description"] = source.standard_description if source else None
        # 구분(중) — 구분(대)(category=module_name) 아래의 중간 분류. 이 칸이 있는 양식에서만
        # 쓰이고, 카탈로그에 값이 없으면 None이라 그 칸이 비는 것으로 끝난다 (2026-08-19).
        row["mid_category"] = source.mid_category if source else None
        line_items.append(row)

    return {
        "line_items": line_items,
        "supply_amount": supply_amount,
        "vat_amount": vat_amount,
        "grand_total": supply_amount + vat_amount,
    }
