"""실 데이터 전수 검사 — `python backend/scripts/audit_quotes.py`

단위 테스트와 타입체크로는 안 잡히는 것들을 실제 DB 데이터로 확인한다. 2026-08-21에
부가세 이중 계산(화면), 인상률 9.9%(격자 미달), extract_json 회귀가 전부 여기 걸렸을
문제인데 셋 다 사용자가 브라우저에서 먼저 발견했다 — 코드를 고친 뒤에는 이 스크립트를
돌리고 나서 "확인했다"고 말한다.

검사하는 불변식:
  1. total_amount == 항목 합 × 1.1        (화면·발급본 총액이 갈리지 않는가)
  2. amount == 그 양식의 수식(단가 × 배수)  (법인별 수식을 지켰는가)
  3. 단가·금액이 만원 단위               (266,250원 같은 잔돈이 없는가)
  4. 비교견적 > 본견적, 인상률 일치        (역전·어긋남이 없는가)

기존 견적서 중 상당수는 2026-08-21 재설계 이전 파이프라인 산출물이라 위반이 남아 있다 —
그 견적서들은 다시 생성해야 정리된다. 새로 만든 견적서에서 위반이 나오면 그건 회귀다.

"만원 단위" 위반은 사용자가 화면에서 금액을 직접 친 견적서에서도 정상적으로 나온다 —
사용자가 친 값은 코드가 다시 건드리지 않는 게 규칙이라(2026-08-21 결정), 금액 4,850,000을
수량 16으로 나눈 단가 303,125가 그대로 저장된다. 생성 경로 산출물인지 사용자 편집분인지는
quote_versions.edit_request_text("직접편집" 여부)로 구분한다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import get_supabase
from app.services import pdf_service
from app.services.quote_pricing import grand_total, structural_violations

sb = get_supabase()
sets = sb.table("estimate_sets").select("id,project_name,vat_included,total_amount").execute().data
problems, checked = [], 0

def flag(where, msg):
    problems.append(f"[{where}] {msg}")

for st in sets:
    quotes = sb.table("entity_quotes").select(
        "id,is_primary,total_amount,line_items,markup_ratio,entity_id,task_types,selected_modules,entity_templates(name)"
    ).eq("estimate_set_id", st["id"]).execute().data
    primary = next((q for q in quotes if q["is_primary"]), None)
    for q in quotes:
        items = q.get("line_items") or []
        if not items:
            continue
        checked += 1
        who = f"{st['project_name'][:14]}/{q['entity_templates']['name']}"
        supply = sum(i["amount"] for i in items)

        # 1) total_amount == 공급가액 × 1.1
        expected = grand_total(supply, st["vat_included"])
        if round(float(q["total_amount"])) != expected:
            flag(who, f"총액 불일치: DB {float(q['total_amount']):,.0f} ≠ 항목합×1.1 {expected:,}")

        # 2·3) 항목 단위 불변식 — generation_service._store가 저장 직전 쓰는 것과 같은 구현
        form = pdf_service.resolve_form_spec(sb, q["entity_id"], q["task_types"], q.get("selected_modules"))
        for v in structural_violations(items, form):
            flag(who, v)

        # 4) 비교견적은 본견적보다 비싸야 한다 + 인상률이 실제로 맞는가
        if not q["is_primary"] and primary and primary.get("line_items"):
            p_total = float(primary["total_amount"])
            if float(q["total_amount"]) <= p_total:
                flag(who, f"역전: 비교 {float(q['total_amount']):,.0f} ≤ 본견적 {p_total:,.0f}")
            elif q.get("markup_ratio"):
                actual = float(q["total_amount"]) / p_total
                if abs(actual - float(q["markup_ratio"])) > 0.005:
                    flag(who, f"인상률 어긋남: 지정 {(float(q['markup_ratio'])-1)*100:.1f}% ≠ 실제 {(actual-1)*100:.1f}%")

print(f"검사한 견적서 {checked}건 / 문제 {len(problems)}건\n")
for p in problems: print(" ", p)
