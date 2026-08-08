from datetime import date
from typing import List

from fastapi import HTTPException

from app.config import get_supabase
from app.models.catalog import EntityModuleOptions
from app.models.estimate import EntityQuoteOut, EstimateSetCreate, EstimateSetOut, EstimateSetSummary, LineItemIn
from app.services import catalog_service, pdf_service
from app.services.catalog_service import EXCLUDED_ENTITIES_BY_TASK_TYPE
from app.services.generation_service import _save_version

TESTIFY_NAME = "테스티파이"  # service_name(용역명) 필드는 이 법인 템플릿에만 존재 (010_seed_quote_templates.sql)


def list_estimate_sets() -> List[EstimateSetSummary]:
    supabase = get_supabase()
    sets_res = supabase.table("estimate_sets").select("*").order("created_at", desc=True).execute()
    if not sets_res.data:
        return []

    set_ids = [row["id"] for row in sets_res.data]
    quotes_res = (
        supabase.table("entity_quotes")
        .select("estimate_set_id, entity_templates(name)")
        .in_("estimate_set_id", set_ids)
        .execute()
    )
    entities_by_set: dict[str, list[str]] = {set_id: [] for set_id in set_ids}
    for row in quotes_res.data:
        entities_by_set[row["estimate_set_id"]].append(row["entity_templates"]["name"])

    return [
        EstimateSetSummary(
            id=row["id"],
            project_name=row["project_name"],
            total_amount=float(row["total_amount"]),
            vat_included=row["vat_included"],
            task_type=row["task_type"],
            created_at=str(row["created_at"]),
            quote_count=len(entities_by_set[row["id"]]),
            entity_names=entities_by_set[row["id"]],
        )
        for row in sets_res.data
    ]


def create_estimate_set(payload: EstimateSetCreate) -> EstimateSetOut:
    supabase = get_supabase()

    all_entities = {row["id"]: row["name"] for row in supabase.table("entity_templates").select("id, name").execute().data}

    primary_selection = next((e for e in payload.entities if e.is_primary), None)
    primary_entity_id = primary_selection.entity_id if primary_selection else None

    for selection in payload.entities:
        if selection.entity_id not in all_entities:
            raise HTTPException(status_code=400, detail="존재하지 않는 법인이 선택되었습니다.")
        entity_name = all_entities[selection.entity_id]
        for task_type in selection.task_types:
            if entity_name in EXCLUDED_ENTITIES_BY_TASK_TYPE.get(task_type, set()):
                raise HTTPException(
                    status_code=400,
                    detail=f"{entity_name}은(는) '{task_type}' 과업종류를 취급하지 않습니다.",
                )

    primary_entity_name = all_entities.get(primary_entity_id) if primary_entity_id else None
    if primary_entity_name == TESTIFY_NAME and not (payload.service_name and payload.service_name.strip()):
        raise HTTPException(
            status_code=400,
            detail="테스티파이를 본견적서 법인으로 선택하면 용역명을 입력해야 합니다.",
        )

    # estimate_sets.task_type은 세트 전체를 대표하는 단일값이 더 이상 없어(기업마다 과업종류가
    # 다를 수 있음), 실제 쓰인 과업종류를 모아 목록 화면 표시용 요약 문자열로만 저장한다.
    task_type_summary = "+".join(
        dict.fromkeys(task_type for selection in payload.entities for task_type in selection.task_types)
    )

    set_res = (
        supabase.table("estimate_sets")
        .insert(
            {
                "project_name": payload.project_name,
                "total_amount": payload.total_amount,
                "vat_included": payload.vat_included,
                "task_type": task_type_summary,
                "primary_entity_id": primary_entity_id,
            }
        )
        .execute()
    )
    estimate_set = set_res.data[0]

    today = date.today().isoformat()
    entity_quote_rows = [
        {
            "estimate_set_id": estimate_set["id"],
            "entity_id": selection.entity_id,
            "is_primary": selection.is_primary,
            "task_type": task_type,
            "recipient_name": payload.recipient_name,
            "quote_date": today,
            "total_amount": payload.total_amount if selection.is_primary else 0,
            "line_items": [],
            # 비교견적으로 테스티파이가 포함된 경우엔 여기서 받지 않고 나중에(발급 전) 채운다.
            "service_name": payload.service_name if selection.is_primary and primary_entity_name == TESTIFY_NAME else None,
        }
        for selection in payload.entities
        for task_type in selection.task_types
    ]
    quotes_res = supabase.table("entity_quotes").insert(entity_quote_rows).execute()

    entity_quotes = [
        EntityQuoteOut(
            id=row["id"],
            entity_id=row["entity_id"],
            entity_name=all_entities[row["entity_id"]],
            is_primary=row["is_primary"],
            task_type=row["task_type"],
            service_name=row["service_name"],
            **pdf_service.get_column_display(supabase, row["entity_id"], row["task_type"], None),
        )
        for row in quotes_res.data
    ]

    return EstimateSetOut(
        id=estimate_set["id"],
        project_name=estimate_set["project_name"],
        total_amount=float(estimate_set["total_amount"]),
        vat_included=estimate_set["vat_included"],
        task_type=estimate_set["task_type"],
        primary_entity_id=estimate_set["primary_entity_id"],
        entity_quotes=entity_quotes,
    )


