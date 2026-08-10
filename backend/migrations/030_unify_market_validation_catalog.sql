-- up
-- 사용자 결정(2026-08-09): 시장검증 항목 정의를 법인별 실제 카탈로그 대신 전체 법인 공통
-- '표준 카탈로그'로 통합한다. 기준은 알파브라더스의 4개 모듈(FGI/사용성 테스트/기술성 테스트/
-- 시장성 테스트, 008 마이그레이션 6.5) — 개조식(1. 2. 3.) 세부항목까지 포함한 유일하게 완전한
-- 버전이라 이걸 기준으로 삼는다. "통합 패키지"는 알파브라더스 고유 번들 상품이라 표준 카탈로그
-- 에서는 제외한다(4개 모듈만 공통 기준, 알파브라더스 자신은 그대로 유지).
--
-- 이 변경으로 테스티파이/썬데이워커의 표준형·Fake-door형·PMF서베이+FGI형, 블렌디드랩의
-- 미러링형·독립형처럼 실제 발급 이력으로 검증된 데이터가 삭제된다 — 사용자가 이를 인지하고
-- "4모듈로 통일하되 되돌릴 수도 있으니 PRD에는 예전 방식을 남겨달라"고 결정함. PRD에 이전
-- 카탈로그 내용을 참고용으로 남겨두었고, 이 마이그레이션 down 블록으로도 완전히 복원 가능하다.

-- 1) 테스티파이/블렌디드랩/썬데이워커의 기존 시장검증 카탈로그 제거
delete from item_catalogs
where task_type = '시장검증'
  and entity_id in (
    select id from entity_templates where name in ('테스티파이', '블렌디드랩', '썬데이워커')
  );

-- 2) 4개 법인(테스티파이/블렌디드랩/썬데이워커/ABBG) 전부에 알파브라더스의 4개 모듈을
--    그대로 복제한다 (통합 패키지 제외). shared_source_entity_id로 출처를 명시한다.
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
  and ac.module_name in ('FGI (심층좌담회)', '사용성 테스트', '기술성 테스트', '시장성 테스트')
  and target.name in ('테스티파이', '블렌디드랩', '썬데이워커', 'ABBG');

-- down
-- 알파브라더스에서 복제해 넣은 4개 법인분 시장검증 행 제거
delete from item_catalogs
where task_type = '시장검증'
  and shared_source_entity_id = (select id from entity_templates where name = '알파브라더스')
  and entity_id in (
    select id from entity_templates where name in ('테스티파이', '블렌디드랩', '썬데이워커', 'ABBG')
  );

-- 테스티파이 시장검증 원복 (008 + 012 + 015 최종 상태)
insert into item_catalogs (entity_id, task_type, module_name, is_required, item_name, historical_ratio, alt_group, work_days, quantity, sort_order) values
((select id from entity_templates where name = '테스티파이'), '시장검증', '시장성 테스트', true,  'BM 진단 및 고도화',             5.6,  '표준형', 1, 1, 1),
((select id from entity_templates where name = '테스티파이'), '시장검증', '시장성 테스트', true,  'MVP 광고안 기획(및 제작)',       44.4, '표준형', 1, 2, 2),
((select id from entity_templates where name = '테스티파이'), '시장검증', '시장성 테스트', true,  '정량 데이터 시계열 분석',         22.2, '표준형', 1, 1, 3),
((select id from entity_templates where name = '테스티파이'), '시장검증', '시장성 테스트', true,  '정량 데이터 클러스터 분석',       22.2, '표준형', 1, 1, 4),
((select id from entity_templates where name = '테스티파이'), '시장검증', '시장성 테스트', true,  '결과 리포트 제공',               5.6,  '표준형', 1, 1, 5),
((select id from entity_templates where name = '테스티파이'), '시장검증', '설문형 시장검증', false, '설문 설계',                     5.6,  null, 1, 1, 1),
((select id from entity_templates where name = '테스티파이'), '시장검증', '설문형 시장검증', false, '설문응답자 모집 및 운영 *리워드 포함', 44.4, null, 1, 1, 2),
((select id from entity_templates where name = '테스티파이'), '시장검증', '설문형 시장검증', false, '설문 데이터 가공 및 시각화',      38.9, null, 1, 1, 3),
((select id from entity_templates where name = '테스티파이'), '시장검증', '설문형 시장검증', false, '결과 리포트 제공',               11.1, null, 1, 1, 4),
((select id from entity_templates where name = '테스티파이'), '시장검증', '시장성 테스트 (Fake-door형)', false, 'BM 진단 및 고도화',      6.83,  'Fake-door형', 1, 1, 1),
((select id from entity_templates where name = '테스티파이'), '시장검증', '시장성 테스트 (Fake-door형)', false, 'MVP 광고안 기획',        34.15, 'Fake-door형', 1, 1, 2),
((select id from entity_templates where name = '테스티파이'), '시장검증', '시장성 테스트 (Fake-door형)', false, 'Meta 광고 세팅 및 운영', 49.45, 'Fake-door형', 1, 1, 3),
((select id from entity_templates where name = '테스티파이'), '시장검증', '시장성 테스트 (Fake-door형)', false, '결과 리포트 제공',       9.56,  'Fake-door형', 1, 1, 4),
((select id from entity_templates where name = '테스티파이'), '시장검증', 'PMF Survey', false, '설문 기획 및 운영 (리워드포함)', 50.0, '서베이인터뷰형', 1, 1, 1),
((select id from entity_templates where name = '테스티파이'), '시장검증', 'PMF Survey', false, '설문 결과 및 분석 리포트 제공', 50.0, '서베이인터뷰형', 1, 1, 2),
((select id from entity_templates where name = '테스티파이'), '시장검증', 'FGI (심층그룹인터뷰)', false, '인터뷰 기획 및 운영 (리워드포함)', 50.0, '서베이인터뷰형', 1, 1, 1),
((select id from entity_templates where name = '테스티파이'), '시장검증', 'FGI (심층그룹인터뷰)', false, '인터뷰 결과 및 분석 리포트 제공', 50.0, '서베이인터뷰형', 1, 1, 2);

