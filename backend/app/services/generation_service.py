"""Phase 4 — 견적 세트의 각 법인별 견적서에 항목을 자동생성한다 (PRD 4.1, 7장)."""

from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional

from fastapi import HTTPException

from app.config import get_supabase
from app.models.estimate import EntityQuoteOut, EstimateSetOut
from app.services import module_selection_service, pdf_service
from app.services.allocation_service import allocate_items
from app.services.catalog_service import get_catalog_for_generation, get_module_options

COMPARISON_MARKUP = 0.10  # PRD 4.3 — 비교견적서 기본 마크업 +10% (팀장 피드백 시 +15%까지, PM override 가능)


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


def _generate_one_quote(quote: dict, estimate_set: dict, selections: Dict[str, List[str]]) -> None:
    supabase = get_supabase()
    entity_name = quote["entity_templates"]["name"]
    task_types = quote["task_types"]
    target_amount = round(
        estimate_set["total_amount"] if quote["is_primary"] else estimate_set["total_amount"] * (1 + COMPARISON_MARKUP)
    )

    # 2026-08-10 사용자 결정: 본견적서 없이 비교견적서만 발행하는 세트도 정식 카탈로그 세부항목을
    # 그대로 써야 한다 — 이전엔 이 경우 Claude가 자유 항목 3~5개를 구성하는 별도 경로(rough
    # generation)를 탔지만, "선택한 과업종류의 세부항목이 그대로 들어가야 한다"는 요청으로 폐기.
    selected_modules = selections.get(quote["id"]) or None
    if selected_modules is None:
        # PM이 직접 고르지 않은 경우(MVP 기본 흐름) — 대안 구성이 있으면 용역명/총액/과업종류를
        # 참고해 Claude가 대신 고른다 (PRD 7장 3~4단계를 LLM 자동 판단으로 대체). 과업종류를
        # 교차 선택한 견적서는 각 과업종류마다 독립적으로 고른 뒤 합친다(모듈명이 과업종류
        # 간에 겹치지 않아 그대로 이어붙여도 안전하다).
        picked: List[str] = []
        for task_type in task_types:
            has_choices, groups = get_module_options(quote["entity_id"], entity_name, task_type)
            if has_choices:
                picked += module_selection_service.choose_modules(
                    entity_name=entity_name,
                    task_type=task_type,
                    total_amount=target_amount,
                    vat_included=estimate_set["vat_included"],
                    service_name=quote.get("service_name"),
                    groups=groups,
                )
        selected_modules = picked or None

    # 교차 선택한 과업종류마다 카탈로그를 따로 가져와 하나로 합친다 — (module_name, item_name)
    # 조합으로 어느 과업종류 항목인지 기억해 둔다(allocate_items 결과에 나중에 다시 붙이려고,
    # allocation_service.py의 description 재부착 방식과 동일한 패턴).
    catalog_items = []
    task_type_by_key: Dict[tuple, str] = {}
    borrowed: List[tuple] = []
    for task_type in task_types:
        catalog = get_catalog_for_generation(quote["entity_id"], entity_name, task_type, selected_modules)
        if not catalog.items:
            raise HTTPException(
                status_code=422,
                detail=f"{entity_name}의 '{task_type}' 카탈로그를 찾을 수 없습니다 (차용 대상도 없음).",
            )
        for item in catalog.items:
            task_type_by_key[(item.module_name, item.item_name)] = task_type
        catalog_items += catalog.items
        if catalog.is_borrowed:
            borrowed.append((task_type, catalog.source_entity_name))

    allocation = allocate_items(catalog_items, target_amount, estimate_set["vat_included"])
    is_catalog_borrowed = bool(borrowed)
    catalog_source_entity_name = borrowed[0][1] if borrowed else None
    for item in allocation["line_items"]:
        item["task_type"] = task_type_by_key.get((item["category"], item["name"]), task_types[0])

    # 카탈로그를 다른 법인에서 차용한 경우, work_days/quantity도 그 출처 법인 카탈로그에서
    # 찾는다(pdf_service.render_entity_quote_pdf와 동일한 규칙) — 과업종류마다 차용 여부가
    # 다를 수 있어 과업종류별로 따로 계산한다.
    catalog_entity_id_by_task_type = {
        task_type: pdf_service.resolve_catalog_entity_id(supabase, quote["entity_id"], entity_name, task_type)
        for task_type in task_types
    }

    # 미리보기 UI에서 단가/작업일/수량까지 바로 보여주기 위해, PDF 발급 때와 같은 로직으로
    # 지금 미리 계산해 저장한다(2026-07-10, 미리보기 컬럼 확장 요청). 템플릿을 못 찾는 등
    # 계산이 안 되는 경우엔 compute_line_item_pricing이 알아서 안전한 기본값으로 대체하므로
    # 생성 자체가 실패하지는 않는다.
    enriched_line_items = pdf_service.compute_line_item_pricing(
        supabase, quote["entity_id"], task_types, selected_modules, catalog_entity_id_by_task_type, allocation["line_items"]
    )

    supabase.table("entity_quotes").update(
        {
            "total_amount": allocation["grand_total"],
            "line_items": enriched_line_items,
            "is_catalog_borrowed": is_catalog_borrowed,
            "catalog_source_entity_name": catalog_source_entity_name,
            "selected_modules": selected_modules,
            "markup_ratio": None if quote["is_primary"] else (1 + COMPARISON_MARKUP),
        }
    ).eq("id", quote["id"]).execute()

    label = "본견적 최초 생성" if quote["is_primary"] else f"비교견적 최초 생성 (마크업 +{int(COMPARISON_MARKUP * 100)}%)"
    _save_version(quote["id"], label, enriched_line_items)


def generate_estimate_set(
    estimate_set_id: str, selections: Optional[Dict[str, List[str]]] = None
) -> EstimateSetOut:
    supabase = get_supabase()
    selections = selections or {}

    set_res = supabase.table("estimate_sets").select("*").eq("id", estimate_set_id).execute()
    if not set_res.data:
        raise HTTPException(status_code=404, detail="견적 세트를 찾을 수 없습니다.")
    estimate_set = set_res.data[0]

    quotes_res = (
        supabase.table("entity_quotes")
        .select("id, entity_id, is_primary, task_type, task_types, service_name, entity_templates(name)")
        .eq("estimate_set_id", estimate_set_id)
        .execute()
    )

    # 법인별 견적서는 서로 완전히 독립적이라(각자 다른 entity_quotes 행) 순서대로 기다릴 필요가
    # 없다 — 동시에 생성해 견적 세트 전체 생성 시간을 법인 수만큼 나눈다(2026-07-10, 생성 속도
    # 개선 요청). 한 법인이라도 실패하면 그 예외를 그대로 올려 기존 에러 처리 방식을 유지한다.
    quotes = quotes_res.data
    if quotes:
        with ThreadPoolExecutor(max_workers=len(quotes)) as pool:
            futures = [pool.submit(_generate_one_quote, quote, estimate_set, selections) for quote in quotes]
            for future in futures:
                future.result()

    from app.services.estimate_service import get_estimate_set  # 순환 참조 회피

    return get_estimate_set(estimate_set_id)
