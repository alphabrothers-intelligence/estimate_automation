-- up
-- 사용자 결정(2026-08-10): "그로스해킹형"(온라인 광고/SEO 마케팅/자사몰 데이터 세팅/그로스해킹
-- 4개 모듈)이 alt_group으로 묶여 있어(027 마이그레이션) PM이 이 4개를 통째로만 고를 수 있고
-- 개별적으로 뜯어 고를 수 없었다 — 사용자가 "온라인 광고만 필요하고 SEO는 필요없는" 등 세부
-- 조합을 못 고른다고 지적함. 실제 테스티파이 마케팅 원본 시트를 다시 보니 카테고리 라벨
-- 칸이 정확히 4개(A15/A20/A24/A28)라 이 4개가 원래도 각각 독립된 칸에 들어가도록 만들어진
-- 양식이었음을 확인했다 — 개별 선택해도 양식이 깨지지 않는다.
--
-- "광고형/네이버쇼핑형/카카오톡스토어형"(대행 상품 3종)은 그대로 택1 유지한다(사용자 결정) —
-- 실제 발급 샘플로 상호 배타 관계가 확인된 별도 상품이라 그로스해킹형과는 성격이 다르다.
update item_catalogs set alt_group = null, is_required = false
where task_type = '마케팅'
  and module_name in ('온라인 광고', 'SEO 마케팅', '자사몰 데이터 세팅', '그로스해킹')
  and alt_group = '그로스해킹형';

-- down
update item_catalogs set alt_group = '그로스해킹형', is_required = true
where task_type = '마케팅'
  and module_name in ('온라인 광고', 'SEO 마케팅', '자사몰 데이터 세팅', '그로스해킹')
  and alt_group is null;