-- 블렌디드랩 시장검증 원복 (008 + 015 + 016 + 018 최종 상태)
insert into item_catalogs (entity_id, task_type, module_name, is_required, item_name, standard_description, historical_ratio, alt_group, shared_source_entity_id, work_days, quantity, sort_order) values
((select id from entity_templates where name = '블렌디드랩'), '시장검증', '시장성 테스트 (세부형)', false, 'BM 진단 및 고도화', null, null, '미러링형(세부형)', (select id from entity_templates where name = '테스티파이'), 1, 1, 1),
((select id from entity_templates where name = '블렌디드랩'), '시장검증', '시장성 테스트 (세부형)', false, 'MVP 제작',          null, null, '미러링형(세부형)', (select id from entity_templates where name = '테스티파이'), 1, 1, 2),
((select id from entity_templates where name = '블렌디드랩'), '시장검증', '시장성 테스트 (세부형)', false, '데이터 분석',        null, null, '미러링형(세부형)', (select id from entity_templates where name = '테스티파이'), 1, 1, 3),
((select id from entity_templates where name = '블렌디드랩'), '시장검증', '시장성 테스트 (세부형)', false, '결과 리포트 제공',   null, null, '미러링형(세부형)', (select id from entity_templates where name = '테스티파이'), 1, 1, 4),
((select id from entity_templates where name = '블렌디드랩'), '시장검증', '설문형 시장검증 (세부형)', false, '설문 설계',         null, null, '미러링형(세부형)', (select id from entity_templates where name = '테스티파이'), 1, 1, 1),
((select id from entity_templates where name = '블렌디드랩'), '시장검증', '설문형 시장검증 (세부형)', false, '모집 운영',         null, null, '미러링형(세부형)', (select id from entity_templates where name = '테스티파이'), 1, 1, 2),
((select id from entity_templates where name = '블렌디드랩'), '시장검증', '설문형 시장검증 (세부형)', false, '설문 가공',         null, null, '미러링형(세부형)', (select id from entity_templates where name = '테스티파이'), 1, 1, 3),
((select id from entity_templates where name = '블렌디드랩'), '시장검증', '설문형 시장검증 (세부형)', false, '결과 리포트 제공',   null, null, '미러링형(세부형)', (select id from entity_templates where name = '테스티파이'), 1, 1, 4),
((select id from entity_templates where name = '블렌디드랩'), '시장검증', '시장성 테스트', true, '시장성 테스트',
 'BM 진단 및 고도화 / MVP 제작 / 데이터 분석 / 결과 리포트 제공', 100.0, '미러링형(통합형)', null, 60, 1, 1),
((select id from entity_templates where name = '블렌디드랩'), '시장검증', '설문형 시장검증', true, '설문형 시장검증',
 '설문 설계 / 모집 운영 / 설문 가공 / 결과 리포트 제공', 100.0, '미러링형(통합형)', null, 90, 1, 1),
((select id from entity_templates where name = '블렌디드랩'), '시장검증', '독립형', false, 'PMF Survey 기획 및 운영', null, 50.0, '독립형', null, 20, 1, 1),
((select id from entity_templates where name = '블렌디드랩'), '시장검증', '독립형', false, '고객 인터뷰 기획 및 운영', null, 50.0, '독립형', null, 20, 1, 2);

