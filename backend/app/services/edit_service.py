"""채팅 기반 수정 (PRD 4.4, 7.3) — 자연어 요청을 받아 기존 항목을 재배분한다."""

import json
import re
from typing import List, Optional

from fastapi import HTTPException
from pydantic import BaseModel, ValidationError

from app.config import CLAUDE_MODEL, get_anthropic, get_supabase
from app.models.estimate import EditResult, EntityQuoteOut
from app.services import pdf_service
from app.services.allocation_service import AllocatedItem, extract_json


def reconcile_amount(
    work_days: Optional[float],
    quantity: Optional[float],
    unit_price: Optional[float],
    amount: float,
    edited: bool,
) -> tuple:
    """공급가액은 항상 단가×수량이고 작업일은 가격에 영향 없는 정보성 필드다(2026-08-14 결정).
    edited=True(단가/작업일/수량 중 하나라도 사용자가 고침)면 amount를 단가×수량으로 재계산하고,
    아니면 quantity만으로 unit_price를 역산한다(둘 다 아니면 원래 amount/unit_price를 그대로 둔다)."""
    if edited:
        if quantity is not None and unit_price is not None:
            amount = round(unit_price * quantity)
    elif quantity is not None:
        unit_price = amount / quantity if quantity else amount
    return amount, unit_price

SYSTEM_PROMPT = (
    "아래는 기존 견적 항목이며, 사용자의 수정 요청을 반영해 재배분하세요. "
    "제약조건(예: 총액 유지)이 있으면 반드시 지켜야 합니다. "
    "먼저 이 요청이 '이번 견적 건만' 수정하려는 것인지, '앞으로도 계속 적용될 기본값(카탈로그)'을 "
    "바꾸려는 것인지 판별하고 scope 필드로 명시하세요. 판별이 애매하면 scope를 \"ambiguous\"로 "
    "표시하세요. 수정 요청에 changed_items의 합계가 맞아야 할 구체적인 금액이 명시돼 있으면(예: "
    "\"광고형 마케팅은 900만원으로 해줘\") 그 정수값을 changed_items_target에 넣으세요(없으면 null). "
    "항목마다 work_days(작업일)/quantity(수량)/unit_price(단가) 필드도 넣을 수 있습니다 — 사용자가 "
    "그 항목의 작업일·수량·단가를 명시적으로 지정하거나 바꿔달라고 한 경우에만 그 필드를 채우고, "
    "언급하지 않은 항목·필드는 반드시 null로 두세요(임의로 값을 지어내면 안 됩니다). "
    "이 세 필드 중 하나라도 채우면 amount는 무시되고 단가×작업일×수량으로 다시 계산되니, amount는 "
    "평소처럼(총액 배분 결과) 채우면 됩니다. "
    "반드시 JSON 객체 하나만 응답하세요(설명, 마크다운 코드블록 없이). 출력 형식: "
    '{"scope": "quote_only" | "catalog_update" | "ambiguous", '
    '"items": [{"category": "...", "name": "...", "amount": 정수, '
    '"work_days": 숫자 | null, "quantity": 숫자 | null, "unit_price": 숫자 | null}], '
    '"changed_items": [{"category": "...", "name": "...", "amount": 정수, '
    '"work_days": 숫자 | null, "quantity": 숫자 | null, "unit_price": 숫자 | null}], '
    '"changed_items_target": 정수 | null}'
)


class EditLLMResult(BaseModel):
    scope: str
    items: List[AllocatedItem]
    changed_items: List[AllocatedItem]
    changed_items_target: Optional[int] = None


