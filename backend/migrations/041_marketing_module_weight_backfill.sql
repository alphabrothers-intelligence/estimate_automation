-- up
-- 040에서 테스티파이 마케팅의 런칭마케팅/그로스해킹/퍼포먼스 3개 모듈에만 module_weight를
-- 채웠는데, 실제 견적 세트(우유곳간 마케팅, 2026-08-20)에서 여기에 "광고형 마케팅 대행"과
-- "자사몰 데이터 세팅"을 함께 선택하니 5개 모듈이 30,000,000÷5=6,000,000씩 완전 균등
-- 분배됐다 — allocation_service._split_amount_weighted는 그룹 하나라도 weight가 없으면
-- 전체를 균등분배로 폴백하기 때문(2026-08-20 실사용 재현). 테스티파이 마케팅 카탈로그의
-- 나머지 6개 모듈도 실제 발급 견적서 근거로 채운다:
--   - 온라인 광고 8,000,000 / SEO 마케팅 2,200,000 / 자사몰 데이터 세팅 3,000,000
--     : data/02. (테스티파이) 우유곳간 마케팅 견적서_260709.xlsx "마케팅" 시트
--       (그로스해킹 마케팅 대행 용역, 합계 18,000,000 중 각 모듈 소계)
--   - 광고형 마케팅 대행 15,000,000
--     : data/02. (테스티파이) 미구 마케팅 대행 견적서_260211.pdf (합계 15,000,000)
--   - 카카오 톡스토어 광고 대행 3,500,000
--     : data/02. (테스티파이) 우유곳간 마케팅 견적서_260709.xlsx "마케팅 (2)" 시트 (합계 3,500,000)
--   - 네이버 쇼핑 광고 대행 3,500,000
--     : 실제 샘플 없음 — 027 마이그레이션에서 카카오 톡스토어와 동일 비중으로 반영한 기존
--       결정을 그대로 따름(사용자 2026-08-08 결정)
-- 썬데이워커는 이 카탈로그를 물리적으로 복제해 갖고 있어(shared_source_entity_id=테스티파이,
-- 027 참고) 같은 값을 별도로 채워야 한다. 알파브라더스/ABBG는 마케팅 실카탈로그가 없어
-- 테스티파이를 그대로 폴백 차용하므로 이 변경만으로 함께 반영된다.
update item_catalogs set module_weight = 8000000
where task_type = '마케팅' and module_name = '온라인 광고'
  and entity_id in (select id from entity_templates where name in ('테스티파이', '썬데이워커'));

update item_catalogs set module_weight = 2200000
where task_type = '마케팅' and module_name = 'SEO 마케팅'
  and entity_id in (select id from entity_templates where name in ('테스티파이', '썬데이워커'));

update item_catalogs set module_weight = 3000000
where task_type = '마케팅' and module_name = '자사몰 데이터 세팅'
  and entity_id in (select id from entity_templates where name in ('테스티파이', '썬데이워커'));

update item_catalogs set module_weight = 15000000
where task_type = '마케팅' and module_name = '광고형 마케팅 대행'
  and entity_id in (select id from entity_templates where name in ('테스티파이', '썬데이워커'));

update item_catalogs set module_weight = 3500000
where task_type = '마케팅' and module_name = '카카오 톡스토어 광고 대행'
  and entity_id in (select id from entity_templates where name in ('테스티파이', '썬데이워커'));

update item_catalogs set module_weight = 3500000
where task_type = '마케팅' and module_name = '네이버 쇼핑 광고 대행'
  and entity_id in (select id from entity_templates where name in ('테스티파이', '썬데이워커'));

-- down
update item_catalogs set module_weight = null
where task_type = '마케팅'
  and module_name in ('온라인 광고', 'SEO 마케팅', '자사몰 데이터 세팅', '광고형 마케팅 대행', '카카오 톡스토어 광고 대행', '네이버 쇼핑 광고 대행')
  and entity_id in (select id from entity_templates where name in ('테스티파이', '썬데이워커'));
