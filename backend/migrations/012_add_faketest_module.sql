-- up
-- 테스티파이 시장검증 "시장성 테스트" 모듈의 Fake-door test 변형을 별도 모듈로 추가한다.
-- 실제 발급 샘플: 단아한화식, 2026-01-30, 공급가액 합계 7,320,000원, 총 합계 8,052,000원(VAT포함).
insert into item_catalogs (entity_id, task_type, module_name, is_required, item_name, historical_ratio, sort_order) values
((select id from entity_templates where name = '테스티파이'), '시장검증', '시장성 테스트 (Fake-door형)', false, 'BM 진단 및 고도화',      6.83,  1),
((select id from entity_templates where name = '테스티파이'), '시장검증', '시장성 테스트 (Fake-door형)', false, 'MVP 광고안 기획',        34.15, 2),
((select id from entity_templates where name = '테스티파이'), '시장검증', '시장성 테스트 (Fake-door형)', false, 'Meta 광고 세팅 및 운영', 49.45, 3),
((select id from entity_templates where name = '테스티파이'), '시장검증', '시장성 테스트 (Fake-door형)', false, '결과 리포트 제공',       9.56,  4);

-- down
delete from item_catalogs
where entity_id = (select id from entity_templates where name = '테스티파이')
  and task_type = '시장검증'
  and module_name = '시장성 테스트 (Fake-door형)';
