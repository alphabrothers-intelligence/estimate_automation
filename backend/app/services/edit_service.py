"""채팅 기반 수정 (PRD 4.4, 7.3) — 자연어 요청을 받아 기존 항목을 재배분한다."""

import json
import re
from typing import List

from fastapi import HTTPException
from pydantic import BaseModel, ValidationError

from app.config import CLAUDE_MODEL, get_anthropic, get_supabase
from app.models.estimate import EditResult, EntityQuoteOut
from app.services import pdf_service
from app.services.allocation_service import AllocatedItem, extract_json
from app.services.generation_service import _save_version

SYSTEM_PROMPT = (
    "아래는 기존 견적 항목이며, 사용자의 수정 요청을 반영해 재배분하세요. "
    "제약조건(예: 총액 유지)이 있으면 반드시 지켜야 합니다. "
    "먼저 이 요청이 '이번 견적 건만' 수정하려는 것인지, '앞으로도 계속 적용될 기본값(카탈로그)'을 "
    "바꾸려는 것인지 판별하고 scope 필드로 명시하세요. 판별이 애매하면 scope를 \"ambiguous\"로 "
    "표시하세요. 반드시 JSON 객체 하나만 응답하세요(설명, 마크다운 코드블록 없이). 출력 형식: "
    '{"scope": "quote_only" | "catalog_update" | "ambiguous", '
    '"items": [{"category": "...", "name": "...", "amount": 정수}], '
    '"changed_items": [{"category": "...", "name": "...", "amount": 정수}]}'
)


class EditLLMResult(BaseModel):
    scope: str
    items: List[AllocatedItem]
    changed_items: List[AllocatedItem]


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
            "id, entity_id, is_primary, task_type, line_items, estimate_set_id, selected_modules, "
            "is_catalog_borrowed, catalog_source_entity_name, service_name, entity_templates(name)"
        )
        .eq("id", entity_quote_id)
        .execute()
    )
    if not quote_res.data:
        raise HTTPException(status_code=404, detail="견적서를 찾을 수 없습니다.")
    quote = quote_res.data[0]

    set_res = (
        supabase.table("estimate_sets").select("vat_included").eq("id", quote["estimate_set_id"]).execute()
    )
    vat_included = set_res.data[0]["vat_included"]

    result = _call_claude_edit(quote["line_items"], edit_request_text)

    supply_amount = sum(i.amount for i in result.items)
    if vat_included:
        grand_total = round(supply_amount * 1.1)
    else:
        grand_total = supply_amount + round(supply_amount * 0.1)

    # 채팅 수정 후에도 미리보기에서 단가/작업일/수량이 계속 보이도록, 생성 때와 같은 로직으로
    # 다시 계산해 저장한다(2026-07-10) — 그렇지 않으면 수정할 때마다 이 컬럼들이 빈 값("—")으로
    # 바뀌어 버린다.
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

    new_line_items = pdf_service.compute_line_item_pricing(
        supabase,
        quote["entity_id"],
        quote["task_type"],
        quote.get("selected_modules"),
        catalog_entity_id,
        [i.model_dump() for i in result.items],
    )
    supabase.table("entity_quotes").update(
        {"total_amount": grand_total, "line_items": new_line_items}
    ).eq("id", entity_quote_id).execute()

    diff = [i.model_dump() for i in result.changed_items]
    _save_version(entity_quote_id, edit_request_text, diff)

    entity_quote_out = EntityQuoteOut(
        id=quote["id"],
        entity_id=quote["entity_id"],
        entity_name=quote["entity_templates"]["name"],
        is_primary=quote["is_primary"],
        task_type=quote["task_type"],
        total_amount=grand_total,
        line_items=new_line_items,
        is_catalog_borrowed=quote["is_catalog_borrowed"],
        catalog_source_entity_name=quote["catalog_source_entity_name"],
        service_name=quote["service_name"],
        **pdf_service.get_column_display(
            supabase, quote["entity_id"], quote["task_type"], quote.get("selected_modules")
        ),
    )

    return EditResult(scope=result.scope, entity_quote=entity_quote_out, changed_items=diff)
