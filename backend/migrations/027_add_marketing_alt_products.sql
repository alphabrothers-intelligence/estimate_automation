-- up
-- 테스티파이 마케팅: 기존 4모듈("그로스해킹 마케팅 대행 용역" 번들)은 상호 배타적인 대안
-- 상품군 중 하나였을 뿐인데 지금까지 alt_group이 없어 항상 유일한 선택지였다. 실제 발급
-- 샘플 2건을 추가 확보해(2026-08-08) 서로 다른 상품임을 확인했으므로 alt_group으로 분리한다:
--   - 카카오 톡스토어 광고 대행: 우유곳간 마케팅 견적서_260709.xlsx 실제 발급본
--     (전략 기획 1,000,000 / 광고 운영 2,000,000 / 결과 보고 500,000, 합계 3,500,000)
--   - 네이버 쇼핑 광고 대행: 실제 샘플 없음 — 사용자 지시로 카카오 톡스토어와 동일한
--     항목 구성·비중을 그대로 반영 (2026-08-08 사용자 결정)
-- work_days/quantity는 우유곳간 샘플에서 전부 1/1로 확인되어 테이블 기본값과 같으므로
-- 별도로 지정하지 않는다.
update item_catalogs set alt_group = '그로스해킹형'
where task_type = '마케팅' and module_name in ('온라인 광고', 'SEO 마케팅', '자사몰 데이터 세팅', '그로스해킹')
  and entity_id = (select id from entity_templates where name = '테스티파이');

insert into item_catalogs (entity_id, task_type, module_name, is_required, item_name, historical_ratio, alt_group, sort_order) values
((select id from entity_templates where name = '테스티파이'), '마케팅', '카카오 톡스토어 광고 대행', false, '전략 기획', 28.57, '카카오톡스토어형', 1),
((select id from entity_templates where name = '테스티파이'), '마케팅', '카카오 톡스토어 광고 대행', false, '광고 운영',   57.14, '카카오톡스토어형', 2),
((select id from entity_templates where name = '테스티파이'), '마케팅', '카카오 톡스토어 광고 대행', false, '결과 보고',   14.29, '카카오톡스토어형', 3),
((select id from entity_templates where name = '테스티파이'), '마케팅', '네이버 쇼핑 광고 대행', false, '전략 기획', 28.57, '네이버쇼핑형', 1),
((select id from entity_templates where name = '테스티파이'), '마케팅', '네이버 쇼핑 광고 대행', false, '광고 운영',   57.14, '네이버쇼핑형', 2),
((select id from entity_templates where name = '테스티파이'), '마케팅', '네이버 쇼핑 광고 대행', false, '결과 보고',   14.29, '네이버쇼핑형', 3);

-- 썬데이워커는 PRD 6.6 원칙대로 테스티파이 마케팅 카탈로그를 그대로 미러링한다(008 참고) —
-- 기존 4모듈에도 동일하게 alt_group을 부여하고, 신규 2종도 동일하게 복제한다.
update item_catalogs set alt_group = '그로스해킹형'
where task_type = '마케팅' and module_name in ('온라인 광고', 'SEO 마케팅', '자사몰 데이터 세팅', '그로스해킹')
  and entity_id = (select id from entity_templates where name = '썬데이워커');

insert into item_catalogs (entity_id, task_type, module_name, is_required, item_name, historical_ratio, alt_group, shared_source_entity_id, sort_order) values
((select id from entity_templates where name = '썬데이워커'), '마케팅', '카카오 톡스토어 광고 대행', false, '전략 기획', 28.57, '카카오톡스토어형', (select id from entity_templates where name = '테스티파이'), 1),
((select id from entity_templates where name = '썬데이워커'), '마케팅', '카카오 톡스토어 광고 대행', false, '광고 운영',   57.14, '카카오톡스토어형', (select id from entity_templates where name = '테스티파이'), 2),
((select id from entity_templates where name = '썬데이워커'), '마케팅', '카카오 톡스토어 광고 대행', false, '결과 보고',   14.29, '카카오톡스토어형', (select id from entity_templates where name = '테스티파이'), 3),
((select id from entity_templates where name = '썬데이워커'), '마케팅', '네이버 쇼핑 광고 대행', false, '전략 기획', 28.57, '네이버쇼핑형', (select id from entity_templates where name = '테스티파이'), 1),
((select id from entity_templates where name = '썬데이워커'), '마케팅', '네이버 쇼핑 광고 대행', false, '광고 운영',   57.14, '네이버쇼핑형', (select id from entity_templates where name = '테스티파이'), 2),
((select id from entity_templates where name = '썬데이워커'), '마케팅', '네이버 쇼핑 광고 대행', false, '결과 보고',   14.29, '네이버쇼핑형', (select id from entity_templates where name = '테스티파이'), 3);

-- 알파브라더스/ABBG는 마케팅 실카탈로그가 없어 테스티파이 카탈로그를 폴백 차용하므로
-- (catalog_service.FALLBACK_SOURCE_BY_TASK_TYPE) 별도 insert 없이도 위 변경이 그대로 적용된다.

-- down
delete from item_catalogs
where task_type = '마케팅' and module_name in ('카카오 톡스토어 광고 대행', '네이버 쇼핑 광고 대행');

update item_catalogs set alt_group = null
where task_type = '마케팅' and module_name in ('온라인 광고', 'SEO 마케팅', '자사몰 데이터 세팅', '그로스해킹');
