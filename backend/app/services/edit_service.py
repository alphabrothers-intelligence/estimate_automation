"""채팅 기반 수정 (PRD 4.4, 7.3) — 자연어 요청을 받아 기존 항목을 재배분한다."""

import json
import re
from typing import List, Optional

from fastapi import HTTPException
from pydantic import BaseModel, ValidationError

from app.config import CLAUDE_MODEL, get_anthropic, get_supabase
from app.models.estimate import EditResult, EntityQuoteOut
from app.services import pdf_service
from app.services.allocation_service import (
    AMOUNT_UNIT,
    AllocatedItem,
    amount_unit_for,
    extract_json,
    grand_total,
    reconcile_amounts,
    reconcile_snapped_items,
)


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
    "항목을 새로 추가해 달라는 요청이면 items에 새 항목을 넣으세요(category는 기존 항목 중 어느 "
    "구분에 들어갈지 골라서 그대로 쓰고, amount는 0이 아닌 합리적인 금액을 채우세요 — 총액을 "
    "그대로 유지해달라는 말이 없는 한 다른 항목은 건드리지 말고 소계가 늘어나게 두세요, 항목을 "
    "빼면 소계가 줄어드는 것과 대칭입니다). "
    "항목을 빼달라는 요청이면 items에서 그 항목을 제외하세요. "
    "금액 계산은 서버가 정확히 다시 맞추니 직접 계산하려 하지 말고, 사용자가 말한 목표만 옮기세요 — "
    "전체 소계를 특정 금액으로 맞춰달라고 하면(예: \"소계를 1,000만원으로\") 그 정수값을 "
    "supply_total_target에 넣으세요(그런 요청이 없으면 null). "
    "구분(대)별로 소계를 지정하면(예: \"런칭 마케팅은 1000만원, 그로스해킹은 880만원으로\") "
    "group_targets에 [{\"category\": 구분(대) 이름, \"amount\": 정수}] 형태로 전부 넣으세요 "
    "(그런 요청이 없으면 빈 배열). category는 items의 category 값과 정확히 같아야 합니다. "
    "사용자가 말한 목표 금액이 VAT(부가세) 포함 금액이면(예: \"VAT 포함 3000만원으로\") "
    "target_includes_vat를 true로 하세요 — 서버가 1.1로 나눠 공급가액 목표로 바꿉니다. "
    "그냥 금액만 말했으면 false입니다. "
    "rounding_unit은 각 항목 공급가액이 떨어져야 할 단위이고 기본값은 100000(10만원)입니다 — "
    "사용자가 다른 단위를 말하면(예: \"100만원 단위로\") 그 값을, 1원 단위까지 정확한 금액을 "
    "지정했으면(예: \"이 항목을 1,234,567원으로\") 1을 넣으세요. "
    "사용자가 말한 금액은 서버가 그대로 지킵니다 — 10만원 단위에 맞추려고 목표 금액을 임의로 "
    "바꾸지 마세요. 사용자가 금액을 말하지 않은 항목만 서버가 10만원 단위로 떨어뜨립니다. "
    "반드시 JSON 객체 하나만 응답하세요(설명, 마크다운 코드블록 없이). 출력 형식: "
    '{"scope": "quote_only" | "catalog_update" | "ambiguous", '
    '"items": [{"category": "...", "name": "...", "amount": 정수, '
    '"work_days": 숫자 | null, "quantity": 숫자 | null, "unit_price": 숫자 | null}], '
    '"changed_items": [{"category": "...", "name": "...", "amount": 정수, '
    '"work_days": 숫자 | null, "quantity": 숫자 | null, "unit_price": 숫자 | null}], '
    '"changed_items_target": 정수 | null, '
    '"group_targets": [{"category": "...", "amount": 정수}], '
    '"supply_total_target": 정수 | null, "target_includes_vat": true | false, '
    '"rounding_unit": 정수 | null}'
)


class GroupTarget(BaseModel):
    category: str
    amount: int


class EditLLMResult(BaseModel):
    scope: str
    items: List[AllocatedItem]
    changed_items: List[AllocatedItem]
    changed_items_target: Optional[int] = None
    # 사용자가 말한 "공급가액 소계를 N원으로" / "M원 단위로 떨어지게" — 계산은 LLM이 아니라
    # 서버(_apply_amount_constraints)가 한다(2026-08-19).
    supply_total_target: Optional[int] = None
    # 구분(대)별 소계 목표. 전체 소계 하나로는 "런칭은 1000만, 그로스해킹은 880만"처럼 그룹마다
    # 다른 목표를 표현할 수 없어서 추가했다(2026-08-20 — 그 요청이 통째로 무시되던 버그).
    group_targets: List[GroupTarget] = []
    # 위 목표들이 VAT 포함 금액인지. 프롬프트에 VAT 개념이 아예 없어서 "VAT 포함 3000만원"의
    # 3000만이 공급가액 목표로 그대로 들어갔다(2026-08-20 발견).
    target_includes_vat: bool = False
    rounding_unit: Optional[int] = None

    def supply_of(self, amount: int) -> int:
        """사용자가 말한 목표 금액 -> 공급가액 목표."""
        return round(amount / 1.1) if self.target_includes_vat else amount


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


