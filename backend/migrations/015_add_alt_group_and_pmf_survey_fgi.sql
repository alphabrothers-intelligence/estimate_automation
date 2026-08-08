-- up
-- alt_group: 같은 (entity, task_type) 안에서 서로 배타적인 "대안 구성"을 묶는 키
-- (예: 알파브라더스의 통합패키지 vs 개별 4개 모듈, 테스티파이의 표준형 vs Fake-door형 vs
-- PMF서베이+FGI). 같은 alt_group 값을 공유하는 module_name들은 하나의 선택지로 합쳐지고,
-- alt_group이 다른 행끼리는 라디오(택1) 관계다. alt_group이 null이면 기존처럼 is_required로만
-- 판단한다(true=항상 포함, false=독립적으로 추가/제외 가능한 옵션).
alter table item_catalogs add column alt_group text;

-- ============================================================
-- 테스티파이 시장검증: 기존 표준형/Fake-door형에 alt_group 부여
-- ============================================================
update item_catalogs set alt_group = '표준형'
where task_type = '시장검증' and module_name = '시장성 테스트' and is_required = true
  and entity_id = (select id from entity_templates where name = '테스티파이');

update item_catalogs set alt_group = 'Fake-door형'
where task_type = '시장검증' and module_name = '시장성 테스트 (Fake-door형)'
  and entity_id = (select id from entity_templates where name = '테스티파이');

-- [신규] 실제 발급 샘플(단아한화식, 2026-01-30, 총 합계 13,200,000원 VAT포함, 용역명:
-- "Survey, Interview형 시장 검증 용역") — 시장성 테스트 없이 PMF Survey + FGI 두 모듈만으로
-- 구성된 완전히 다른 견적. 표준형/Fake-door형과 상호 배타이므로 alt_group을 공유시킨다
-- (PM이 이 조합을 고르면 시장성 테스트는 빠지고 PMF Survey+FGI만 들어감).
insert into item_catalogs (entity_id, task_type, module_name, is_required, item_name, historical_ratio, alt_group, sort_order) values
((select id from entity_templates where name = '테스티파이'), '시장검증', 'PMF Survey', false, '설문 기획 및 운영 (리워드포함)', 50.0, '서베이인터뷰형', 1),
((select id from entity_templates where name = '테스티파이'), '시장검증', 'PMF Survey', false, '설문 결과 및 분석 리포트 제공', 50.0, '서베이인터뷰형', 2),
((select id from entity_templates where name = '테스티파이'), '시장검증', 'FGI (심층그룹인터뷰)', false, '인터뷰 기획 및 운영 (리워드포함)', 50.0, '서베이인터뷰형', 1),
((select id from entity_templates where name = '테스티파이'), '시장검증', 'FGI (심층그룹인터뷰)', false, '인터뷰 결과 및 분석 리포트 제공', 50.0, '서베이인터뷰형', 2);

-- ============================================================
-- 알파브라더스 시장검증: 5개 모듈(통합패키지 vs 개별 4개)이 서로 배타
-- ============================================================
update item_catalogs set alt_group = '통합패키지'
where task_type = '시장검증' and module_name = '통합 패키지'
  and entity_id = (select id from entity_templates where name = '알파브라더스');
update item_catalogs set alt_group = 'FGI'
where task_type = '시장검증' and module_name = 'FGI (심층좌담회)'
  and entity_id = (select id from entity_templates where name = '알파브라더스');
update item_catalogs set alt_group = '사용성테스트'
where task_type = '시장검증' and module_name = '사용성 테스트'
  and entity_id = (select id from entity_templates where name = '알파브라더스');
update item_catalogs set alt_group = '기술성테스트'
where task_type = '시장검증' and module_name = '기술성 테스트'
  and entity_id = (select id from entity_templates where name = '알파브라더스');
update item_catalogs set alt_group = '시장성테스트'
where task_type = '시장검증' and module_name = '시장성 테스트' and is_required = false
  and entity_id = (select id from entity_templates where name = '알파브라더스');

-- ============================================================
-- 블렌디드랩 시장검증: "미러링형"(미구 샘플 — 시장성테스트+설문형시장검증 묶음)과
-- "독립형"(단아한화식 샘플 — PMF Survey+고객인터뷰)은 서로 다른 실제 고객사의 완전히 다른
-- 견적 구성인데 지금까지 둘 다 is_required=true로 항상 같이 붙어 나가고 있었다. 상호배타로 정정.
-- ============================================================
update item_catalogs set alt_group = '미러링형'
where task_type = '시장검증' and module_name in ('미러링형 - 시장성 테스트', '미러링형 - 설문형 시장검증')
  and entity_id = (select id from entity_templates where name = '블렌디드랩');
