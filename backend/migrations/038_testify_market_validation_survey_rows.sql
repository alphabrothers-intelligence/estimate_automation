-- up
-- 사용자가 templates/testify.xlsx '시장검증' 시트의 "설문형 시장검증" 블록을 4행(22~25)에서
-- 21행(22~42)으로 직접 늘린 새 원본 파일을 제공함(2026-08-17, "행추가 예시" 파일). 세부 항목이
-- 5개 이상이라 소계로 접혀야 했던 케이스(PMF Survey 등)를 이제 세부 항목 그대로 담을 수 있다.
-- 파일을 열어 직접 확인: 블록 라벨/소계 셀 위치(A21/H21)는 그대로, 아래 합계(H43)·부가세(H44)·
-- 총합계(H45) 셀만 행이 밀린 만큼 이동. '광고대행' task_type도 같은 시트를 재사용하므로 함께 갱신.
update quote_templates
set cell_map = jsonb_set(
    jsonb_set(cell_map, '{item_blocks}', '[
        {"category_label_cell": "A15", "category_subtotal_cell": "H15", "rows": [16, 17, 18, 19, 20]},
        {"category_label_cell": "A21", "category_subtotal_cell": "H21", "rows": [22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42]}
    ]'::jsonb),
    '{totals}',
    '{"subtotal_cell": "H43", "vat_cell": "H44", "grand_total_cell": "H45", "top_display_cell": "H10"}'::jsonb
)
where entity_id = (select id from entity_templates where name = '테스티파이')
  and sheet_name = '시장검증';

-- down
update quote_templates
set cell_map = jsonb_set(
    jsonb_set(cell_map, '{item_blocks}', '[
        {"category_label_cell": "A15", "category_subtotal_cell": "H15", "rows": [16, 17, 18, 19, 20]},
        {"category_label_cell": "A21", "category_subtotal_cell": "H21", "rows": [22, 23, 24, 25]}
    ]'::jsonb),
    '{totals}',
    '{"subtotal_cell": "H26", "vat_cell": "H27", "grand_total_cell": "H28", "top_display_cell": "H10"}'::jsonb
)
where entity_id = (select id from entity_templates where name = '테스티파이')
  and sheet_name = '시장검증';
