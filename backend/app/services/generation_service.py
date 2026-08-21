"""견적서 항목·금액 생성 (PRD 4.1, 7장) — 2026-08-21 재설계.

흐름이 순차로 바뀌었다: **본견적을 먼저 만들고, 그 결과를 입력으로 비교견적을 리라이팅한다.**
예전에는 본견적과 비교견적을 동시에 각자의 카탈로그로 만든 뒤 총액 비율로 스케일링해서
맞췄는데(sync_service, 폐기), 법인마다 항목 구성이 달라 1:1 대응이 성립하지 않았고 실무자가
"같은 과업인데 항목이 서로 다른 비교견적"을 매번 손으로 고쳐야 했다.

금액을 정하는 곳은 두 곳뿐이다 — AI(여기서 프롬프트로 부름)와 quote_pricing.finalize.
그 외 어떤 코드도 금액을 재계산하지 않는다.
"""

from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional

from fastapi import HTTPException

from app.config import CLAUDE_MAX_TOKENS, CLAUDE_MODEL, get_anthropic, get_supabase
from app.models.estimate import EstimateSetOut
from app.services import module_selection_service, pdf_service, quote_prompts
from app.services.catalog_service import get_catalog_for_generation, get_module_options
from app.services.quote_pricing import FormSpec, assert_storable, finalize, grand_total

DEFAULT_COMPARISON_MARKUP = 0.10  # PRD 4.3 — 비교견적서 기본 마크업 +10%

# 항목 산정은 카탈로그 표준값을 배율로 옮기는 작업이라 깊은 추론이 필요 없다. effort를 낮추면
# 출력 토큰이 절반 이하로 줄고 그만큼 대기시간이 짧아진다 — 품질이 떨어지면 "high"로 올린다.
_EFFORT = "low"

def _call_claude(system: str, user_content: str) -> dict:
    """JSON 하나를 받아온다. 한 번 실패하면 이유를 붙여 다시 묻는다."""
    client = get_anthropic()
    last_error: Optional[Exception] = None
    for _ in range(2):
        message = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=CLAUDE_MAX_TOKENS,
            # 시스템 프롬프트는 견적서마다 그대로라 캐시에 걸린다 — 비교견적 여러 건을 동시에
            # 만들 때 입력 처리 비용이 한 번으로 줄어든다(2026-08-21 속도 개선).
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            output_config={"effort": _EFFORT},
            messages=[{"role": "user", "content": user_content}],
        )
        text = next((b.text for b in message.content if b.type == "text"), "")
        try:
            return quote_prompts.extract_json(text, require_key="items")
        except ValueError as e:  # JSONDecodeError는 ValueError의 하위 클래스
            last_error = e
            user_content += (
                "\n\n[재시도] 이전 응답에서 JSON 객체를 찾지 못했습니다. "
                "설명 없이 JSON 객체 하나만 정확히 출력하세요."
            )
    # RuntimeError로 올리면 Starlette가 CORSMiddleware 바깥에서 500을 만들어 CORS 헤더 없이
    # 응답한다 — 브라우저가 네트워크 오류로 처리해 프론트엔드에 사유가 하나도 안 남는다.
    raise HTTPException(status_code=502, detail=f"AI 응답을 해석하지 못했습니다: {last_error}")


def _save_version(entity_quote_id: str, edit_request_text: str, diff: list) -> None:
    supabase = get_supabase()
    existing = (
        supabase.table("quote_versions")
        .select("version_no")
        .eq("entity_quote_id", entity_quote_id)
        .order("version_no", desc=True)
        .limit(1)
        .execute()
    )
    next_version = (existing.data[0]["version_no"] + 1) if existing.data else 1
    version_res = (
        supabase.table("quote_versions")
        .insert(
            {
                "entity_quote_id": entity_quote_id,
                "version_no": next_version,
                "edit_request_text": edit_request_text,
                "diff": diff,
            }
        )
        .execute()
    )
    supabase.table("entity_quotes").update(
        {"current_version_id": version_res.data[0]["id"]}
    ).eq("id", entity_quote_id).execute()


