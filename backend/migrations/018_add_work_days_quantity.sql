-- up
-- Phase 5(PDF 발급)에서 실제 양식의 단가·작업일·수량 셀을 채우기 위해 추가한다. 단가는 저장하지
-- 않는다 — 실제 원본에 단가×작업일×수량이 공급가액과 안 맞는 "절삭" 보정 사례가 있어서(부록 A),
-- Claude가 배분한 금액을 (작업일×수량)으로 나눠 단가를 그때그때 역산한다. work_days/quantity는
-- 실제 발급 이력에서 확인된 값이고, 확인 안 된 항목은 기본값 1/1(단가=배분금액)로 둔다.
alter table item_catalogs
    add column work_days numeric(6,1) not null default 1,
    add column quantity numeric(8,2) not null default 1;

-- ============================================================
-- 테스티파이 — 시장검증 (미구 260324, 단아한화식 260130/260211 실제 샘플)
-- ============================================================
update item_catalogs set work_days = 1, quantity = 2
where task_type = '시장검증' and module_name = '시장성 테스트' and item_name = 'MVP 광고안 기획(및 제작)'
  and entity_id = (select id from entity_templates where name = '테스티파이');
-- (나머지 시장성 테스트/설문형 시장검증/Fake-door형/PMF Survey/FGI 항목은 전부 작업일1·수량1 확인됨 — 기본값 그대로)

-- ============================================================
-- 테스티파이 — 마케팅 (미구 260324 실제 샘플)
-- ============================================================
update item_catalogs set work_days = 1, quantity = 20
where task_type = '마케팅' and item_name = '이미지형 광고 소재 제작'
  and entity_id = (select id from entity_templates where name = '테스티파이');
update item_catalogs set work_days = 3, quantity = 1
where task_type = '마케팅' and item_name = 'Meta 광고 세팅 및 운영'
  and entity_id = (select id from entity_templates where name = '테스티파이');
update item_catalogs set work_days = 3, quantity = 4
where task_type = '마케팅' and item_name in ('주간 단위 데이터 분석', '주간 단위 액션플랜 수행')
  and entity_id = (select id from entity_templates where name = '테스티파이');

-- ============================================================
-- 블렌디드랩 — 마케팅/시장검증 통합형 (미구 260424_수정 실제 샘플)
-- ============================================================
update item_catalogs set work_days = 20, quantity = 1
where task_type = '마케팅' and item_name = '온라인 마케팅'
  and entity_id = (select id from entity_templates where name = '블렌디드랩');
update item_catalogs set work_days = 90, quantity = 1
where task_type = '마케팅' and item_name = '퍼포먼스 마케팅'
  and entity_id = (select id from entity_templates where name = '블렌디드랩');
update item_catalogs set work_days = 60, quantity = 1
where task_type = '마케팅' and item_name = '자사몰 데이터 세팅'
  and entity_id = (select id from entity_templates where name = '블렌디드랩');
update item_catalogs set work_days = 60, quantity = 1
where task_type = '마케팅' and item_name = '그로스해킹'
  and entity_id = (select id from entity_templates where name = '블렌디드랩');
update item_catalogs set work_days = 60, quantity = 1
where task_type = '시장검증' and alt_group = '미러링형(통합형)' and item_name = '시장성 테스트'
  and entity_id = (select id from entity_templates where name = '블렌디드랩');
update item_catalogs set work_days = 90, quantity = 1
where task_type = '시장검증' and alt_group = '미러링형(통합형)' and item_name = '설문형 시장검증'
  and entity_id = (select id from entity_templates where name = '블렌디드랩');
update item_catalogs set work_days = 20, quantity = 1
where task_type = '시장검증' and module_name = '독립형' and item_name = 'PMF Survey 기획 및 운영'
  and entity_id = (select id from entity_templates where name = '블렌디드랩');
update item_catalogs set work_days = 20, quantity = 1
where task_type = '시장검증' and module_name = '독립형' and item_name = '고객 인터뷰 기획 및 운영'
  and entity_id = (select id from entity_templates where name = '블렌디드랩');

