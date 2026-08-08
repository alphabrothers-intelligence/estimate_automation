-- up
-- [v0.4, 2026-07-07] 이미 적용된 001~010 마이그레이션 결과를 아래 정책 변경에 맞게 보정한다:
--   1) "UXUI/디자인 제작"은 ABBG의 실제 취급 업무가 아니라 원본 파일의 예시 내용이었음 → 삭제
--   2) "고객검증"은 "시장검증"과 동일 과업의 다른 표기 → "시장검증"으로 통합
--   3) 5개 법인 모두 (마케팅/광고대행/시장검증) 3개 과업종류를 공통 취급 → 누락된 조합을 해당
--      법인의 기존 시트 레이아웃을 재사용해 채운다 (008/010 파일 자체는 이미 이 상태로 수정해둠;
--      이 마이그레이션은 이미 실행된 라이브 DB에 동일한 변경을 반영하기 위한 것)

-- 1) ABBG의 UXUI/디자인 제작 카탈로그·템플릿 삭제
delete from item_catalogs
where entity_id = (select id from entity_templates where name = 'ABBG')
  and task_type = 'UXUI/디자인 제작';

delete from quote_templates
where entity_id = (select id from entity_templates where name = 'ABBG')
  and task_type = 'UXUI/디자인 제작';

-- 2) 블렌디드랩 고객검증 → 시장검증 통합
update item_catalogs
set task_type = '시장검증'
where entity_id = (select id from entity_templates where name = '블렌디드랩')
  and task_type = '고객검증';

update quote_templates
set task_type = '시장검증'
where entity_id = (select id from entity_templates where name = '블렌디드랩')
  and task_type = '고객검증';