def _floor_nonpositive_amounts(result: EditLLMResult) -> None:
    """새로 추가된 항목에 Claude가 amount 0(또는 음수)을 주는 경우가 있다(2026-08-19 재현,
    "행 추가" 요청이 0원으로 나오는 버그) — reconcile_amounts는 0을 "의도된 삭제"로 보고
    그대로 둔다(allocation_service.py의 `if a > 0 else 0` 참고)라서 여기서 먼저 걸러야 한다.
    가장 큰 항목에서 최소 단위만큼 덜어 채운다(다른 흡수 로직과 같은 "최댓값이 흡수" 패턴)."""
    if len(result.items) < 2:
        return
    for idx, item in enumerate(result.items):
        if item.amount > 0:
            continue
        biggest = max(range(len(result.items)), key=lambda i: result.items[i].amount)
        if biggest == idx:
            continue
        fixed = item.model_copy(update={"amount": AMOUNT_UNIT})
        result.items[idx] = fixed
        result.items[biggest] = result.items[biggest].model_copy(
            update={"amount": result.items[biggest].amount - AMOUNT_UNIT}
        )
        for cidx, citem in enumerate(result.changed_items):
            if (citem.category, citem.name) == (fixed.category, fixed.name):
                result.changed_items[cidx] = fixed
                break


def _group_indexes(result: EditLLMResult) -> dict:
    indexes: dict = {}
    for idx, item in enumerate(result.items):
        indexes.setdefault(item.category, []).append(idx)
    return indexes


def _apply_amount_constraints(result: EditLLMResult) -> None:
    """"소계를 1,000만원으로" / "런칭 마케팅은 1000만원으로" 같은 목표를 서버에서 정확히 맞춘다.

    LLM은 목표(group_targets/supply_total_target)와 단위(rounding_unit)만 뽑고, 실제 배분은
    allocation_service.reconcile_amounts가 한다 — LLM이 직접 계산하면 소계가 목표와 어긋나거나
    152,900원처럼 단위가 안 맞는 값이 그대로 남는 걸 반복해서 확인했다(2026-08-19).

    목표를 하나도 말하지 않았으면 아무것도 하지 않는다. 예전엔 목표가 없어도 현재 소계를
    목표로 삼아 전 항목을 10만원 단위로 다시 반올림하고 그 차액을 가장 큰 항목에 몰아줬는데,
    사용자가 건드리지도 않은 항목의 금액이 채팅 수정 때마다 제멋대로 움직이는 주된 원인이었다
    (2026-08-20 사용자 지적). 격자 맞추기는 목표를 맞추는 과정에서만 한다.

    구분(대)별 목표와 전체 소계 목표가 함께 오면 구분별 목표가 이긴다 — 더 구체적인 지시이고,
    둘이 안 맞으면(사용자가 부른 숫자끼리 모순인 경우) 전체를 맞추느라 구분별 목표가 전부
    깨지는 쪽이 훨씬 나쁘다. 남은 총액 차이는 사용자가 화면에서 보고 다시 고치면 된다.
    """
    if not result.items:
        return
    unit = result.rounding_unit or AMOUNT_UNIT

    if result.group_targets:
        indexes = _group_indexes(result)
        for target in result.group_targets:
            idx = indexes.get(target.category)
            if not idx:
                continue
            amounts = reconcile_amounts(
                [result.items[i].amount for i in idx], result.supply_of(target.amount), unit
            )
            for i, amount in zip(idx, amounts):
                result.items[i] = result.items[i].model_copy(update={"amount": amount})
        return

    if result.supply_total_target is not None:
        amounts = reconcile_amounts(
            [i.amount for i in result.items], result.supply_of(result.supply_total_target), unit
        )
        result.items = [i.model_copy(update={"amount": a}) for i, a in zip(result.items, amounts)]