-- ============================================================
-- 알파브라더스 — 시장검증 5개 모듈 (실제 원본 파일 셀 값 그대로)
-- ============================================================
update item_catalogs set work_days = 3, quantity = 3
where task_type = '시장검증' and module_name = 'FGI (심층좌담회)' and item_name = '인터뷰이 모집'
  and entity_id = (select id from entity_templates where name = '알파브라더스');
update item_catalogs set work_days = 5, quantity = 3
where task_type = '시장검증' and module_name = 'FGI (심층좌담회)' and item_name = '인터뷰 스크립트 작성'
  and entity_id = (select id from entity_templates where name = '알파브라더스');
update item_catalogs set work_days = 3, quantity = 1
where task_type = '시장검증' and module_name = 'FGI (심층좌담회)' and item_name = '인터뷰 진행'
  and entity_id = (select id from entity_templates where name = '알파브라더스');

update item_catalogs set work_days = 3, quantity = 3
where task_type = '시장검증' and module_name = '사용성 테스트' and item_name = '테스터 설계'
  and entity_id = (select id from entity_templates where name = '알파브라더스');
update item_catalogs set work_days = 1, quantity = 100
where task_type = '시장검증' and module_name = '사용성 테스트' and item_name = '일반테스터 모집'
  and entity_id = (select id from entity_templates where name = '알파브라더스');
update item_catalogs set work_days = 5, quantity = 1
where task_type = '시장검증' and module_name = '사용성 테스트' and item_name = '테스트 운영'
  and entity_id = (select id from entity_templates where name = '알파브라더스');

update item_catalogs set work_days = 1, quantity = 5
where task_type = '시장검증' and module_name = '기술성 테스트' and item_name = '기술성 테스트 설계'
  and entity_id = (select id from entity_templates where name = '알파브라더스');
update item_catalogs set work_days = 1, quantity = 5
where task_type = '시장검증' and module_name = '기술성 테스트' and item_name = '전문테스터 모집'
  and entity_id = (select id from entity_templates where name = '알파브라더스');
update item_catalogs set work_days = 10, quantity = 1
where task_type = '시장검증' and module_name = '기술성 테스트' and item_name = '1·2차 테스트 운영'
  and entity_id = (select id from entity_templates where name = '알파브라더스');

update item_catalogs set work_days = 3, quantity = 3
where task_type = '시장검증' and module_name = '시장성 테스트' and item_name = 'MVP 광고안 기획'
  and entity_id = (select id from entity_templates where name = '알파브라더스');
update item_catalogs set work_days = 10, quantity = 3
where task_type = '시장검증' and module_name = '시장성 테스트' and item_name = 'MVP 제작'
  and entity_id = (select id from entity_templates where name = '알파브라더스');
update item_catalogs set work_days = 5, quantity = 1
where task_type = '시장검증' and module_name = '시장성 테스트' and item_name = '데이터 분석'
  and entity_id = (select id from entity_templates where name = '알파브라더스');

update item_catalogs set work_days = 5, quantity = 5
where task_type = '시장검증' and module_name = '통합 패키지' and item_name = 'BM 진단 및 고도화'
  and entity_id = (select id from entity_templates where name = '알파브라더스');
update item_catalogs set work_days = 30, quantity = 2
where task_type = '시장검증' and module_name = '통합 패키지'
  and item_name in ('FGI (심층 그룹 인터뷰)', '사용성 테스트', '기술성 테스트')
  and entity_id = (select id from entity_templates where name = '알파브라더스');
update item_catalogs set work_days = 30, quantity = 3
where task_type = '시장검증' and module_name = '통합 패키지' and item_name = '시장성 테스트'
  and entity_id = (select id from entity_templates where name = '알파브라더스');

-- ============================================================
-- 테스티파이 — 광고대행 (미구 260211 실제 샘플: 4개 항목 전부 작업일1·수량1 확인됨)
-- 썬데이워커는 테스티파이를 그대로 미러링하므로 동일 값 반영
-- ============================================================
-- (전부 기본값 1/1과 일치 — 별도 업데이트 불필요)

-- down
alter table item_catalogs
    drop column if exists work_days,
    drop column if exists quantity;