update item_catalogs set alt_group = '독립형', is_required = false
where task_type = '시장검증' and module_name = '독립형'
  and entity_id = (select id from entity_templates where name = '블렌디드랩');

-- ============================================================
-- 썬데이워커 시장검증: PRD 6.6 "테스티파이 6.1 카탈로그를 그대로 사용" 원칙에 따라
-- 표준형/Fake-door형/PMF서베이+FGI 구성을 동일하게 미러링한다. 겸사겸사 "설문형 시장검증"이
-- 실수로 is_required=true로 들어가 있던 것도 테스티파이 원본(false, 옵션)과 일치하도록 정정.
-- ============================================================
update item_catalogs set is_required = false
where task_type = '시장검증' and module_name = '설문형 시장검증'
  and entity_id = (select id from entity_templates where name = '썬데이워커');

update item_catalogs set alt_group = '표준형'
where task_type = '시장검증' and module_name = '시장성 테스트' and is_required = true
  and entity_id = (select id from entity_templates where name = '썬데이워커');

insert into item_catalogs (entity_id, task_type, module_name, is_required, item_name, historical_ratio, alt_group, shared_source_entity_id, sort_order) values
((select id from entity_templates where name = '썬데이워커'), '시장검증', '시장성 테스트 (Fake-door형)', false, 'BM 진단 및 고도화', 6.83, 'Fake-door형', (select id from entity_templates where name = '테스티파이'), 1),
((select id from entity_templates where name = '썬데이워커'), '시장검증', '시장성 테스트 (Fake-door형)', false, 'MVP 광고안 기획', 34.15, 'Fake-door형', (select id from entity_templates where name = '테스티파이'), 2),
((select id from entity_templates where name = '썬데이워커'), '시장검증', '시장성 테스트 (Fake-door형)', false, 'Meta 광고 세팅 및 운영', 49.45, 'Fake-door형', (select id from entity_templates where name = '테스티파이'), 3),
((select id from entity_templates where name = '썬데이워커'), '시장검증', '시장성 테스트 (Fake-door형)', false, '결과 리포트 제공', 9.56, 'Fake-door형', (select id from entity_templates where name = '테스티파이'), 4),
((select id from entity_templates where name = '썬데이워커'), '시장검증', 'PMF Survey', false, '설문 기획 및 운영 (리워드포함)', 50.0, '서베이인터뷰형', (select id from entity_templates where name = '테스티파이'), 1),
((select id from entity_templates where name = '썬데이워커'), '시장검증', 'PMF Survey', false, '설문 결과 및 분석 리포트 제공', 50.0, '서베이인터뷰형', (select id from entity_templates where name = '테스티파이'), 2),
((select id from entity_templates where name = '썬데이워커'), '시장검증', 'FGI (심층그룹인터뷰)', false, '인터뷰 기획 및 운영 (리워드포함)', 50.0, '서베이인터뷰형', (select id from entity_templates where name = '테스티파이'), 1),
((select id from entity_templates where name = '썬데이워커'), '시장검증', 'FGI (심층그룹인터뷰)', false, '인터뷰 결과 및 분석 리포트 제공', 50.0, '서베이인터뷰형', (select id from entity_templates where name = '테스티파이'), 2);

-- down
delete from item_catalogs
where task_type = '시장검증' and module_name in ('PMF Survey', 'FGI (심층그룹인터뷰)', '시장성 테스트 (Fake-door형)')
  and entity_id = (select id from entity_templates where name = '썬데이워커');

update item_catalogs set alt_group = null;
update item_catalogs set is_required = true
where task_type = '시장검증' and module_name = '독립형'
  and entity_id = (select id from entity_templates where name = '블렌디드랩');
update item_catalogs set is_required = true
where task_type = '시장검증' and module_name = '설문형 시장검증'
  and entity_id = (select id from entity_templates where name = '썬데이워커');

delete from item_catalogs
where task_type = '시장검증' and module_name in ('PMF Survey', 'FGI (심층그룹인터뷰)')
  and entity_id = (select id from entity_templates where name = '테스티파이');

alter table item_catalogs drop column if exists alt_group;
