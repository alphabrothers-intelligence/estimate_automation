-- up
-- 썬데이워커 마스터 원본(B24)에 예전 실제 고객의 "DC : {금액}" 조정값이 자유텍스트로 남아있다.
-- 우리 데이터 모델엔 DC(할인) 개념이 없어 채울 값이 없으므로, 발급할 때마다 항상 빈 값으로
-- 지운다(사용자 확인, 2026-07-08 — 인건비 블록과 같은 이유로 "그냥 제거").
update quote_templates
set cell_map = jsonb_set(cell_map, '{always_clear_cells}', '["B24"]'::jsonb)
where entity_id = (select id from entity_templates where name = '썬데이워커');

-- down
update quote_templates
set cell_map = cell_map - 'always_clear_cells'
where entity_id = (select id from entity_templates where name = '썬데이워커');