def _pick_modules(quote: dict, entity_name: str, target_amount: int, vat_included: bool) -> Optional[List[str]]:
    """PM이 직접 고르지 않았으면 대안 구성을 AI가 고른다 (PRD 7장 3~4단계)."""
    picked: List[str] = []
    for task_type in quote["task_types"]:
        has_choices, groups = get_module_options(quote["entity_id"], entity_name, task_type)
        if has_choices:
            picked += module_selection_service.choose_modules(
                entity_name=entity_name,
                task_type=task_type,
                total_amount=target_amount,
                vat_included=vat_included,
                service_name=quote.get("service_name"),
                groups=groups,
            )
    return picked or None


def _load_catalog(quote: dict, entity_name: str, selected_modules: Optional[List[str]]) -> tuple:
    """교차 선택한 과업종류마다 카탈로그를 따로 가져와 하나로 합친다.

    "둘 다 고를 필요는 없다"(위저드 3단계 안내문구)라서 개별 과업종류의 items가 비어 있는 것
    자체는 에러가 아니다. 진짜 에러는 그 법인×과업종류에 카탈로그 행이 아예 없거나(has_catalog),
    선택된 과업종류를 전부 합쳐도 항목이 하나도 없는 경우뿐이다.
    """
    rows: List[dict] = []
    borrowed: List[tuple] = []
    for task_type in quote["task_types"]:
        catalog = get_catalog_for_generation(quote["entity_id"], entity_name, task_type, selected_modules)
        if not catalog.has_catalog:
            raise HTTPException(
                status_code=422,
                detail=f"{entity_name}의 '{task_type}' 카탈로그를 찾을 수 없습니다 (차용 대상도 없음).",
            )
        for item in catalog.items:
            row = item.model_dump()
            row["task_type"] = task_type
            rows.append(row)
        if catalog.is_borrowed:
            borrowed.append((task_type, catalog.source_entity_name))

    if not rows:
        raise HTTPException(
            status_code=422,
            detail=(
                f"{entity_name}의 {'/'.join(quote['task_types'])} 중 선택된 세부 항목이 없습니다 — "
                "최소 한 과업종류에서 항목을 하나 이상 골라주세요."
            ),
        )
    return rows, borrowed


def _store(quote: dict, items: List[dict], vat_included: bool, extra: dict, label: str,
           form: Optional[FormSpec] = None) -> List[dict]:
    # 저장 직전 마지막 관문 — 구조적 위반이 있으면 저장하지 않고 실패시킨다.
    # 조용히 틀린 견적서가 발급되느니 생성이 실패하는 게 낫다(2026-08-21).
    if form is not None:
        assert_storable(items, form, f"{quote['entity_templates']['name']} {label}")
    supply = sum(i["amount"] for i in items)
    get_supabase().table("entity_quotes").update(
        {
            "total_amount": grand_total(supply, vat_included),
            "line_items": items,
            "adjustment_note": label,
            **extra,
        }
    ).eq("id", quote["id"]).execute()
    _save_version(quote["id"], label, items)
    return items


def _generate_primary(quote: dict, estimate_set: dict, selections: Dict[str, List[str]]) -> List[dict]:
    """카탈로그 세부항목을 그대로 쓰고, 작업일·수량·단가만 AI가 산정한다."""
    supabase = get_supabase()
    entity_name = quote["entity_templates"]["name"]
    total = estimate_set["total_amount"]
    vat_included = estimate_set["vat_included"]
    target_supply = round(total / 1.1) if vat_included else total

    selected_modules = selections.get(quote["id"]) or _pick_modules(
        quote, entity_name, total, vat_included
    )
    catalog_rows, borrowed = _load_catalog(quote, entity_name, selected_modules)
    form = pdf_service.resolve_form_spec(supabase, quote["entity_id"], quote["task_types"], selected_modules)

    result = _call_claude(
        quote_prompts.PRIMARY_SYSTEM,
        quote_prompts.build_primary_user(
            entity_name, "/".join(quote["task_types"]), form, catalog_rows, target_supply
        ),
    )
    items = _merge_with_catalog(result.get("items") or [], catalog_rows, form)
    items, residual, log = finalize(items, target_supply, form)

    return _store(
        quote,
        items,
        vat_included,
        {
            "is_catalog_borrowed": bool(borrowed),
            "catalog_source_entity_name": borrowed[0][1] if borrowed else None,
            "selected_modules": selected_modules,
            "markup_ratio": None,
        },
        _label("본견적 생성", residual, log),
        form,
    )


