-- up
-- cell_map 공통 구조:
-- {
--   "header_fields": { 논리필드명: "셀좌표" },      -- 수신자/견적일자 등 건별 가변값
--   "item_blocks": [ { "category_label_cell"?, "category_subtotal_cell"?, "rows": [행번호,...] } ],
--   "columns": { 논리컬럼명: "열문자" },            -- item_blocks의 각 행에 적용되는 컬럼 좌표
--   "totals": { 논리필드명: "셀좌표" },
--   "notes": "특이사항 (자유텍스트 셀, 수식 등)"
-- }
-- 각 파일은 backend/templates/*.xlsx(또는 .xls) 원본 그대로이며, Phase 5에서 openpyxl로
-- item_blocks가 가리키는 행 + header_fields만 채우고 나머지(고정정보/문구/로고/도장/수식)는 건드리지 않는다.
--
-- [v0.4] "고객검증"은 "시장검증"과 실제로 동일 과업이며 견적서마다 명칭만 다르게 표기된 것으로
-- 확인되어(2026-07-07) 별도 task_type으로 두지 않고 "시장검증"으로 통합했다. 알파브라더스의
-- "시장성 테스트" 모듈명도 같은 개념(시장검증)의 회사별 표기 차이일 뿐이라 module_name은 그대로 두되
-- task_type='시장검증' 하나로 묶는다. "UXUI/디자인 제작"도 삭제했다 (008 참고).
-- 5개 법인 모두 마케팅/광고대행/시장검증 3개 과업종류를 공통 취급하므로, 실제 발급 이력이 없는
-- 조합은 해당 법인의 기존 시트 레이아웃을 그대로 재사용해 채운다.

-- ============================================================
-- 테스티파이 (backend/templates/testify.xlsx)
-- ============================================================
insert into quote_templates (entity_id, task_type, module_name, storage_path, sheet_name, cell_map) values
(
    (select id from entity_templates where name = '테스티파이'), '시장검증', null,
    'templates/testify.xlsx', '시장검증',
    '{
        "header_fields": {"quote_year": "B4", "quote_month": "C4", "quote_day": "D4", "recipient_name": "B6", "service_name": "B12"},
        "item_blocks": [
            {"category_label_cell": "A15", "category_subtotal_cell": "H15", "rows": [16, 17, 18, 19, 20]},
            {"category_label_cell": "A21", "category_subtotal_cell": "H21", "rows": [22, 23, 24, 25]}
        ],
        "columns": {"item_name": "A", "unit_price": "E", "work_days": "F", "quantity": "G", "supply_amount": "H", "note": "J"},
        "totals": {"subtotal_cell": "H26", "vat_cell": "H27", "grand_total_cell": "H28", "top_display_cell": "H10"},
        "notes": "공급가액(H열)은 대부분 =단가*작업일*수량 수식. 항목 행 개수는 모듈당 고정(5+4)이라 카탈로그 옵션모듈 선택에 따라 rows 범위를 좁혀 씀."
    }'::jsonb
),
(
    (select id from entity_templates where name = '테스티파이'), '마케팅', null,
    'templates/testify.xlsx', '마케팅',
    '{
        "header_fields": {"quote_year": "B4", "quote_month": "C4", "quote_day": "D4", "recipient_name": "B6", "service_name": "B12"},
        "item_blocks": [
            {"category_label_cell": "A15", "category_subtotal_cell": "H15", "rows": [16, 17, 18, 19]},
            {"category_label_cell": "A20", "category_subtotal_cell": "H20", "rows": [21, 22, 23]},
            {"category_label_cell": "A24", "category_subtotal_cell": "H24", "rows": [25, 26, 27]},
            {"category_label_cell": "A28", "category_subtotal_cell": "H28", "rows": [29, 30]}
        ],
        "columns": {"item_name": "A", "unit_price": "E", "work_days": "F", "quantity": "G", "supply_amount": "H", "note": "J"},
        "totals": {"subtotal_cell": "H31", "vat_cell": "H32", "grand_total_cell": "H33", "top_display_cell": "H10"},
        "notes": "시장검증 시트와 헤더 좌표는 동일, 카테고리 블록 구성(4개)만 다름."
    }'::jsonb
),
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
        "notes": "[v0.4] 5개 법인 공통 3개 과업종류 정책에 따라 추가 — 실제 발급 이력이 없어 시장검증 시트 레이아웃을 재사용 (PRD 부록 B)."
    }'::jsonb
);

-- ============================================================
-- 블렌디드랩 (backend/templates/blendedlab.xls) — 마케팅/광고대행/시장검증 공용 (동일 시트 재사용)
-- ============================================================
insert into quote_templates (entity_id, task_type, module_name, storage_path, sheet_name, cell_map) values
(
    (select id from entity_templates where name = '블렌디드랩'), '마케팅', null,
    'templates/blendedlab.xls', '견적서 (2)',
    '{
        "header_fields": {"recipient_block": "B6"},
        "item_blocks": [{"rows": [13, 14, 15]}],
        "columns": {"item_name": "B", "work_days": "O", "quantity": "S", "unit_price": "W", "amount": "AB"},
        "totals": {"grand_total_cell": "AB17"},
        "notes": "B6 한 셀에 \"수신자 : {고객사}\\n\\n아래와 같이 견적서를 발송합니다.\\n\\n{YYYY}년 {M}월 {D}일\"이 자유텍스트로 합쳐져 있어 문자열 템플릿으로 채워야 함. 항목행은 부가세 별도 금액이며 합계금액(AB17)에서 ×1.1 계산. 구형 .xls 포맷이라 openpyxl로 직접 열 수 없음 — Phase 5 전에 .xlsx로 1회 변환 필요."
    }'::jsonb
),
(
    (select id from entity_templates where name = '블렌디드랩'), '광고대행', null,
    'templates/blendedlab.xls', '견적서 (2)',
    '{
        "header_fields": {"recipient_block": "B6"},
        "item_blocks": [{"rows": [13, 14, 15]}],
        "columns": {"item_name": "B", "work_days": "O", "quantity": "S", "unit_price": "W", "amount": "AB"},
        "totals": {"grand_total_cell": "AB17"},
        "notes": "마케팅과 동일 템플릿 재사용 (표본 1건, 단일 항목형 — PRD 8장 질문 5)."
    }'::jsonb
),
(
    (select id from entity_templates where name = '블렌디드랩'), '시장검증', null,
    'templates/blendedlab.xls', '견적서 (2)',
    '{
        "header_fields": {"recipient_block": "B6"},
        "item_blocks": [{"rows": [13, 14, 15]}],
        "columns": {"item_name": "B", "work_days": "O", "quantity": "S", "unit_price": "W", "amount": "AB"},
        "totals": {"grand_total_cell": "AB17"},
        "notes": "[v0.4] 기존 고객검증에서 명칭 통합 — 마케팅과 동일 템플릿 재사용."
    }'::jsonb
);

-- ============================================================
-- 알파브라더스 (backend/templates/alphabrothers.xlsx) — 모듈별로 시트가 다름, 좌표는 공통
-- ============================================================
insert into quote_templates (entity_id, task_type, module_name, storage_path, sheet_name, cell_map) values
(
    (select id from entity_templates where name = '알파브라더스'), '시장검증', 'FGI',
    'templates/alphabrothers.xlsx', 'FGI',
    '{
        "header_fields": {"quote_code": "AB3", "quote_date": "D4", "client_name": "D5", "client_contact": "D6", "client_phone": "D7", "client_email": "D8"},
        "item_blocks": [{"category_large_cell": "A13", "category_mid_cell": "C13", "rows": [13, 14, 15, 16, 17]}],
        "columns": {"item_name": "E", "description": "I", "work_days": "T", "quantity": "V", "unit_price": "X", "supply_amount": "AA"},
        "totals": {"top_display_cell": "G10", "vat_cell": "E18", "supply_total_cell": "T18"},
        "notes": "구분(대)/구분(중)은 병합셀이라 블록당 1회만 세팅."
    }'::jsonb
),
(
    (select id from entity_templates where name = '알파브라더스'), '시장검증', '사용성 테스트',
    'templates/alphabrothers.xlsx', '사용성테스트',
    '{
        "header_fields": {"quote_code": "AB3", "quote_date": "D4", "client_name": "D5", "client_contact": "D6", "client_phone": "D7", "client_email": "D8"},
        "item_blocks": [{"category_large_cell": "A13", "category_mid_cell": "C13", "rows": [13, 14, 15, 16, 17]}],
        "columns": {"item_name": "E", "description": "I", "work_days": "T", "quantity": "V", "unit_price": "X", "supply_amount": "AA"},
        "totals": {"top_display_cell": "G10", "vat_cell": "E18", "supply_total_cell": "T18"},
        "notes": "FGI 시트와 좌표 동일."
    }'::jsonb
),
(
    (select id from entity_templates where name = '알파브라더스'), '시장검증', '기술성 테스트',
    'templates/alphabrothers.xlsx', '기술성테스트',
    '{
        "header_fields": {"quote_code": "AB3", "quote_date": "D4", "client_name": "D5", "client_contact": "D6", "client_phone": "D7", "client_email": "D8"},
        "item_blocks": [{"category_large_cell": "A13", "category_mid_cell": "C13", "rows": [13, 14, 15, 16, 17]}],
        "columns": {"item_name": "E", "description": "I", "work_days": "T", "quantity": "V", "unit_price": "X", "supply_amount": "AA"},
        "totals": {"top_display_cell": "G10", "vat_cell": "E18", "supply_total_cell": "T18"},
        "notes": "FGI 시트와 좌표 동일."
    }'::jsonb
),
(
    (select id from entity_templates where name = '알파브라더스'), '시장검증', '시장성 테스트',
    'templates/alphabrothers.xlsx', '시장성테스트',
    '{
        "header_fields": {"quote_code": "AB3", "quote_date": "D4", "client_name": "D5", "client_contact": "D6", "client_phone": "D7", "client_email": "D8"},
        "item_blocks": [{"category_large_cell": "A13", "category_mid_cell": "C13", "rows": [13, 14, 15, 16, 17]}],
        "columns": {"item_name": "E", "description": "I", "work_days": "T", "quantity": "V", "unit_price": "X", "supply_amount": "AA"},
        "totals": {"top_display_cell": "G10", "vat_cell": "E18", "supply_total_cell": "T18"},
        "notes": "실제 발급 샘플(어니티, 2024.7.24) 원본 그대로. [v0.4] 이 시장성 테스트 모듈명 자체가 테스티파이/블렌디드랩이 말하는 시장검증과 같은 개념의 알파브라더스식 표기."
    }'::jsonb
),
(
    (select id from entity_templates where name = '알파브라더스'), '시장검증', '통합 패키지',
    'templates/alphabrothers.xlsx', '견적서',
    '{
        "header_fields": {"quote_code": "AB3", "quote_date": "D4", "client_name": "D5", "client_contact": "D6", "client_phone": "D7", "client_email": "D8"},
        "item_blocks": [{"category_large_cell": "A13", "category_mid_cell": "C13", "rows": [13, 14, 15, 16, 17]}],
        "columns": {"item_name": "E", "description": "I", "work_days": "T", "quantity": "V", "unit_price": "X", "supply_amount": "AA"},
        "totals": {"top_display_cell": "G10", "vat_cell": "E18", "supply_total_cell": "T18"},
        "notes": "이 시트가 4개 모듈 번들(통합 패키지) 본체. 공급가액 수식이 다른 모듈 시트와 달리 =V*X (작업일 미반영)."
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
        "notes": "[v0.4] 5개 법인 공통 3개 과업종류 정책에 따라 추가 — 실제 발급 이력 없어 시장성테스트 시트 레이아웃 재사용."
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
);

-- ============================================================
-- 썬데이워커 (backend/templates/sundaywalker.xlsx) — 시장검증/마케팅/광고대행 공용 (동일 시트, PRD 6.6)
-- ============================================================
insert into quote_templates (entity_id, task_type, module_name, storage_path, sheet_name, cell_map) values
(
    (select id from entity_templates where name = '썬데이워커'), '시장검증', null,
    'templates/sundaywalker.xlsx', '견적서',
    '{
        "header_fields": {"client_name": "B4", "quote_date": "D6", "validity_text": "D7"},
        "item_blocks": [
            {"rows": [13, 14, 15, 16, 17, 18]},
            {"rows": [20, 21, 22], "role": "labor_fte"}
        ],
        "columns": {"item_name": "B", "input_mm": "H", "quantity": "K", "unit_price": "N", "supply_amount": "R", "tax_amount": "V"},
        "totals": {"top_display_cell": "R9", "grand_total_row": 35},
        "notes": "인건비 3행(20~22)은 수량이 FTE %문자열(예: \"40(%)\")이고 공급가액 수식도 =단가*투입MM*FTE% 형태로 달라 별도 role로 구분. DC 조정값은 B24 셀에 \"DC : {금액}\" 형태 자유텍스트로 들어있어 문자열 포맷으로 갱신. 세액(V열)은 대부분 =공급가액*0.1 수식."
    }'::jsonb
),
(
    (select id from entity_templates where name = '썬데이워커'), '마케팅', null,
    'templates/sundaywalker.xlsx', '견적서',
    '{
        "header_fields": {"client_name": "B4", "quote_date": "D6", "validity_text": "D7"},
        "item_blocks": [
            {"rows": [13, 14, 15, 16, 17, 18]},
            {"rows": [20, 21, 22], "role": "labor_fte"}
        ],
        "columns": {"item_name": "B", "input_mm": "H", "quantity": "K", "unit_price": "N", "supply_amount": "R", "tax_amount": "V"},
        "totals": {"top_display_cell": "R9", "grand_total_row": 35},
        "notes": "시장검증과 동일 템플릿 재사용 (PRD 6.6 — 항목 내용만 6.1/6.2 카탈로그에서 채움)."
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
);

-- ============================================================
-- ABBG (backend/templates/abbg.xlsx) — [v0.4] "UXUI/디자인 제작" 대신 마케팅/광고대행/시장검증 공용
-- ============================================================
insert into quote_templates (entity_id, task_type, module_name, storage_path, sheet_name, cell_map) values
(
    (select id from entity_templates where name = 'ABBG'), '마케팅', null,
    'templates/abbg.xlsx', '견적서',
    '{
        "header_fields": {"quote_date": "D3", "client_company": "D4", "client_contact": "D5", "client_phone": "D6", "client_email": "D7"},
        "item_blocks": [{"rows": [10, 11, 12, 13, 14, 15, 16, 17]}],
        "columns": {"item_name": "A", "description": "I", "work_days": "T", "quantity": "V", "unit_price": "X", "supply_amount": "AA"},
        "totals": {"vat_cell": "G18", "supply_total_cell": "V18", "grand_total_cell": "G19"},
        "notes": "확보된 원본이 값이 채워지지 않은 빈 마스터(단가=0)라 다른 파일과 달리 그대로 블랭크 템플릿으로 사용 가능. 원래 UXUI/디자인 예시였으나 실제로는 5개 법인 공통 과업(마케팅/광고대행/시장검증)에 사용."
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
delete from quote_templates;
