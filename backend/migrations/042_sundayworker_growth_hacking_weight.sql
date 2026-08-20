-- up
-- 041에서 놓친 부분: 썬데이워커의 "그로스해킹" 모듈(주간 단위 데이터 분석 / 주간 단위
-- 액션플랜 수행, mid_category 없음)은 테스티파이의 새 "그로스해킹"(주간 Wrap-Up 등,
-- mid_category='주간단위 그로스해킹', 040에서 12,800,000으로 채움)과 이름만 같을 뿐
-- 다른 구버전 모듈이라 041의 조건(module_name='그로스해킹')에서 테스티파이 값과 섞일까봐
-- 제외했었다. 이 구버전은 historical_ratio도 원래 비어 있었다 — data/02. (테스티파이)
-- 우유곳간 마케팅 견적서_260709.xlsx "마케팅" 시트의 "그로스해킹" 소계(주간단위 데이터
-- 분석 2,400,000 + 주간단위 액션플랜 수행 2,400,000 = 4,800,000, 50:50)로 채운다.
update item_catalogs set module_weight = 4800000, historical_ratio = 50.000
where task_type = '마케팅' and module_name = '그로스해킹' and mid_category is null
  and entity_id = (select id from entity_templates where name = '썬데이워커');

-- down
update item_catalogs set module_weight = null, historical_ratio = null
where task_type = '마케팅' and module_name = '그로스해킹' and mid_category is null
  and entity_id = (select id from entity_templates where name = '썬데이워커');