def _reconcile_changed_items_target(result: EditLLMResult) -> None:
    """Claude가 준 changed_items 합이 사용자가 명시한 목표 금액과 다르면 마지막 항목에서
    차액을 흡수한다(allocation_service._reconcile_rounding과 같은 패턴, PRD 7.1-6) — LLM이
    비율 계산을 하다 목표에 못 미치는 경우가 있어(2026-08-10 확인) 서버에서 정확히 맞춘다."""
    if result.changed_items_target is None or not result.changed_items:
        return
    diff = result.changed_items_target - sum(i.amount for i in result.changed_items)
    if diff == 0:
        return
    last = result.changed_items[-1]
    fixed = last.model_copy(update={"amount": last.amount + diff})
    result.changed_items[-1] = fixed
    for idx, item in enumerate(result.items):
        if (item.category, item.name) == (last.category, last.name):
            result.items[idx] = fixed
            break


def _call_claude_edit(existing_items: list, edit_request_text: str) -> EditLLMResult:
    client = get_anthropic()
    user_content = (
        f"[기존 항목]\n{json.dumps(existing_items, ensure_ascii=False)}\n\n"
        f"[수정 요청]\n\"{edit_request_text}\""
    )
    last_error = None
    for _ in range(2):
        message = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        text = next((b.text for b in message.content if b.type == "text"), "")
        try:
            data = extract_json(text)
            return EditLLMResult.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as e:
            last_error = e
            user_content += "\n\n[재시도] 이전 응답이 올바른 JSON이 아니었습니다. JSON 객체 하나만 정확히 출력하세요."
    raise RuntimeError(f"Claude 응답을 JSON으로 파싱하지 못했습니다: {last_error}")