def _restore_targets(result: EditLLMResult, items: List[dict], unit: int) -> List[dict]:
    """단가 스냅(compute_line_item_pricing) 뒤 목표에서 벌어진 차액을 단가로 되돌린다.

    스냅은 단가를 10만원 배수로 미는 과정이라 소계가 목표에서 조금씩 벗어난다. 최초 생성은
    target_supply를 넘겨 이미 되돌리고 있었는데(pdf_service.compute_line_item_pricing) 채팅
    수정 경로에만 이 마지막 보정이 빠져 있어서 "1000만원으로" 요청이 960만원으로 발급됐다
    (2026-08-20 원인 규명). 격자상 목표에 정확히 못 닿는 목표면(수량 16짜리 항목만 있는 구분은
    한 걸음이 160만원이라 880만원에 닿지 못한다) 가장 가까운 값까지만 가고 그대로 둔다 —
    되묻지 않는다. 사용자가 화면에서 보고 직접 고치는 게 빠르다(2026-08-20 사용자 결정).
    """
    if result.group_targets:
        indexes: dict = {}
        for idx, item in enumerate(items):
            indexes.setdefault(item["category"], []).append(idx)
        items = list(items)
        for target in result.group_targets:
            idx = indexes.get(target.category)
            if not idx:
                continue
            group = reconcile_snapped_items(
                [items[i] for i in idx], result.supply_of(target.amount), unit
            )
            for i, fixed in zip(idx, group):
                items[i] = fixed
        return items

    if result.supply_total_target is not None:
        return reconcile_snapped_items(items, result.supply_of(result.supply_total_target), unit)
    return items


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
    # RuntimeError면 CORS 헤더 없는 500이 되어 브라우저가 사유를 못 읽는다(allocation_service._call_claude 주석 참고).
    raise HTTPException(status_code=502, detail=f"AI 응답을 해석하지 못했습니다: {last_error}")


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
    _floor_nonpositive_amounts(result)
    _reconcile_changed_items_target(result)
    _apply_amount_constraints(result)

    # Claude 응답(AllocatedItem)엔 category/name/amount(+옵션 work_days/quantity/unit_price)뿐이라
    # task_type·description이 빠진다 — 기존 line_items에서 (category, name)으로 다시 찾아 붙인다.
    # 항목명을 Claude가 바꾼 경우(rename) 이름으로는 못 찾으므로, 같은 위치(index)의 기존 항목으로
    # 대체 매칭한다(2026-08-14 — 이름 변경 시 상품구성/과업종류가 유실되는 버그 수정. items 배열은
    # 재배분이지 항목 추가/삭제가 아니므로 순서가 그대로 유지된다는 전제). description을 안 붙이면
    # "상품구성" 컬럼이 있는 양식(알파브라더스 등)에서 채팅 수정할 때마다 그 칸이 비어버린다
    # (2026-08-11 발견).
    old_item_by_key = {(i["category"], i["name"]): i for i in quote["line_items"]}
    old_items = quote["line_items"]
    # 위치(index) 대체 매칭은 "items는 재배분이라 개수·순서가 그대로"라는 전제 위에서만 쓴다 —
    # 채팅으로 항목을 추가·삭제하면 그 전제가 깨져서 뒤쪽 항목들이 통째로 한 칸씩 밀린 채
    # 엉뚱한 상품구성·과업종류를 물려받는다(2026-08-19 항목 추가 지원하며 발견). 개수가 달라진
    # 경우 새 항목의 과업종류는 같은 구분(category)에 있던 기존 항목에서 가져온다.
    same_length = len(result.items) == len(old_items)
    task_type_by_category = {i["category"]: i.get("task_type") for i in old_items}
    mid_category_by_category = {i["category"]: i.get("mid_category") for i in old_items}
    updated_items = []
    for idx, i in enumerate(result.items):
        old_item = old_item_by_key.get((i.category, i.name))
        if old_item is None and same_length and idx < len(old_items):
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

        # 사용자가 이번 턴에 콕 집어 지정한 항목은 잠근다 — 잠긴 항목은 단가 스냅
        # (pdf_service._snapped)·카탈로그 비율 환산(_scale_standard_unit_prices)·잔액 흡수
        # (reconcile_snapped_items)에서 전부 제외되어 말한 값 그대로 남는다(2026-08-20).
        # 이전 턴에 잠긴 항목도 금액이 그대로면 계속 잠긴 채로 둔다 — 그러지 않으면 다음
        # 채팅 수정 때 스냅이 다시 그 단가를 10만원 배수로 밀어버린다. 반대로 이번 목표
        # 때문에 금액이 바뀌었으면(_apply_amount_constraints) 잠금은 풀린다.
        locked = edited or bool(
            (old_item or {}).get("locked") and (old_item or {}).get("amount") == amount
        )

        updated_items.append({
            "category": i.category,
            "name": i.name,
            "amount": amount,
            "locked": locked,
            "work_days": work_days,
            "quantity": quantity,
            "unit_price": unit_price,
            "task_type": (old_item or {}).get("task_type") or task_type_by_category.get(i.category) or task_types[0],
            "description": (old_item or {}).get("description"),
            # 구분(중)도 Claude 응답엔 없으므로 기존 항목에서 되붙인다 — 새로 추가된 항목은
            # 같은 구분(대)에 있던 기존 항목의 값을 물려받는다(2026-08-19).
            "mid_category": (old_item or {}).get("mid_category") or mid_category_by_category.get(i.category),
        })

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
        unit=amount_unit_for(quote["is_primary"]),
    )
    new_line_items = _restore_targets(result, new_line_items, amount_unit_for(quote["is_primary"]))

    # 총액은 compute_line_item_pricing이 단가를 10만원 단위로 스냅한 뒤에 합산해야 한다 —
    # 그 전(updated_items)에서 더하면 화면 합계가 항목 합과 어긋난다(2026-08-20).
    total = grand_total(sum(i["amount"] for i in new_line_items), vat_included)

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
        total_amount=total,
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
