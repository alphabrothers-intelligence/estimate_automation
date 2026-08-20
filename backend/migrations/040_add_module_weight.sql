-- up
-- 사용자 결정(2026-08-19): 여러 모듈(구분(대))을 조합한 견적은 지금까지 총액을 모듈 수만큼
-- 균등분배했다(allocation_service._split_amount_evenly, 2026-07-10 결정) — 모듈 안에서는
-- historical_ratio로 실제 비중을 반영하면서, 모듈 "사이"는 항상 1/n로 나눠 실제 참고 견적서와
-- 동떨어진 결과가 나왔다(예: 그로스해킹이 퍼포먼스보다 항목이 훨씬 많은데도 똑같이 나눔).
-- module_weight에 참고 견적서의 실제 모듈별 공급가액(절대값, 같은 카탈로그 내에서만 상대
-- 비교)을 넣어 두면, 모듈 조합 배분도 실제 비중대로 나눌 수 있다. null이면(기존 데이터 전부)
-- 지금처럼 균등분배로 폴백한다 — 값을 채운 모듈만 점진적으로 정확해진다.

alter table item_catalogs add column module_weight numeric(12, 0);
comment on column item_catalogs.module_weight is
    '이 모듈(module_name)이 참고 견적서에서 차지한 실제 공급가액. 같은 module_name의 모든 행에
     동일한 값을 넣는다. null이면 allocation_service가 모듈 간 배분을 균등분배로 폴백한다
     (2026-08-19)';

-- 테스티파이 "우유곳간 자사몰 그로스해킹 마케팅 견적서_260811" 원본 발급본 실제 모듈별
-- 공급가액 그대로 (039 마이그레이션이 넣은 런칭 마케팅/그로스해킹/퍼포먼스 항목의 출처와 동일).
update item_catalogs set module_weight = 5300000
where task_type = '마케팅' and module_name = '런칭 마케팅'
  and entity_id = (select id from entity_templates where name = '테스티파이');
update item_catalogs set module_weight = 12800000
where task_type = '마케팅' and module_name = '그로스해킹' and mid_category = '주간단위 그로스해킹'
  and entity_id = (select id from entity_templates where name = '테스티파이');
update item_catalogs set module_weight = 9900000
where task_type = '마케팅' and module_name = '퍼포먼스'
  and entity_id = (select id from entity_templates where name = '테스티파이');

-- down
alter table item_catalogs drop column if exists module_weight;