def get_estimate_set(estimate_set_id: str) -> EstimateSetOut:
    supabase = get_supabase()
    set_res = supabase.table("estimate_sets").select("*").eq("id", estimate_set_id).execute()
    if not set_res.data:
        raise HTTPException(status_code=404, detail="견적 세트를 찾을 수 없습니다.")
    estimate_set = set_res.data[0]

    quotes_res = (
        supabase.table("entity_quotes")
        .select(
            "id, entity_id, is_primary, task_type, total_amount, line_items, selected_modules, "
            "is_catalog_borrowed, catalog_source_entity_name, service_name, entity_templates(name)"
        )
        .eq("estimate_set_id", estimate_set_id)
        .execute()
    )
    entity_quotes = [
        EntityQuoteOut(
            id=row["id"],
            entity_id=row["entity_id"],
            entity_name=row["entity_templates"]["name"],
            is_primary=row["is_primary"],
            task_type=row["task_type"],
            total_amount=float(row["total_amount"]),
            line_items=row["line_items"] or [],
            is_catalog_borrowed=row["is_catalog_borrowed"],
            catalog_source_entity_name=row["catalog_source_entity_name"],
            service_name=row["service_name"],
            **pdf_service.get_column_display(
                supabase, row["entity_id"], row["task_type"], row.get("selected_modules")
            ),
        )
        for row in quotes_res.data
    ]

    return EstimateSetOut(
        id=estimate_set["id"],
        project_name=estimate_set["project_name"],
        total_amount=float(estimate_set["total_amount"]),
        vat_included=estimate_set["vat_included"],
        task_type=estimate_set["task_type"],
        primary_entity_id=estimate_set["primary_entity_id"],
        entity_quotes=entity_quotes,
    )


def get_module_options_for_set(estimate_set_id: str) -> List[EntityModuleOptions]:
    """세트 내 각 법인별 견적서가 고를 수 있는 옵션 모듈 목록을 반환한다 (PRD 7장 3~4단계)."""
    supabase = get_supabase()
    quotes_res = (
        supabase.table("entity_quotes")
        .select("id, entity_id, task_type, entity_templates(name)")
        .eq("estimate_set_id", estimate_set_id)
        .execute()
    )
    if not quotes_res.data:
        raise HTTPException(status_code=404, detail="견적 세트를 찾을 수 없습니다.")

    results = []
    for row in quotes_res.data:
        entity_name = row["entity_templates"]["name"]
        has_modules, groups = catalog_service.get_module_options(row["entity_id"], entity_name, row["task_type"])
        results.append(
            EntityModuleOptions(
                entity_quote_id=row["id"],
                entity_name=entity_name,
                has_modules=has_modules,
                groups=groups,
            )
        )
    return results


def update_service_name(entity_quote_id: str, service_name: str) -> EntityQuoteOut:
    """견적서의 '용역명'을 입력/수정한다. 테스티파이 템플릿에만 해당 셀이 있다 (4.2)."""
    supabase = get_supabase()
    quote_res = (
        supabase.table("entity_quotes")
        .select(
            "id, entity_id, is_primary, task_type, total_amount, line_items, selected_modules, "
            "is_catalog_borrowed, catalog_source_entity_name, entity_templates(name)"
        )
        .eq("id", entity_quote_id)
        .execute()
    )
    if not quote_res.data:
        raise HTTPException(status_code=404, detail="견적서를 찾을 수 없습니다.")
    quote = quote_res.data[0]

    if quote["entity_templates"]["name"] != TESTIFY_NAME:
        raise HTTPException(status_code=400, detail="용역명은 테스티파이 견적서에만 입력할 수 있습니다.")

    supabase.table("entity_quotes").update({"service_name": service_name}).eq("id", entity_quote_id).execute()

    return EntityQuoteOut(
        id=quote["id"],
        entity_id=quote["entity_id"],
        entity_name=quote["entity_templates"]["name"],
        is_primary=quote["is_primary"],
        task_type=quote["task_type"],
        total_amount=float(quote["total_amount"]),
        line_items=quote["line_items"] or [],
        is_catalog_borrowed=quote["is_catalog_borrowed"],
        catalog_source_entity_name=quote["catalog_source_entity_name"],
        service_name=service_name,
        **pdf_service.get_column_display(
            supabase, quote["entity_id"], quote["task_type"], quote.get("selected_modules")
        ),
    )


def update_line_items(entity_quote_id: str, items: List[LineItemIn]) -> EntityQuoteOut:
    """화면에서 항목명・금액을 직접 클릭해 고친 뒤 저장한다 (PRD 4.4 "직접 편집").

    단가/작업일/수량은 실제 발급 시 pdf_service가 항목명 기준으로 카탈로그에서 다시 계산해
    채우므로(_lookup_work_days_quantity) 여기서 직접 편집 대상으로 받지 않는다 — 카테고리・
    항목명・금액만 실제 문서에 반영된다.
    """
    supabase = get_supabase()
    quote_res = (
        supabase.table("entity_quotes")
        .select(
            "id, entity_id, is_primary, task_type, selected_modules, estimate_set_id, "
            "is_catalog_borrowed, catalog_source_entity_name, service_name, entity_templates(name)"
        )
        .eq("id", entity_quote_id)
        .execute()
    )
    if not quote_res.data:
        raise HTTPException(status_code=404, detail="견적서를 찾을 수 없습니다.")
    quote = quote_res.data[0]

    vat_included = (
        supabase.table("estimate_sets").select("vat_included").eq("id", quote["estimate_set_id"]).execute()
    ).data[0]["vat_included"]

    supply_amount = sum(item.amount for item in items)
    grand_total = round(supply_amount * 1.1) if vat_included else supply_amount + round(supply_amount * 0.1)

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
        [item.model_dump() for item in items],
    )
    supabase.table("entity_quotes").update(
        {"total_amount": grand_total, "line_items": new_line_items}
    ).eq("id", entity_quote_id).execute()

    _save_version(entity_quote_id, "직접편집", new_line_items)

    return EntityQuoteOut(
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