def _merge_with_catalog(ai_items: List[dict], catalog_rows: List[dict], form: FormSpec) -> List[dict]:
    """AI 응답에 카탈로그 원본 정보(과업종류·구분(중)·상품구성)를 되붙인다.

    AI는 항목을 같은 순서로 그대로 돌려주도록 되어 있지만(프롬프트 1번 규칙), 어겼을 때
    조용히 어긋나면 안 되므로 개수가 다르면 카탈로그 순서를 기준으로 잘라 맞춘다. 이름은
    AI가 준 걸 쓰되, 값이 빠진 칸은 카탈로그 표준값으로 메운다.
    """
    # AI는 카탈로그 번호(i, 1-based)로 답한다 — 순서가 어긋나거나 일부가 빠져도 제자리에 꽂힌다.
    by_index = {int(a["i"]) - 1: a for a in ai_items if isinstance(a.get("i"), (int, float))}
    merged = []
    for i, row in enumerate(catalog_rows):
        ai = by_index.get(i) or (ai_items[i] if i < len(ai_items) else {})
        merged.append(
            {
                # 항목명·구분은 카탈로그가 정답이다(AI에게 다시 적게 하지 않는다).
                "category": row.get("module_name") or "",
                "name": row["item_name"],
                "work_days": ai.get("work_days") if ai.get("work_days") is not None else row["work_days"],
                "quantity": ai.get("quantity") if ai.get("quantity") is not None else row["quantity"],
                "unit_price": ai.get("unit_price") or row.get("unit_price") or 0,
                "amount": 0,  # finalize가 양식 수식으로 채운다
                "task_type": row["task_type"],
                "mid_category": row.get("mid_category"),
                "description": row.get("standard_description"),
            }
        )
    return merged


def _generate_comparison(
    quote: dict, primary_entity: str, primary_items: List[dict], primary_supply: int, vat_included: bool
) -> List[dict]:
    """확정된 본견적을 입력으로 같은 과업을 다른 업체 어투로 다시 쓴다."""
    supabase = get_supabase()
    entity_name = quote["entity_templates"]["name"]
    markup = float(quote.get("markup_ratio") or (1 + DEFAULT_COMPARISON_MARKUP)) - 1
    selected_modules = quote.get("selected_modules")
    form = pdf_service.resolve_form_spec(supabase, quote["entity_id"], quote["task_types"], selected_modules)

    result = _call_claude(
        quote_prompts.COMPARISON_SYSTEM,
        quote_prompts.build_comparison_user(
            entity_name,
            "/".join(quote["task_types"]),
            form,
            primary_entity,
            primary_items,
            primary_supply,
            markup,
        ),
    )
    ai_items = result.get("items") or []
    by_index = {int(a["i"]) - 1: a for a in ai_items if isinstance(a.get("i"), (int, float))}
    items = []
    for i, src in enumerate(primary_items):
        ai = by_index.get(i) or (ai_items[i] if i < len(ai_items) else {})
        items.append(
            {
                # 구분·항목명·상세는 AI가 다시 쓴 것을 쓴다. 이게 비교견적의 존재 이유다.
                "category": ai.get("category") or src.get("category") or "",
                "name": ai.get("name") or src["name"],
                "description": ai.get("description") or src.get("description"),
                "work_days": ai.get("work_days") if ai.get("work_days") is not None else src.get("work_days"),
                "quantity": ai.get("quantity") if ai.get("quantity") is not None else src.get("quantity"),
                "unit_price": ai.get("unit_price") or src.get("unit_price") or 0,
                "amount": 0,
                # 과업종류·구분(중)은 발급 시 어느 카탈로그·어느 칸을 쓸지 정하는 값이라
                # 본견적 대응 항목에서 그대로 물려받는다.
                "task_type": src.get("task_type"),
                "mid_category": src.get("mid_category"),
            }
        )
    target_supply = round(primary_supply * (1 + markup))
    items, residual, log = finalize(items, target_supply, form)

    return _store(
        quote,
        items,
        vat_included,
        {"markup_ratio": round(1 + markup, 4), "selected_modules": selected_modules},
        _label(f"비교견적 생성 (마크업 +{round(markup * 100)}%)", residual, log),
        form,
    )


