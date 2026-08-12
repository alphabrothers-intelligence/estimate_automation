"""본견적↔비교견적 총액 동기화 (PRD 8장 미해결 질문 3번 답, 2026-08-11 사용자 결정).

법인마다 카탈로그 항목 구성이 달라(예: 마케팅 블렌디드랩 vs 테스티파이) 항목 단위
1:1 대응을 전제할 수 없어, 동기화는 견적서 전체 총액 단위로만 이뤄진다.

- 비교견적은 entity_quotes.markup_ratio(본견적 총액 대비 배율, 최초 생성 시 1.10)를 가진다.
- 본견적 총액이 바뀌면 → 배율을 유지한 채 각 비교견적의 기존 항목 금액을 비례 확대/축소한다.
- 비교견적 총액을 직접 바꾸면 → 그 비교견적의 markup_ratio만 새로 계산해 갱신한다(본견적은 그대로).
"""

from app.config import get_supabase
from app.services.generation_service import _save_version


def _grand_total(supply_amount: float, vat_included: bool) -> int:
    return round(supply_amount * 1.1) if vat_included else supply_amount + round(supply_amount * 0.1)


def _scale_items_to_supply(line_items: list, target_supply: int) -> list:
    current_supply = sum(item["amount"] for item in line_items)
    if current_supply <= 0:
        return line_items
    factor = target_supply / current_supply
    scaled = []
    for item in line_items:
        new_item = dict(item)
        new_item["amount"] = round(item["amount"] * factor)
        divisor = (new_item.get("work_days") or 1) * (new_item.get("quantity") or 1)
        new_item["unit_price"] = new_item["amount"] / divisor if divisor else new_item["amount"]
        scaled.append(new_item)

    # 반올림 오차는 마지막 항목에서 흡수한다 (allocation_service._reconcile_rounding과 같은 패턴).
    diff = target_supply - sum(i["amount"] for i in scaled)
    if diff != 0 and scaled:
        last = scaled[-1]
        last["amount"] += diff
        divisor = (last.get("work_days") or 1) * (last.get("quantity") or 1)
        last["unit_price"] = last["amount"] / divisor if divisor else last["amount"]
    return scaled


def sync_comparisons_from_primary(estimate_set_id: str, primary_total: float, vat_included: bool) -> None:
    """본견적 총액이 바뀐 뒤 호출 — 같은 세트의 비교견적들을 저장된 배율대로 다시 맞춘다."""
    supabase = get_supabase()
    comparisons = (
        supabase.table("entity_quotes")
        .select("id, line_items, markup_ratio")
        .eq("estimate_set_id", estimate_set_id)
        .eq("is_primary", False)
        .execute()
    ).data

    for quote in comparisons:
        ratio = quote["markup_ratio"]
        if not ratio or not quote["line_items"]:
            continue
        target_grand_total = round(primary_total * float(ratio))
        target_supply = round(target_grand_total / 1.1)
        scaled_items = _scale_items_to_supply(quote["line_items"], target_supply)
        new_grand_total = _grand_total(sum(i["amount"] for i in scaled_items), vat_included)

        supabase.table("entity_quotes").update(
            {"total_amount": new_grand_total, "line_items": scaled_items}
        ).eq("id", quote["id"]).execute()
        _save_version(quote["id"], "본견적 연동 자동 동기화", scaled_items)


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