-- 3) 누락된 (법인×과업종류) 조합의 quote_templates 채우기 — 기존 시트 레이아웃 재사용
insert into quote_templates (entity_id, task_type, module_name, storage_path, sheet_name, cell_map) values
(
    (select id from entity_templates where name = '테스티파이'), '광고대행', null,
    'templates/testify.xlsx', '시장검증',
    '{
        "header_fields": {"quote_year": "B4", "quote_month": "C4", "quote_day": "D4", "recipient_name": "B6", "service_name": "B12"},
        "item_blocks": [
            {"category_label_cell": "A15", "category_subtotal_cell": "H15", "rows": [16, 17, 18, 19, 20]},
            {"category_label_cell": "A21", "category_subtotal_cell": "H21", "rows": [22, 23, 24, 25]}
        ],
        "columns": {"item_name": "A", "unit_price": "E", "work_days": "F", "quantity": "G", "supply_amount": "H", "note": "J"},
        "totals": {"subtotal_cell": "H26", "vat_cell": "H27", "grand_total_cell": "H28", "top_display_cell": "H10"},
        "notes": "[v0.4] 5개 법인 공통 3개 과업종류 정책에 따라 추가 — 실제 발급 이력이 없어 시장검증 시트 레이아웃을 재사용."
    }'::jsonb
),
(
    (select id from entity_templates where name = '알파브라더스'), '마케팅', null,
    'templates/alphabrothers.xlsx', '시장성테스트',
    '{
        "header_fields": {"quote_code": "AB3", "quote_date": "D4", "client_name": "D5", "client_contact": "D6", "client_phone": "D7", "client_email": "D8"},
        "item_blocks": [{"category_large_cell": "A13", "category_mid_cell": "C13", "rows": [13, 14, 15, 16, 17]}],
        "columns": {"item_name": "E", "description": "I", "work_days": "T", "quantity": "V", "unit_price": "X", "supply_amount": "AA"},
        "totals": {"top_display_cell": "G10", "vat_cell": "E18", "supply_total_cell": "T18"},
        "notes": "[v0.4] 실제 발급 이력 없어 시장성테스트 시트 레이아웃 재사용."
    }'::jsonb
),
(
    (select id from entity_templates where name = '알파브라더스'), '광고대행', null,
    'templates/alphabrothers.xlsx', '시장성테스트',
    '{
        "header_fields": {"quote_code": "AB3", "quote_date": "D4", "client_name": "D5", "client_contact": "D6", "client_phone": "D7", "client_email": "D8"},
        "item_blocks": [{"category_large_cell": "A13", "category_mid_cell": "C13", "rows": [13, 14, 15, 16, 17]}],
        "columns": {"item_name": "E", "description": "I", "work_days": "T", "quantity": "V", "unit_price": "X", "supply_amount": "AA"},
        "totals": {"top_display_cell": "G10", "vat_cell": "E18", "supply_total_cell": "T18"},
        "notes": "[v0.4] 실제 발급 이력 없어 시장성테스트 시트 레이아웃 재사용."
    }'::jsonb
),
(
    (select id from entity_templates where name = '썬데이워커'), '광고대행', null,
    'templates/sundaywalker.xlsx', '견적서',
    '{
        "header_fields": {"client_name": "B4", "quote_date": "D6", "validity_text": "D7"},
        "item_blocks": [
            {"rows": [13, 14, 15, 16, 17, 18]},
            {"rows": [20, 21, 22], "role": "labor_fte"}
        ],
        "columns": {"item_name": "B", "input_mm": "H", "quantity": "K", "unit_price": "N", "supply_amount": "R", "tax_amount": "V"},
        "totals": {"top_display_cell": "R9", "grand_total_row": 35},
        "notes": "[v0.4] 5개 법인 공통 3개 과업종류 정책에 따라 추가 — 시장검증과 동일 템플릿 재사용."
    }'::jsonb
),
(
    (select id from entity_templates where name = 'ABBG'), '마케팅', null,
    'templates/abbg.xlsx', '견적서',
    '{
        "header_fields": {"quote_date": "D3", "client_company": "D4", "client_contact": "D5", "client_phone": "D6", "client_email": "D7"},
        "item_blocks": [{"rows": [10, 11, 12, 13, 14, 15, 16, 17]}],
        "columns": {"item_name": "A", "description": "I", "work_days": "T", "quantity": "V", "unit_price": "X", "supply_amount": "AA"},
        "totals": {"vat_cell": "G18", "supply_total_cell": "V18", "grand_total_cell": "G19"},
        "notes": "확보된 원본이 값이 채워지지 않은 빈 마스터(단가=0)라 그대로 블랭크 템플릿으로 사용 가능. 원래 UXUI/디자인 예시였으나 실제로는 5개 법인 공통 과업(마케팅/광고대행/시장검증)에 사용."
    }'::jsonb
),
(
    (select id from entity_templates where name = 'ABBG'), '광고대행', null,
    'templates/abbg.xlsx', '견적서',
    '{
        "header_fields": {"quote_date": "D3", "client_company": "D4", "client_contact": "D5", "client_phone": "D6", "client_email": "D7"},
        "item_blocks": [{"rows": [10, 11, 12, 13, 14, 15, 16, 17]}],
        "columns": {"item_name": "A", "description": "I", "work_days": "T", "quantity": "V", "unit_price": "X", "supply_amount": "AA"},
        "totals": {"vat_cell": "G18", "supply_total_cell": "V18", "grand_total_cell": "G19"},
        "notes": "마케팅과 동일 템플릿 재사용."
    }'::jsonb
),
(
    (select id from entity_templates where name = 'ABBG'), '시장검증', null,
    'templates/abbg.xlsx', '견적서',
    '{
        "header_fields": {"quote_date": "D3", "client_company": "D4", "client_contact": "D5", "client_phone": "D6", "client_email": "D7"},
        "item_blocks": [{"rows": [10, 11, 12, 13, 14, 15, 16, 17]}],
        "columns": {"item_name": "A", "description": "I", "work_days": "T", "quantity": "V", "unit_price": "X", "supply_amount": "AA"},
        "totals": {"vat_cell": "G18", "supply_total_cell": "V18", "grand_total_cell": "G19"},
        "notes": "마케팅과 동일 템플릿 재사용."
    }'::jsonb
);

-- down
-- 데이터 정정(잘못된 UXUI 예시 데이터 폐기)이 포함되어 있어 완전한 역방향은 의미가 없다.
-- 구조적으로 추가한 항목만 되돌린다.
delete from quote_templates
where module_name is null
  and (
    (entity_id = (select id from entity_templates where name = '테스티파이') and task_type = '광고대행')
    or (entity_id = (select id from entity_templates where name = '알파브라더스') and task_type in ('마케팅', '광고대행'))
    or (entity_id = (select id from entity_templates where name = '썬데이워커') and task_type = '광고대행')
    or (entity_id = (select id from entity_templates where name = 'ABBG') and task_type in ('마케팅', '광고대행', '시장검증'))
  );

update quote_templates
set task_type = '고객검증'
where entity_id = (select id from entity_templates where name = '블렌디드랩')
  and task_type = '시장검증';

update item_catalogs
set task_type = '고객검증'
where entity_id = (select id from entity_templates where name = '블렌디드랩')
  and task_type = '시장검증';
