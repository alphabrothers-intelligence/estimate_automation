from datetime import date
from typing import List

from fastapi import HTTPException

from app.config import get_supabase
from app.models.catalog import EntityModuleOptions
from app.models.estimate import EntityQuoteOut, EstimateSetCreate, EstimateSetOut, EstimateSetSummary, LineItemIn, LineItemsUpdateResult, QuoteVersionOut, RecipientInfoUpdate
from app.services import allocation_service, catalog_service, pdf_service
from app.services.catalog_service import EXCLUDED_ENTITIES_BY_TASK_TYPE
from app.services.generation_service import _save_version
from app.services import sync_service

TESTIFY_NAME = "테스티파이"  # service_name(용역명) 필드는 이 법인 템플릿에만 존재 (010_seed_quote_templates.sql)


def list_estimate_sets() -> List[EstimateSetSummary]:
    supabase = get_supabase()
    # 예전엔 estimate_sets, entity_quotes를 각각 조회해 파이썬에서 합쳤다(왕복 2회) —
    # PostgREST 중첩 임베드로 한 번의 요청에 합쳐서 지연시간을 절반으로 줄인다.
    sets_res = (
        supabase.table("estimate_sets")
        .select("*, entity_quotes(entity_templates(name))")
        .order("created_at", desc=True)
        .execute()
    )
    return [
        EstimateSetSummary(
            id=row["id"],
            project_name=row["project_name"],
            total_amount=float(row["total_amount"]),
            vat_included=row["vat_included"],
            task_type=row["task_type"],
            created_at=str(row["created_at"]),
            quote_count=len(row["entity_quotes"]),
            entity_names=[q["entity_templates"]["name"] for q in row["entity_quotes"]],
        )
        for row in sets_res.data
    ]


