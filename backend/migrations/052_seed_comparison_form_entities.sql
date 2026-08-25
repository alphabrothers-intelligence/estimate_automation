-- up
-- 비교견적 발행 전용 법인 5곳과 그 양식을 등록한다 (2026-08-25 사용자 승인).
--
-- **왜 필요했나:** 기존 비교견적 법인 중 썬데이워커 양식에 직인이 찍혀 있지 않아, 쓸 때마다
-- 날인을 따로 요청해야 해서 번거로웠다. 그래서 실무자가 직인이 이미 박힌 타사 견적서 양식
-- 묶음을 새 비교견적 양식으로 전달했다(2026-08-25 히스토리).
--
-- 출처는 `data/(알파) 마케팅, 개발, 디자인, 특허 비교견적서 모음_250917.xlsx` — 알파브라더스가
-- 실제로 받아본 타사 견적서 모음이다. 시트 8개 중 5개를 넣는다. 채택 기준은 실무자가 정했다:
-- **항목 / 견적 세부내용 / 품명 / 수량 / 단가 / 공급가액 같은 칸이 있어 우리 과업을 그대로
-- 얹을 수 있는 양식만 쓴다.** 제외한 셋:
--   · 이음/올림  = 특허 비용 견적서. 열이 "특허청 관납료 / 대리인 수수료 / 부가세"라 우리
--                   과업이 들어갈 칸 자체가 없다. 실무자도 특허 견적서는 안 쓴다고 확인.
--   · FLES        = 실무자 판단으로 제외(양식 안의 법인명이 달라 쓰기 어렵다). 기술적으로는
--                   해결했었다 — 항목 칸이 C15:D21 등 세로 7행 병합 1덩어리라 발급 시점에
--                   unmerge_cells로 풀고 행마다 다시 묶으면 정상 발급됐다(렌더링으로 확인).
--                   그 기능(unmerge_cells / column_merge_end_cols)은 pdf_service에 남아 있으니
--                   비슷한 양식이 또 오면 cell_map만 쓰면 된다.
--
-- **파일을 시트별로 쪼개지 않는다.** pdf_service가 발급 시점에 대상 시트만 남기고 나머지
-- <sheet> 정의를 지우므로(_reorder_sheet_first + _remove_other_sheets, 테스티파이 6시트가
-- 이미 그렇게 동작한다), 워크북 하나를 그대로 올리고 sheet_name만 다르게 주면 된다.
-- openpyxl로 재저장하면 서식이 깎이는데 그 위험도 사라진다.
--
-- 과업종류는 마케팅·시장검증 둘만 건다. 이 양식들은 "다른 업체가 우리 과업을 자기 양식으로
-- 견적낸 것"을 흉내내는 자리라, 카탈로그는 본견적 법인 것을 그대로 쓴다(비교견적은
-- generation_service._generate_comparison이 본견적을 리라이팅하지 카탈로그를 읽지 않는다).

insert into entity_templates (name) values
('안르'), ('위드앤코'), ('테키'), ('다름과이음'), ('스프린트');