def edit_entity_quote(entity_quote_id: str, edit_request_text: str) -> EditResult:
    supabase = get_supabase()

    quote_res = (
        supabase.table("entity_quotes")
        .select(
            "id, entity_id, is_primary, task_type, task_types, line_items, estimate_set_id, selected_modules, "
            "is_catalog_borrowed, catalog_source_entity_name, service_name, quote_date, "
            "recipient_name, recipient_contact, recipient_phone, recipient_email, entity_templates(name)"
        )
        .eq("id", entity_quote_id)
        .execute()
    )
    if not quote_res.data:
        raise HTTPException(status_code=404, detail="견적서를 찾을 수 없습니다.")
    quote = quote_res.data[0]
    task_types = quote["task_types"]

    set_res = (
        supabase.table("estimate_sets").select("vat_included").eq("id", quote["estimate_set_id"]).execute()
    )
    vat_included = set_res.data[0]["vat_included"]

    result = _call_claude_edit(quote["line_items"], edit_request_text)
    _reconcile_changed_items_target(result)

    # Claude 응답(AllocatedItem)엔 category/name/amount(+옵션 work_days/quantity/unit_price)뿐이라
    # task_type·description이 빠진다 — 기존 line_items에서 (category, name)으로 다시 찾아 붙인다.
    # 항목명을 Claude가 바꾼 경우(rename) 이름으로는 못 찾으므로, 같은 위치(index)의 기존 항목으로
    # 대체 매칭한다(2026-08-14 — 이름 변경 시 상품구성/과업종류가 유실되는 버그 수정. items 배열은
    # 재배분이지 항목 추가/삭제가 아니므로 순서가 그대로 유지된다는 전제). description을 안 붙이면
    # "상품구성" 컬럼이 있는 양식(알파브라더스 등)에서 채팅 수정할 때마다 그 칸이 비어버린다
    # (2026-08-11 발견).
    old_item_by_key = {(i["category"], i["name"]): i for i in quote["line_items"]}
    old_items = quote["line_items"]
    updated_items = []
    for idx, i in enumerate(result.items):
        old_item = old_item_by_key.get((i.category, i.name))
        if old_item is None and idx < len(old_items):
            old_item = old_items[idx]

        # 프론트엔드 직접편집(estimate-wizard.tsx handleEditItem)과 같은 규칙 — 공급가액은 항상
        # 단가×수량이고 작업일은 가격에 영향 없는 정보성 필드다(2026-08-14 사용자 결정 — 원본
        # xlsx 중 일부 시트엔 단가×작업일×수량 수식이 박혀있지만, 그건 pdf_service가 발급 시점에
        # 역산으로 흡수하는 별개 문제다. 여기(화면/채팅 편집)의 amount는 항상 단가×수량이어야 한다).
        work_days = i.work_days if i.work_days is not None else (old_item or {}).get("work_days")
        quantity = i.quantity if i.quantity is not None else (old_item or {}).get("quantity")
        unit_price = i.unit_price if i.unit_price is not None else (old_item or {}).get("unit_price")
        edited = i.work_days is not None or i.quantity is not None or i.unit_price is not None
        amount, unit_price = reconcile_amount(work_days, quantity, unit_price, i.amount, edited)

        updated_items.append({
            "category": i.category,
            "name": i.name,
            "amount": amount,
            "work_days": work_days,
            "quantity": quantity,
            "unit_price": unit_price,
            "task_type": (old_item or {}).get("task_type") or task_types[0],
            "description": (old_item or {}).get("description"),
        })

    supply_amount = sum(i["amount"] for i in updated_items)
    if vat_included:
        grand_total = round(supply_amount * 1.1)
    else:
        grand_total = supply_amount + round(supply_amount * 0.1)

    entity_name = quote["entity_templates"]["name"]
    # 채팅 수정 후에도 미리보기에서 단가/작업일/수량이 계속 보이도록, 생성 때와 같은 로직으로
    # 다시 계산해 저장한다(2026-07-10) — 그렇지 않으면 수정할 때마다 이 컬럼들이 빈 값("—")으로
    # 바뀌어 버린다.
    catalog_entity_id_by_task_type = {
        task_type: pdf_service.resolve_catalog_entity_id(supabase, quote["entity_id"], entity_name, task_type)
        for task_type in task_types
    }

    new_line_items = pdf_service.compute_line_item_pricing(
        supabase,
        quote["entity_id"],
        task_types,
        quote.get("selected_modules"),
        catalog_entity_id_by_task_type,
        updated_items,
    )

    # changed_items(변경 요약, 채팅창에 그대로 표시됨)의 amount는 work_days/quantity/unit_price
    # 재계산 전 Claude 원본값이라 최종 amount와 다를 수 있다 — new_line_items(재계산 완료)에서
    # 같은 항목을 다시 찾아 최종 금액으로 맞춘다(2026-08-14).
    new_item_by_key = {(i["category"], i["name"]): i for i in new_line_items}
    diff = [
        new_item_by_key.get((i.category, i.name), i.model_dump())
        for i in result.changed_items
    ]

    # 미리보기 전용 — DB에는 아무것도 쓰지 않는다(2026-08-14). 사용자가 화면에서 확인 후
    # "수정 반영하기"를 눌러야 estimate_service.update_line_items로 실제 저장·버전기록·비교견적
    # 동기화가 일어난다 — 직접편집과 완전히 같은 커밋 경로를 공유해 채팅 수정도 되돌리기/
    # 원본복원 대상이 되게 한다.
    entity_quote_out = EntityQuoteOut(
        id=quote["id"],
        entity_id=quote["entity_id"],
        entity_name=entity_name,
        is_primary=quote["is_primary"],
        task_type=quote["task_type"],
        task_types=task_types,
        total_amount=grand_total,
        line_items=new_line_items,
        is_catalog_borrowed=quote["is_catalog_borrowed"],
        catalog_source_entity_name=quote["catalog_source_entity_name"],
        service_name=quote["service_name"],
        quote_date=quote["quote_date"],
        recipient_name=quote["recipient_name"],
        recipient_contact=quote["recipient_contact"],
        recipient_phone=quote["recipient_phone"],
        recipient_email=quote["recipient_email"],
        **pdf_service.get_column_display(
            supabase, quote["entity_id"], task_types, quote.get("selected_modules")
        ),
    )

    return EditResult(scope=result.scope, entity_quote=entity_quote_out, changed_items=diff)