-- 썬데이워커 시장검증 원복 (008 + 015 최종 상태 — 테스티파이 카탈로그 그대로 미러링)
insert into item_catalogs (entity_id, task_type, module_name, is_required, item_name, historical_ratio, alt_group, shared_source_entity_id, work_days, quantity, sort_order) values
((select id from entity_templates where name = '썬데이워커'), '시장검증', '시장성 테스트', true,  'BM 진단 및 고도화',            5.6,  '표준형', (select id from entity_templates where name = '테스티파이'), 1, 1, 1),
((select id from entity_templates where name = '썬데이워커'), '시장검증', '시장성 테스트', true,  'MVP 광고안 기획(및 제작)',      44.4, '표준형', (select id from entity_templates where name = '테스티파이'), 1, 1, 2),
((select id from entity_templates where name = '썬데이워커'), '시장검증', '시장성 테스트', true,  '정량 데이터 시계열 분석',        22.2, '표준형', (select id from entity_templates where name = '테스티파이'), 1, 1, 3),
((select id from entity_templates where name = '썬데이워커'), '시장검증', '시장성 테스트', true,  '정량 데이터 클러스터 분석',      22.2, '표준형', (select id from entity_templates where name = '테스티파이'), 1, 1, 4),
((select id from entity_templates where name = '썬데이워커'), '시장검증', '시장성 테스트', true,  '결과 리포트 제공',              5.6,  '표준형', (select id from entity_templates where name = '테스티파이'), 1, 1, 5),
((select id from entity_templates where name = '썬데이워커'), '시장검증', '설문형 시장검증', false, '설문 설계',                    5.6,  null, (select id from entity_templates where name = '테스티파이'), 1, 1, 1),
((select id from entity_templates where name = '썬데이워커'), '시장검증', '설문형 시장검증', false, '설문응답자 모집 및 운영 *리워드 포함', 44.4, null, (select id from entity_templates where name = '테스티파이'), 1, 1, 2),
((select id from entity_templates where name = '썬데이워커'), '시장검증', '설문형 시장검증', false, '설문 데이터 가공 및 시각화',      38.9, null, (select id from entity_templates where name = '테스티파이'), 1, 1, 3),
((select id from entity_templates where name = '썬데이워커'), '시장검증', '설문형 시장검증', false, '결과 리포트 제공',              11.1, null, (select id from entity_templates where name = '테스티파이'), 1, 1, 4),
((select id from entity_templates where name = '썬데이워커'), '시장검증', '시장성 테스트 (Fake-door형)', false, 'BM 진단 및 고도화', 6.83, 'Fake-door형', (select id from entity_templates where name = '테스티파이'), 1, 1, 1),
((select id from entity_templates where name = '썬데이워커'), '시장검증', '시장성 테스트 (Fake-door형)', false, 'MVP 광고안 기획', 34.15, 'Fake-door형', (select id from entity_templates where name = '테스티파이'), 1, 1, 2),
((select id from entity_templates where name = '썬데이워커'), '시장검증', '시장성 테스트 (Fake-door형)', false, 'Meta 광고 세팅 및 운영', 49.45, 'Fake-door형', (select id from entity_templates where name = '테스티파이'), 1, 1, 3),
((select id from entity_templates where name = '썬데이워커'), '시장검증', '시장성 테스트 (Fake-door형)', false, '결과 리포트 제공', 9.56, 'Fake-door형', (select id from entity_templates where name = '테스티파이'), 1, 1, 4),
((select id from entity_templates where name = '썬데이워커'), '시장검증', 'PMF Survey', false, '설문 기획 및 운영 (리워드포함)', 50.0, '서베이인터뷰형', (select id from entity_templates where name = '테스티파이'), 1, 1, 1),
((select id from entity_templates where name = '썬데이워커'), '시장검증', 'PMF Survey', false, '설문 결과 및 분석 리포트 제공', 50.0, '서베이인터뷰형', (select id from entity_templates where name = '테스티파이'), 1, 1, 2),
((select id from entity_templates where name = '썬데이워커'), '시장검증', 'FGI (심층그룹인터뷰)', false, '인터뷰 기획 및 운영 (리워드포함)', 50.0, '서베이인터뷰형', (select id from entity_templates where name = '테스티파이'), 1, 1, 1),
((select id from entity_templates where name = '썬데이워커'), '시장검증', 'FGI (심층그룹인터뷰)', false, '인터뷰 결과 및 분석 리포트 제공', 50.0, '서베이인터뷰형', (select id from entity_templates where name = '테스티파이'), 1, 1, 2);