def _label(prefix: str, residual: int, log: List[str]) -> str:
    """버전 이력에 남길 한 줄. 후처리가 무엇을 움직였는지 여기서 추적된다."""
    parts = [prefix]
    if residual:
        parts.append(f"잔액 {residual:+,}원")
    if log:
        parts.append(" / ".join(log))
    return " — ".join(parts)


def generate_estimate_set(
    estimate_set_id: str, selections: Optional[Dict[str, List[str]]] = None
) -> EstimateSetOut:
    supabase = get_supabase()
    selections = selections or {}

    set_res = supabase.table("estimate_sets").select("*").eq("id", estimate_set_id).execute()
    if not set_res.data:
        raise HTTPException(status_code=404, detail="견적 세트를 찾을 수 없습니다.")
    estimate_set = set_res.data[0]
    vat_included = estimate_set["vat_included"]

    quotes = (
        supabase.table("entity_quotes")
        .select(
            "id, entity_id, is_primary, task_type, task_types, service_name, markup_ratio, "
            "selected_modules, entity_templates(name)"
        )
        .eq("estimate_set_id", estimate_set_id)
        .execute()
    ).data

    primary = next((q for q in quotes if q["is_primary"]), None)
    comparisons = [q for q in quotes if not q["is_primary"]]

    if primary:
        # 본견적만 만든다. 비교견적은 사용자가 본견적을 검토·확정한 뒤 regenerate_comparisons로
        # 따로 만든다(2026-08-21 순차 흐름) — 확정 전 본견적으로 비교견적을 써봐야 곧 버려진다.
        _generate_primary(primary, estimate_set, selections)
        from app.services.estimate_service import get_estimate_set  # 순환 참조 회피

        return get_estimate_set(estimate_set_id)
    else:
        # 본견적 없이 비교견적만 발행하는 세트(2026-08-10 사용자 결정) — 리라이팅의 원본이
        # 없으므로 각 비교견적을 자기 카탈로그로 본견적처럼 만든다.
        with ThreadPoolExecutor(max_workers=max(1, len(comparisons))) as pool:
            list(pool.map(lambda q: _generate_primary(q, estimate_set, selections), comparisons))
        from app.services.estimate_service import get_estimate_set  # 순환 참조 회피

        return get_estimate_set(estimate_set_id)

    # 비교견적끼리는 서로 독립적이라 동시에 만든다.
    if comparisons:
        with ThreadPoolExecutor(max_workers=len(comparisons)) as pool:
            futures = [
                pool.submit(
                    _generate_comparison, q, primary_entity, primary_items, primary_supply, vat_included
                )
                for q in comparisons
            ]
            for future in futures:
                future.result()

    from app.services.estimate_service import get_estimate_set  # 순환 참조 회피

    return get_estimate_set(estimate_set_id)


def regenerate_comparisons(estimate_set_id: str) -> EstimateSetOut:
    """확정된 본견적을 기준으로 비교견적만 다시 만든다.

    본견적을 고친 뒤 비교견적을 맞추는 유일한 방법이다 — 예전처럼 본견적 저장이 비교견적을
    자동으로 비례 스케일링하지 않는다(sync_service 폐기, 2026-08-21). 사용자가 명시적으로
    누를 때만 비교견적이 바뀐다.
    """
    supabase = get_supabase()
    estimate_set = (
        supabase.table("estimate_sets").select("*").eq("id", estimate_set_id).execute()
    ).data
    if not estimate_set:
        raise HTTPException(status_code=404, detail="견적 세트를 찾을 수 없습니다.")

    quotes = (
        supabase.table("entity_quotes")
        .select(
            "id, entity_id, is_primary, task_type, task_types, service_name, markup_ratio, "
            "selected_modules, line_items, entity_templates(name)"
        )
        .eq("estimate_set_id", estimate_set_id)
        .execute()
    ).data
    primary = next((q for q in quotes if q["is_primary"]), None)
    if not primary or not primary.get("line_items"):
        raise HTTPException(status_code=422, detail="기준이 될 본견적이 아직 생성되지 않았습니다.")

    comparisons = [q for q in quotes if not q["is_primary"]]
    primary_supply = sum(i["amount"] for i in primary["line_items"])
    if comparisons:
        with ThreadPoolExecutor(max_workers=len(comparisons)) as pool:
            futures = [
                pool.submit(
                    _generate_comparison,
                    q,
                    primary["entity_templates"]["name"],
                    primary["line_items"],
                    primary_supply,
                    estimate_set[0]["vat_included"],
                )
                for q in comparisons
            ]
            for future in futures:
                future.result()

    from app.services.estimate_service import get_estimate_set  # 순환 참조 회피

    return get_estimate_set(estimate_set_id)


