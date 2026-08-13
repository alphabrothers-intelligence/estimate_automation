-- up
-- 사용자 결정(2026-08-12): 030에서 "통합 패키지는 알파브라더스 고유 상품"이라는 이유로 표준
-- 카탈로그에서 제외했었는데, 실제 알파브라더스 원본 파일(견적서 시트, 상상특허법률사무소 건)을
-- 확인한 뒤 재검토함 — 다른 4개 법인은 애초에 시장검증 시트 자체가 대/중분류+상품명 정도의
-- 요약형 구조라(module_name=null, 단일 시트 범용 렌더링), 통합 패키지처럼 모듈당 1줄로 압축된
-- 요약형 항목이 오히려 더 잘 맞는다고 판단해 4개 법인에도 추가하기로 함. 알파브라더스의 5개
-- 항목(BM진단/FGI/사용성테스트/기술성테스트/시장성테스트, 030과 동일한 복제 패턴)을 그대로
-- 복제한다 — 새 quote_template/시트 작업 불필요(4개 법인 모두 module_name 무관 단일 시트 렌더링).
insert into item_catalogs (
    entity_id, task_type, module_name, is_required, item_name, standard_description,
    historical_ratio, alt_group, work_days, quantity, shared_source_entity_id, sort_order
)
select target.id, ac.task_type, ac.module_name, ac.is_required, ac.item_name, ac.standard_description,
       ac.historical_ratio, ac.alt_group, ac.work_days, ac.quantity, alpha.id, ac.sort_order
from item_catalogs ac
join entity_templates alpha on alpha.id = ac.entity_id and alpha.name = '알파브라더스'
cross join entity_templates target
where ac.task_type = '시장검증'
  and ac.is_current = true
  and ac.module_name = '통합 패키지'
  and target.name in ('테스티파이', '블렌디드랩', '썬데이워커', 'ABBG');

-- down
delete from item_catalogs
where task_type = '시장검증'
  and module_name = '통합 패키지'
  and shared_source_entity_id = (select id from entity_templates where name = '알파브라더스')
  and entity_id in (
    select id from entity_templates where name in ('테스티파이', '블렌디드랩', '썬데이워커', 'ABBG')
  );