def delete_estimate_set(estimate_set_id: str) -> None:
    supabase = get_supabase()
    res = supabase.table("estimate_sets").delete().eq("id", estimate_set_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="견적 세트를 찾을 수 없습니다.")


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
    # 용역명(service_name)은 예전 테스티파이 양식의 B12 칸 전용 필드였다 — 039 마이그레이션으로
    # 알파브라더스형 신양식(구분(대)/구분(중)/상품명/상품구성)으로 갈아타면서 그 칸 자체가
    # 없어져 필수 검증도 함께 뗀다(2026-08-19). 컬럼과 입력 UI는 남겨 둔다(이미 발급된 견적서의
    # 값을 보존하고, 다시 필요해지면 cell_map에 칸만 다시 이어주면 되도록).

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
    # 기업 하나가 과업종류를 교차 선택해도(예: 마케팅+시장검증) entity_quote는 1건만 만든다 —
    # 항목을 합쳐 하나의 견적서로 발급한다(2026-08-10 사용자 결정). task_type은 "+"로 합친
    # 표시용 라벨, task_types가 실제 목록이다.
    entity_quote_rows = [
        {
            "estimate_set_id": estimate_set["id"],
            "entity_id": selection.entity_id,
            "is_primary": selection.is_primary,
            "task_type": "+".join(selection.task_types),
            "task_types": selection.task_types,
            "recipient_name": payload.recipient_name,
            "recipient_contact": payload.recipient_contact,
            "recipient_phone": payload.recipient_phone,
            "recipient_email": payload.recipient_email,
            "quote_date": today,
            "total_amount": payload.total_amount if selection.is_primary else 0,
            "line_items": [],
            # 사용자가 지정한 비교견적 마크업 배율(본견적 대비, 예: 1.10 = +10%) — None이면
            # generation_service가 기본값(+10%)을 적용해 생성 시점에 다시 채운다.
            "markup_ratio": (
                None if selection.is_primary or selection.markup_ratio is None
                else round(1 + selection.markup_ratio, 4)
            ),
            # 비교견적으로 테스티파이가 포함된 경우엔 여기서 받지 않고 나중에(발급 전) 채운다.
            "service_name": payload.service_name if selection.is_primary and primary_entity_name == TESTIFY_NAME else None,
        }
        for selection in payload.entities
    ]
    quotes_res = supabase.table("entity_quotes").insert(entity_quote_rows).execute()

    entity_quotes = [
        EntityQuoteOut(
            id=row["id"],
            entity_id=row["entity_id"],
            entity_name=all_entities[row["entity_id"]],
            is_primary=row["is_primary"],
            task_type=row["task_type"],
            task_types=row["task_types"],
            service_name=row["service_name"],
            quote_date=row["quote_date"],
            recipient_name=row["recipient_name"],
            recipient_contact=row["recipient_contact"],
            recipient_phone=row["recipient_phone"],
            recipient_email=row["recipient_email"],
            **pdf_service.get_column_display(supabase, row["entity_id"], row["task_types"], None),
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
            "id, entity_id, is_primary, task_type, task_types, total_amount, line_items, selected_modules, "
            "is_catalog_borrowed, catalog_source_entity_name, service_name, quote_date, "
            "recipient_name, recipient_contact, recipient_phone, recipient_email, entity_templates(name)"
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
            task_types=row["task_types"],
            total_amount=float(row["total_amount"]),
            line_items=row["line_items"] or [],
            is_catalog_borrowed=row["is_catalog_borrowed"],
            catalog_source_entity_name=row["catalog_source_entity_name"],
            service_name=row["service_name"],
            quote_date=row["quote_date"],
            recipient_name=row["recipient_name"],
            recipient_contact=row["recipient_contact"],
            recipient_phone=row["recipient_phone"],
            recipient_email=row["recipient_email"],
            **pdf_service.get_column_display(
                supabase, row["entity_id"], row["task_types"], row.get("selected_modules")
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
        .select("id, entity_id, task_types, entity_templates(name)")
        .eq("estimate_set_id", estimate_set_id)
        .execute()
    )
    if not quotes_res.data:
        raise HTTPException(status_code=404, detail="견적 세트를 찾을 수 없습니다.")

    results = []
    for row in quotes_res.data:
        entity_name = row["entity_templates"]["name"]
        # 과업종류를 교차 선택한 견적서는 각 과업종류의 선택지 그룹을 그대로 이어붙인다 —
        # 모듈명이 과업종류 간에 겹치지 않아 뒤섞여도 어느 그룹이 어느 과업종류 것인지는
        # option_key/module_names로 여전히 구분된다.
        has_modules = False
        groups: list = []
        for task_type in row["task_types"]:
            type_has_modules, type_groups = catalog_service.get_module_options(row["entity_id"], entity_name, task_type)
            has_modules = has_modules or type_has_modules
            groups += type_groups
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
            "id, entity_id, is_primary, task_type, task_types, total_amount, line_items, selected_modules, "
            "is_catalog_borrowed, catalog_source_entity_name, quote_date, "
            "recipient_name, recipient_contact, recipient_phone, recipient_email, entity_templates(name)"
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
        task_types=quote["task_types"],
        total_amount=float(quote["total_amount"]),
        line_items=quote["line_items"] or [],
        is_catalog_borrowed=quote["is_catalog_borrowed"],
        catalog_source_entity_name=quote["catalog_source_entity_name"],
        service_name=service_name,
        quote_date=quote["quote_date"],
        recipient_name=quote["recipient_name"],
        recipient_contact=quote["recipient_contact"],
        recipient_phone=quote["recipient_phone"],
        recipient_email=quote["recipient_email"],
        **pdf_service.get_column_display(
            supabase, quote["entity_id"], quote["task_types"], quote.get("selected_modules")
        ),
    )


def update_quote_date(entity_quote_id: str, quote_date: date) -> EntityQuoteOut:
    """견적서의 '견적일자'(년/월/일)를 직접 수정한다 — 발급 후에도 채팅 없이 바로 고칠 수 있는
    전용 입력칸이 필요하다는 사용자 요청(2026-08-11)."""
    supabase = get_supabase()
    quote_res = (
        supabase.table("entity_quotes")
        .select(
            "id, entity_id, is_primary, task_type, task_types, total_amount, line_items, selected_modules, "
            "is_catalog_borrowed, catalog_source_entity_name, service_name, "
            "recipient_name, recipient_contact, recipient_phone, recipient_email, entity_templates(name)"
        )
        .eq("id", entity_quote_id)
        .execute()
    )
    if not quote_res.data:
        raise HTTPException(status_code=404, detail="견적서를 찾을 수 없습니다.")
    quote = quote_res.data[0]

    quote_date_str = quote_date.isoformat()
    supabase.table("entity_quotes").update({"quote_date": quote_date_str}).eq("id", entity_quote_id).execute()

    return EntityQuoteOut(
        id=quote["id"],
        entity_id=quote["entity_id"],
        entity_name=quote["entity_templates"]["name"],
        is_primary=quote["is_primary"],
        task_type=quote["task_type"],
        task_types=quote["task_types"],
        total_amount=float(quote["total_amount"]),
        line_items=quote["line_items"] or [],
        is_catalog_borrowed=quote["is_catalog_borrowed"],
        catalog_source_entity_name=quote["catalog_source_entity_name"],
        service_name=quote["service_name"],
        quote_date=quote_date_str,
        recipient_name=quote["recipient_name"],
        recipient_contact=quote["recipient_contact"],
        recipient_phone=quote["recipient_phone"],
        recipient_email=quote["recipient_email"],
        **pdf_service.get_column_display(
            supabase, quote["entity_id"], quote["task_types"], quote.get("selected_modules")
        ),
    )


def update_recipient_info(entity_quote_id: str, payload: RecipientInfoUpdate) -> EntityQuoteOut:
    """견적서의 수신자(고객사명)/담당자/연락처/이메일을 발급 후에도 화면에서 바로 고친다
    (2026-08-12 사용자 요청 — 생성 시점엔 선택값이라 나중에 채우거나 수정할 수 있어야 함)."""
    supabase = get_supabase()
    quote_res = (
        supabase.table("entity_quotes")
        .select(
            "id, entity_id, is_primary, task_type, task_types, total_amount, line_items, selected_modules, "
            "is_catalog_borrowed, catalog_source_entity_name, service_name, quote_date, "
            "recipient_name, recipient_contact, recipient_phone, recipient_email, entity_templates(name)"
        )
        .eq("id", entity_quote_id)
        .execute()
    )
    if not quote_res.data:
        raise HTTPException(status_code=404, detail="견적서를 찾을 수 없습니다.")
    quote = quote_res.data[0]

    update_fields = payload.model_dump(exclude_unset=True)
    supabase.table("entity_quotes").update(update_fields).eq("id", entity_quote_id).execute()
    quote.update(update_fields)

    return EntityQuoteOut(
        id=quote["id"],
        entity_id=quote["entity_id"],
        entity_name=quote["entity_templates"]["name"],
        is_primary=quote["is_primary"],
        task_type=quote["task_type"],
        task_types=quote["task_types"],
        total_amount=float(quote["total_amount"]),
        line_items=quote["line_items"] or [],
        is_catalog_borrowed=quote["is_catalog_borrowed"],
        catalog_source_entity_name=quote["catalog_source_entity_name"],
        service_name=quote["service_name"],
        quote_date=quote["quote_date"],
        recipient_name=quote["recipient_name"],
        recipient_contact=quote["recipient_contact"],
        recipient_phone=quote["recipient_phone"],
        recipient_email=quote["recipient_email"],
        **pdf_service.get_column_display(
            supabase, quote["entity_id"], quote["task_types"], quote.get("selected_modules")
        ),
    )


def update_line_items(entity_quote_id: str, items: List[LineItemIn], edit_request_text: str = "직접편집") -> LineItemsUpdateResult:
    """화면에서 항목명・금액・단가・작업일・투입인력・비고를 직접 클릭해 고친 뒤 저장한다
    (PRD 4.4 "직접 편집" — 2026-08-09 사용자 결정으로 편집 대상을 단가/작업일/투입인력/비고까지
    확장). 프론트엔드가 단가/수량 중 하나를 고치면 나머지로 금액(단가×수량, 작업일은 무관)을
    다시 계산해서 보내므로, 여기서는 받은 값을 그대로 저장한다 — 채팅 수정(edit_service)의
    미리보기도 같은 커밋 경로로 여기 들어온다(2026-08-14, edit_request_text로 출처를 구분).
    """
    supabase = get_supabase()
    quote_res = (
        supabase.table("entity_quotes")
        .select(
            "id, entity_id, is_primary, task_type, task_types, selected_modules, estimate_set_id, "
            "is_catalog_borrowed, catalog_source_entity_name, service_name, quote_date, "
            "recipient_name, recipient_contact, recipient_phone, recipient_email, entity_templates(name)"
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

    # 직접 편집은 사용자가 친 금액을 그대로 저장한다 — 10만원 단위 스냅은 자동생성·채팅 수정
    # (compute_line_item_pricing)에서만 하고, 여기서 다시 건드리면 "이 항목만 1,234,567원으로"
    # 같은 의도적인 값을 되돌려버린다.
    total = allocation_service.grand_total(sum(item.amount for item in items), vat_included)

    new_line_items = [item.model_dump() for item in items]
    supabase.table("entity_quotes").update(
        {"total_amount": total, "line_items": new_line_items}
    ).eq("id", entity_quote_id).execute()

    _save_version(entity_quote_id, edit_request_text, new_line_items)

    synced_comparison_quotes = []
    if quote["is_primary"]:
        synced_comparison_quotes = sync_service.sync_comparisons_from_primary(
            quote["estimate_set_id"], total, vat_included
        )
    else:
        sync_service.update_ratio_from_comparison(entity_quote_id, quote["estimate_set_id"], total)

    entity_quote_out = EntityQuoteOut(
        id=quote["id"],
        entity_id=quote["entity_id"],
        entity_name=quote["entity_templates"]["name"],
        is_primary=quote["is_primary"],
        task_type=quote["task_type"],
        task_types=quote["task_types"],
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
            supabase, quote["entity_id"], quote["task_types"], quote.get("selected_modules")
        ),
    )

    return LineItemsUpdateResult(
        entity_quote=entity_quote_out, synced_comparison_quotes=synced_comparison_quotes
    )


def list_quote_versions(entity_quote_id: str) -> List[QuoteVersionOut]:
    """되돌아가기/원본으로 되돌리기 버튼용 — 이 견적서의 버전 이력을 오래된 순으로 반환한다.
    diff는 저장 경로(직접편집/채팅수정 커밋/동기화/최초생성)와 무관하게 항상 그 시점 전체
    항목 목록이다(2026-08-14, edit_service가 더 이상 직접 저장하지 않게 되며 보장됨)."""
    supabase = get_supabase()
    versions = (
        supabase.table("quote_versions")
        .select("version_no, edit_request_text, edited_at, diff")
        .eq("entity_quote_id", entity_quote_id)
        .order("version_no")
        .execute()
    )
    return [
        QuoteVersionOut(
            version_no=v["version_no"],
            edit_request_text=v["edit_request_text"],
            edited_at=v["edited_at"],
            line_items=v["diff"] or [],
        )
        for v in versions.data
    ]
