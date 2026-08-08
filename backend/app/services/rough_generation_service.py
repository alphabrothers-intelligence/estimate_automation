"""비교견적서만 러프하게 발행하는 경우(본견적서 없음)의 항목 생성 (2026-07-10 사용자 결정).

정식 카탈로그를 참조해 상세 항목을 만드는 기존 배분 로직과 달리, 이 경로는 용역명·총액만
가지고 Claude가 간단한 항목 3~5개를 자유롭게 구성한다. "비교견적서만 선택하고 비교견적서만
발행"하는 경우는 증빙 자료로 빠르게 보내야 하는 상황이라, 테스티파이/알파브라더스처럼 항목을
세세하게 쪼개는 정식 카탈로그 스타일을 강제하면 안 된다는 실제 참고 자료(우유곳간 마케팅
견적서_260709 — 전략 기획/광고 운영/결과 보고 3개 항목)를 바탕으로 만들었다.
"""

from typing import Optional

from pydantic import BaseModel, ValidationError

from app.config import CLAUDE_MODEL, get_anthropic
from app.services.allocation_service import extract_json

SYSTEM_PROMPT = (
    "당신은 견적서 항목 생성 담당자입니다. 이 견적서는 정식 카탈로그 없이 빠르게 발행하는 "
    "러프한 비교견적서이므로, 실제 업무를 지나치게 세분화하지 말고 일반적인 업무 단계 "
    "(예: 기획/실행/운영/결과보고 수준) 3~5개로 간단하게 구성하세요. 용역명에 어울리는 "
    "자연스러운 항목명을 자유롭게 만들되, 실제 업무 성격에 맞아야 합니다. 반드시 JSON 객체 "
    "하나만 응답하고(설명, 마크다운 코드블록 없이), 배분된 금액(amount)의 합은 입력된 "
    '공급가액과 정확히 일치해야 합니다. 출력 형식: {"items": [{"name": "항목명", "amount": 정수}]}'
)


class RoughItem(BaseModel):
    name: str
    amount: int


class RoughAllocationResult(BaseModel):
    items: list[RoughItem]


def _call_claude(user_content: str) -> RoughAllocationResult:
    client = get_anthropic()
    last_error: Optional[Exception] = None

    for attempt in range(2):
        message = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        text = next((b.text for b in message.content if b.type == "text"), "")
        try:
            data = extract_json(text)
            return RoughAllocationResult.model_validate(data)
        except (ValueError, ValidationError) as e:
            last_error = e
            user_content = (
                user_content
                + "\n\n[재시도] 이전 응답이 올바른 JSON이 아니었습니다. "
                + "설명 없이 JSON 객체 하나만 정확히 출력하세요."
            )

    raise RuntimeError(f"Claude 응답을 JSON으로 파싱하지 못했습니다: {last_error}")


def _reconcile_rounding(items: list[RoughItem], target_supply_amount: int) -> list[RoughItem]:
    total = sum(i.amount for i in items)
    diff = target_supply_amount - total
    if diff != 0 and items:
        items[-1] = RoughItem(name=items[-1].name, amount=items[-1].amount + diff)
    return items


def generate_rough_items(
    entity_name: str,
    task_type: str,
    service_name: Optional[str],
    total_amount: int,
    vat_included: bool,
) -> dict:
    if vat_included:
        supply_amount = round(total_amount / 1.1)
        vat_amount = total_amount - supply_amount
    else:
        supply_amount = total_amount
        vat_amount = round(supply_amount * 0.1)

    user_content = (
        f"[법인] {entity_name}\n[과업종류] {task_type}\n"
        f"[용역명] {service_name or task_type}\n"
        f"[공급가액(VAT 제외)] {supply_amount}원"
    )
    result = _call_claude(user_content)
    items = _reconcile_rounding(result.items, supply_amount)

    # 하나의 용역이라 항목들을 한 카테고리로 묶어 미리보기/PDF에서 한 그룹으로 보이게 한다
    # (참고 자료의 "용역명: 카카오 톡스토어 광고 대행" 아래 3개 항목이 한 블록으로 묶인 형태).
    category = service_name or task_type
    line_items = [{"name": i.name, "amount": i.amount, "category": category} for i in items]

    return {
        "line_items": line_items,
        "supply_amount": supply_amount,
        "vat_amount": vat_amount,
        "grand_total": supply_amount + vat_amount,
    }