def rescale_comparisons(estimate_set_id: str, primary_supply: int, vat_included: bool) -> dict:
    """본견적 금액이 바뀌었을 때 비교견적 금액만 AI 없이 다시 맞춘다.

    항목명·작업일·수량은 손대지 않고 단가에만 같은 배율을 곱한 뒤 finalize로 목표에 맞춘다 —
    실무자가 본견적 총액을 조정하는 게 가장 흔한 수정이고, 그때 비교견적 문장은 이미 맞아서
    다시 쓸 이유가 없다. 0원·즉시라서 저장할 때마다 자동으로 돌려도 부담이 없다.

    겉모습은 폐기된 sync_service._scale_items_to_supply와 비슷하지만 속이 다르다. 예전엔
    스냅·잔액흡수가 6겹으로 얽혀 손대지 않은 항목까지 매번 흔들렸고, 지금은 finalize가
    최대 2개 항목만 움직이며 무엇이 얼마나 움직였는지 전부 문장으로 남는다.

    항목 수가 본견적과 달라진 비교견적(사용자가 본견적 항목을 추가·삭제함)은 1:1 대응이
    깨져서 금액만으로는 못 맞춘다 — 건드리지 않고 id만 돌려주어 화면이 재생성을 안내한다.
    """
    supabase = get_supabase()
    comparisons = (
        supabase.table("entity_quotes")
        .select("id, entity_id, task_types, line_items, markup_ratio, selected_modules")
        .eq("estimate_set_id", estimate_set_id)
        .eq("is_primary", False)
        .execute()
    ).data

    rescaled, needs_regeneration = [], []
    for quote in comparisons:
        items = quote.get("line_items") or []
        ratio = float(quote.get("markup_ratio") or 0)
        if not items or ratio <= 0:
            continue
        if len(items) != _primary_item_count(supabase, estimate_set_id):
            needs_regeneration.append(quote["id"])
            continue

        form = pdf_service.resolve_form_spec(
            supabase, quote["entity_id"], quote["task_types"], quote.get("selected_modules")
        )
        target = round(primary_supply * ratio)
        current = sum(i["amount"] for i in items) or 1
        factor = target / current
        scaled = [dict(i, unit_price=(i.get("unit_price") or 0) * factor) for i in items]
        scaled, residual, log = finalize(scaled, target, form)

        assert_storable(scaled, form, "비교견적 금액 자동 반영")
        note = _label("본견적 금액 변경 자동 반영", residual, log)
        supabase.table("entity_quotes").update(
            {
                "total_amount": grand_total(sum(i["amount"] for i in scaled), vat_included),
                "line_items": scaled,
                "adjustment_note": note,
            }
        ).eq("id", quote["id"]).execute()
        _save_version(quote["id"], note, scaled)
        rescaled.append(quote["id"])

    return {"rescaled": rescaled, "needs_regeneration": needs_regeneration}


def _primary_item_count(supabase, estimate_set_id: str) -> int:
    rows = (
        supabase.table("entity_quotes")
        .select("line_items")
        .eq("estimate_set_id", estimate_set_id)
        .eq("is_primary", True)
        .execute()
    ).data
    return len(rows[0].get("line_items") or []) if rows else 0
