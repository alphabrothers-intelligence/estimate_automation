"""본견적↔비교견적 총액 동기화 (PRD 8장 미해결 질문 3번 답, 2026-08-11 사용자 결정).

법인마다 카탈로그 항목 구성이 달라(예: 마케팅 블렌디드랩 vs 테스티파이) 항목 단위
1:1 대응을 전제할 수 없어, 동기화는 견적서 전체 총액 단위로만 이뤄진다.

- 비교견적은 entity_quotes.markup_ratio(본견적 총액 대비 배율, 최초 생성 시 1.10)를 가진다.
- 본견적 총액이 바뀌면 → 배율을 유지한 채 각 비교견적의 기존 항목 금액을 비례 확대/축소한다.
- 비교견적 총액을 직접 바꾸면 → 그 비교견적의 markup_ratio만 새로 계산해 갱신한다(본견적은 그대로).
"""

from typing import List

from app.config import get_supabase
from app.models.estimate import EntityQuoteOut
from app.services import pdf_service
from app.services.allocation_service import (
    COMPARISON_AMOUNT_UNIT,
    grand_total,
    reconcile_snapped_items,
    snap_unit_price,
)
from app.services.generation_service import _save_version


def _scale_items_to_supply(line_items: list, target_supply: int) -> list:
    """비교견적 총액을 다시 맞춘다 — 단가에 배율을 곱하고 수량은 그대로 둔다.

    수량·작업일은 카탈로그가 정한 업무량이라 금액을 맞추려고 건드리지 않는다(그래야 "주간
    Wrap-Up 16회 / 액션플랜 16회"처럼 한 묶음인 항목들의 수량이 어긋나지 않는다). 단가를 같은
    배율로 함께 늘리면 항목 간 상대 중요도도 그대로 유지된다(2026-08-20 사용자 요구).
    스냅으로 벌어진 잔액은 reconcile_snapped_items가 단가를 단위씩 움직여 되돌린다.
    """
    current_supply = sum(item["amount"] for item in line_items)
    if current_supply <= 0:
        return line_items
    factor = target_supply / current_supply
    scaled = []
    for item in line_items:
        new_item = dict(item)
        # 금액과 단가를 같은 배율로 함께 넘긴다 — snap_unit_price가 둘의 비(=수량×작업일)를
        # 그대로 유지하므로, 저장된 단가와 공급가액의 관계가 스케일링 후에도 깨지지 않는다.
        new_item["amount"], new_item["unit_price"] = snap_unit_price(
            item["amount"] * factor,
            (item.get("unit_price") or item["amount"]) * factor,
            COMPARISON_AMOUNT_UNIT,
        )
        scaled.append(new_item)
    return reconcile_snapped_items(scaled, target_supply, COMPARISON_AMOUNT_UNIT)


def sync_comparisons_from_primary(
    estimate_set_id: str, primary_total: float, vat_included: bool
) -> List[EntityQuoteOut]:
    """본견적 총액이 바뀐 뒤 호출 — 같은 세트의 비교견적들을 저장된 배율대로 다시 맞춘다.
    갱신된 비교견적들을 반환한다 — 프론트엔드가 커밋 후 이 결과로 화면을 바로 갱신할 수 있게
    해서, 굳이 세트 전체를 다시 조회하지 않아도 되게 한다(2026-08-17, 커밋 응답 지연 개선)."""
    supabase = get_supabase()
    comparisons = (
        supabase.table("entity_quotes")
        .select(
            "id, entity_id, task_type, task_types, line_items, markup_ratio, selected_modules, "
            "is_catalog_borrowed, catalog_source_entity_name, service_name, quote_date, "
            "recipient_name, recipient_contact, recipient_phone, recipient_email, entity_templates(name)"
        )
        .eq("estimate_set_id", estimate_set_id)
        .eq("is_primary", False)
        .execute()
    ).data

    updated: List[EntityQuoteOut] = []
    for quote in comparisons:
        ratio = quote["markup_ratio"]
        if not ratio or not quote["line_items"]:
            continue
        target_grand_total = round(primary_total * float(ratio))
        target_supply = round(target_grand_total / 1.1)
        scaled_items = _scale_items_to_supply(quote["line_items"], target_supply)
        new_grand_total = grand_total(sum(i["amount"] for i in scaled_items), vat_included)

        supabase.table("entity_quotes").update(
            {"total_amount": new_grand_total, "line_items": scaled_items}
        ).eq("id", quote["id"]).execute()
        _save_version(quote["id"], "본견적 연동 자동 동기화", scaled_items)

        updated.append(
            EntityQuoteOut(
                id=quote["id"],
                entity_id=quote["entity_id"],
                entity_name=quote["entity_templates"]["name"],
                is_primary=False,
                task_type=quote["task_type"],
                task_types=quote["task_types"],
                total_amount=new_grand_total,
                line_items=scaled_items,
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
        )
    return updated


def update_ratio_from_comparison(entity_quote_id: str, estimate_set_id: str, new_total: float) -> None:
    """비교견적 총액을 직접 바꾼 뒤 호출 — 그 비교견적의 markup_ratio만 새로 계산해 갱신한다."""
    supabase = get_supabase()
    primary = (
        supabase.table("entity_quotes")
        .select("total_amount")
        .eq("estimate_set_id", estimate_set_id)
        .eq("is_primary", True)
        .execute()
    ).data
    if not primary or not primary[0]["total_amount"]:
        return  # 세트에 본견적이 없으면(비교견적만 발급) 배율 기준이 없어 아무것도 하지 않는다.

    new_ratio = new_total / float(primary[0]["total_amount"])
    supabase.table("entity_quotes").update({"markup_ratio": round(new_ratio, 4)}).eq(
        "id", entity_quote_id
    ).execute()