insert into quote_templates (entity_id, task_type, module_name, storage_path, sheet_name, cell_map)
select e.id, t.task_type, null, 'templates/comparison_forms.xlsx', s.sheet_name, s.cell_map::jsonb
from (values
-- ─────────────────────────────────────────────────────────────────────────
-- 안르 — 품명/규격단위/수량/단가/공급가액/세액/비고. 항목 행마다 세액 칸이 따로 있다.
--   원본 수식: I{r} = IF(F{r}="", H{r}, F{r}*H{r})   ← 수량 비면 단가 그대로, 아니면 단가×수량
--             J{r} = I{r}*0.1                        ← 세액
--   우리는 수량을 항상 채우므로 단가×수량으로 계산된다(FormSpec 기본값과 일치).
--   D16(합계금액 세액포함) = SUM(I33:J33), I16 = D16 — 소계만 채우면 연쇄로 따라온다.
('안르', '안르 (마케팅, 개발, 디자인)', '{
    "header_fields": {"quote_date": "I4", "recipient_name": "C6", "client_contact": "C7",
                      "client_phone": "C10", "client_email": "C11", "service_name": "C12"},
    "header_labels": {"client_phone": "연 락 처 : ", "client_email": "이 메 일 : "},
    "item_blocks": [{"rows": [19,20,21,22,23,24,25,26,27,28,29,30,31,32]}],
    "columns": {"item_name": "C", "description": "E", "quantity": "F", "unit_price": "H",
                "supply_amount": "I", "tax_amount": "J", "note": "K"},
    "column_labels": {"item_name": "품명", "description": "규격/단위", "quantity": "수량",
                      "unit_price": "단가", "supply_amount": "공급가액", "tax_amount": "세액", "note": "비고"},
    "detail_column_order": ["description", "quantity", "unit_price"],
    "totals": {"supply_total_cell": "I33"},
    "notes": "타사(안르) 양식. C12는 \"견 적 명 : \" 라벨이 셀에 박혀 있어 service_name 핸들러가 \"용역명: ~\"로 덮어쓴다."
}'),
-- ─────────────────────────────────────────────────────────────────────────
-- 위드앤코 — 항목/세부내용/단가/수량/소요기간/금액/비고. 항목마다 여러 행을 세로 병합해서
--   쓴다(C14:D17, C18:D19, C20:D21, C22:D23, C24:D27) → 실제 앵커 행은 5개뿐이다.
--   I{r} = F{r}*G{r} (단가×수량), I28 = SUM(I14:I27), E29 = I28*0.1, I29 = I28+E29.
--   E7(업무 기간)은 원본에 "약 60일"(남의 견적 건 값)이 박혀 있어 duration_text로 덮는다.
('위드앤코', '위드앤코 (마케팅, 디자인)', '{
    "header_fields": {"quote_date_serial": "E5", "service_name": "E6", "duration_text": "E7"},
    "header_labels": {"service_name": ""},
    "item_blocks": [{"rows": [14,18,20,22,24]}],
    "always_clear_cells": ["E15","E16","E17","E19","E21","E23","E25","E26","E27"],
    "columns": {"item_name": "C", "description": "E", "unit_price": "F", "quantity": "G",
                "work_days": "H", "amount": "I", "note": "J"},
    "column_labels": {"item_name": "항목", "description": "견적 세부 내용", "unit_price": "단가",
                      "quantity": "수량", "work_days": "소요기간", "amount": "금 액(원)", "note": "비고"},
    "detail_column_order": ["description", "unit_price", "quantity", "work_days"],
    "totals": {"supply_total_cell": "I28", "vat_cell": "E29", "grand_total_cell": "I29", "top_display_cell": "E11"},
    "notes": "타사(위드앤코) 양식. 항목 앵커 행이 세로 병합 블록의 첫 행뿐이라 5줄이 상한 — 넘치면 xlsx_rows가 늘린다. E열(견적 세부 내용)만 병합이 아니라 행마다 개별 셀이라, 앵커가 아닌 행에 남는 원본 예시 문구를 always_clear_cells로 지운다."
}'),
-- ─────────────────────────────────────────────────────────────────────────
-- 테키 — 대분류 라벨 행 + 그 아래 항목들 + 소계 행이 반복되는 구조(알파브라더스류).
--   I{r} = G{r}*H{r} (수량×단가), 블록 소계 I20/I24/I28/I33,
--   H45 = SUM(I20,I24,I28,I33) ← 블록 소계만 더한다. H46 = H45*0.1.
--   블록을 늘리면 H45가 새 소계를 못 잡으므로 _grow_template이 totals 수식을 걷어낸다.
--   D10(제작기간)은 원본에 "1.5개월 예상"이 박혀 있어 duration_text로 덮는다.
('테키', '테키 (마케팅)', '{
    "header_fields": {"quote_date_serial": "D9", "recipient_name": "B5", "duration_text": "D10"},
    "item_blocks": [
        {"category_label_cell": "E16", "rows": [17,18,19], "category_subtotal_cell": "I20"},
        {"category_label_cell": "E21", "rows": [22,23],    "category_subtotal_cell": "I24"},
        {"category_label_cell": "E25", "rows": [26,27],    "category_subtotal_cell": "I28"},
        {"category_label_cell": "E29", "rows": [30,31,32], "category_subtotal_cell": "I33"}
    ],
    "columns": {"item_name": "E", "quantity": "G", "unit_price": "H", "amount": "I"},
    "column_labels": {"item_name": "item", "quantity": "ea", "unit_price": "unit price", "amount": "amount"},
    "detail_column_order": ["quantity", "unit_price"],
    "totals": {"supply_total_cell": "H45", "vat_cell": "H46", "grand_total_cell": "H47"},
    "notes": "타사(테키) 양식. D8은 =TEXT(H45,...)&\" 원 (VAT별도)\" 수식이라 H45만 채우면 상단 총액이 따라온다."
}'),
-- ─────────────────────────────────────────────────────────────────────────
-- 다름과이음 — A~AB까지 넓게 병합된 양식. 수량이 2단(H=투입 인력, K=수량)이고
--   R{r} = N{r}*K{r}*H{r} 로 **세 값을 곱한다**. 우리 FormSpec은 단가×수량이라 그대로 두면
--   투입 인력이 1이 아닐 때 화면 금액과 발급본이 갈린다 — 그래서 항목 금액·세액 셀의 수식을
--   걷어내고(drop_formula_cells) 우리가 계산한 값을 그대로 쓴다.
('다름과이음', '다름과이음 (마케팅, 개발, 디자인)', '{
    "header_fields": {"quote_date_serial": "D6"},
    "item_blocks": [{"rows": [13,14,15,16,17,18,19,20,21,22,23,24,25,26]}],
    "columns": {"item_name": "B", "work_days": "H", "quantity": "K", "unit_price": "N",
                "supply_amount": "R", "tax_amount": "V"},
    "column_labels": {"item_name": "품명 / 규격", "work_days": "투입 인력", "quantity": "수량",
                      "unit_price": "단가", "supply_amount": "공급가액", "tax_amount": "세액"},
    "detail_column_order": ["work_days", "quantity", "unit_price"],
    "totals": {"grand_total_cell": "R9"},
    "drop_formula_cells": ["R13","R14","R15","R16","R17","R18","R19","R20","R21","R22","R23","R24","R25","R26",
                           "V13","V14","V15","V16","V17","V18","V19","V20","V21","V22","V23","V24","V25","V26"],
    "notes": "타사(다름과이음) 양식. 원본 공급가액 수식이 단가×수량×투입인력이라 항목 금액 수식을 걷어내고 값으로 쓴다."
}')
,
-- ─────────────────────────────────────────────────────────────────────────
-- 스프린트 — 항목마다 여러 행을 세로 병합한다(C23:D23, C24:D25, C26:D28) → 앵커는 3줄.
--   **단가 칸이 없다.** 금액(I)을 직접 적는 양식이라 columns에 unit_price를 두지 않는다.
--   G열(기술수준)은 병합이 아니라 행마다 개별 셀이고, 여기에 특급/고급/중급/초급이 들어간다.
--   등급 기준이 아직 없어 quote_pricing.assign_grades가 **금액 순으로 초안**만 넣고, 실무자가
--   표에서 고치면 그 값을 쓴다(2026-08-25 사용자 결정). M8:N11 / N15:O18의 등급별 단가표는
--   양식이 원래 갖고 있는 참고표라 건드리지 않는다.
--   I29 = SUM(I23:I28) → D30 → F30(VAT) → I30(총액) → E17(제안금액)까지 수식이 연쇄한다.
--
--   **H11(공급자 상호)이 "유아이 스튜디오"인 건 원본이 그런 것이고, 그대로 둔다**
--   (2026-08-25 사용자 결정). 나머지 공급자 정보는 전부 스프린트 것이다(대표 최보양,
--   542-14-01209, cs@go-sprint.co.kr, 로고 ESTIMATE SPRINT). 법인명만 '스프린트'로 등록하고
--   양식 안의 상호는 손대지 않는다 — 공급자 정보는 우리가 지어낼 값이 아니다.
--   버그로 오인해서 header_fields에 매핑하지 말 것.
('스프린트', '스프린트 (마케팅, 개발, 디자인)', '{
    "header_fields": {"quote_date_serial": "E11", "service_name": "E12", "duration_text": "E13"},
    "header_labels": {"service_name": ""},
    "item_blocks": [{"rows": [23,24,26]}],
    "always_clear_cells": ["E25","E27","E28","G25","G27","G28","H25","H27","H28"],
    "columns": {"item_name": "C", "description": "E", "grade": "G", "work_days": "H",
                "amount": "I", "note": "J"},
    "column_labels": {"item_name": "항목", "description": "주요 세부 항목", "grade": "기술수준",
                      "work_days": "기간(day)", "amount": "금 액(원)", "note": "비고"},
    "detail_column_order": ["description", "grade", "work_days"],
    "totals": {"supply_total_cell": "I29"},
    "notes": "타사(스프린트) 양식. 단가 칸이 없어 금액을 직접 적는다. E13(개발 기간)은 원본에 \"약 12주\"가 박혀 있어 duration_text로 덮는다."
}')

) as s(entity_name, sheet_name, cell_map)
join entity_templates e on e.name = s.entity_name
cross join (values ('마케팅'), ('시장검증')) as t(task_type);

-- down
delete from quote_templates
where storage_path = 'templates/comparison_forms.xlsx';
delete from entity_templates
where name in ('안르', '위드앤코', '테키', '다름과이음', '스프린트');
