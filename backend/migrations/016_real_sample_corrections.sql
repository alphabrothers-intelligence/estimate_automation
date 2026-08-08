-- up
-- data/ 폴더에 있던 실제 견적서 원본(테스티파이 미구 마케팅대행/광고대행 샘플, 블렌디드랩 미구
-- 마케팅/고객검증 최신 수정본, 블렌디드랩 단아한화식 독립형)을 다시 확인하고 발견한 오류를
-- 바로잡는다 (2026-07-08 재검토).

-- ============================================================
-- 1) 블렌디드랩 마케팅 — 비중 채우기 (구조는 이미 맞았음, historical_ratio만 비어있었음)
-- 실제 샘플: "마케팅 견적서_미구_260424_수정" (22,000,000원 VAT포함, 20,000,000 공급가액)
-- ============================================================
update item_catalogs set historical_ratio = 20.0,
    standard_description = '마케팅 전략, USP설정, 소재 제작, Meta 운영'
where task_type = '마케팅' and module_name = '온라인 마케팅'
  and entity_id = (select id from entity_templates where name = '블렌디드랩');

update item_catalogs set historical_ratio = 60.0,
    standard_description = '테크니컬 SEO, SEO키워드제안, 결과보고'
where task_type = '마케팅' and module_name = '퍼포먼스 마케팅'
  and entity_id = (select id from entity_templates where name = '블렌디드랩');

update item_catalogs set historical_ratio = 10.0,
    standard_description = 'GA4, GTM, 대시보드 구축'
where task_type = '마케팅' and module_name = '자사몰 데이터 세팅'
  and entity_id = (select id from entity_templates where name = '블렌디드랩');

update item_catalogs set historical_ratio = 10.0,
    standard_description = '주간 단위 데이터분석 및 액션플랜'
where task_type = '마케팅' and module_name = '그로스해킹'
  and entity_id = (select id from entity_templates where name = '블렌디드랩');

-- ============================================================
-- 2) 블렌디드랩 시장검증 — "미러링형" 세부항목(근거 없음, 4개씩)을 "세부형" 대안으로 남기고,
-- 실제 샘플("고객검증 견적서_미구_260424_수정", 20,900,000원 VAT포함)과 일치하는 "통합형"
-- (모듈당 1개 항목)을 새 기본값으로 추가한다. "미러링형 -" 접두어는 화면에 노출되지 않도록
-- module_name에서 뺀다 (PM 요청).
-- ============================================================
update item_catalogs set
    module_name = '시장성 테스트 (세부형)',
    alt_group = '미러링형(세부형)',
    is_required = false
where task_type = '시장검증' and module_name = '미러링형 - 시장성 테스트'
  and entity_id = (select id from entity_templates where name = '블렌디드랩');

update item_catalogs set
    module_name = '설문형 시장검증 (세부형)',
    alt_group = '미러링형(세부형)',
    is_required = false
where task_type = '시장검증' and module_name = '미러링형 - 설문형 시장검증'
  and entity_id = (select id from entity_templates where name = '블렌디드랩');

insert into item_catalogs (entity_id, task_type, module_name, is_required, item_name, standard_description, historical_ratio, alt_group, sort_order) values
((select id from entity_templates where name = '블렌디드랩'), '시장검증', '시장성 테스트', true, '시장성 테스트',
 'BM 진단 및 고도화 / MVP 제작 / 데이터 분석 / 결과 리포트 제공', 100.0, '미러링형(통합형)', 1),
((select id from entity_templates where name = '블렌디드랩'), '시장검증', '설문형 시장검증', true, '설문형 시장검증',
 '설문 설계 / 모집 운영 / 설문 가공 / 결과 리포트 제공', 100.0, '미러링형(통합형)', 1);

-- 독립형(PMF Survey+고객인터뷰, 단아한화식 11,000,000원 샘플)은 정확히 50/50 확인됨
update item_catalogs set historical_ratio = 50.0
where task_type = '시장검증' and module_name = '독립형'
  and entity_id = (select id from entity_templates where name = '블렌디드랩');

-- ============================================================
-- 3) 테스티파이 광고대행 — 실제 샘플 신규 반영 ("마케팅 대행 견적서_미구_260211",
-- 16,500,000원 VAT포함, 용역명: "마케팅 대행 용역"). 지금까지는 자체 데이터가 없어
-- 블렌디드랩 카탈로그를 빌려쓰고 있었다.
-- ============================================================
insert into item_catalogs (entity_id, task_type, module_name, is_required, item_name, historical_ratio, sort_order) values
((select id from entity_templates where name = '테스티파이'), '광고대행', '광고형 마케팅 대행', true, '광고 대시보드 구축', 13.33, 1),
((select id from entity_templates where name = '테스티파이'), '광고대행', '광고형 마케팅 대행', true, '광고 집행 및 운영', 33.33, 2),
((select id from entity_templates where name = '테스티파이'), '광고대행', '광고형 마케팅 대행', true, '데이터 분석', 33.33, 3),
((select id from entity_templates where name = '테스티파이'), '광고대행', '광고형 마케팅 대행', true, '결과 리포팅 및 고도화 설계', 20.0, 4);

-- 썬데이워커는 PRD 6.6 "테스티파이 카탈로그를 그대로 사용" 원칙에 따라 동일하게 미러링
insert into item_catalogs (entity_id, task_type, module_name, is_required, item_name, historical_ratio, shared_source_entity_id, sort_order) values
((select id from entity_templates where name = '썬데이워커'), '광고대행', '광고형 마케팅 대행', true, '광고 대시보드 구축', 13.33, (select id from entity_templates where name = '테스티파이'), 1),
((select id from entity_templates where name = '썬데이워커'), '광고대행', '광고형 마케팅 대행', true, '광고 집행 및 운영', 33.33, (select id from entity_templates where name = '테스티파이'), 2),
((select id from entity_templates where name = '썬데이워커'), '광고대행', '광고형 마케팅 대행', true, '데이터 분석', 33.33, (select id from entity_templates where name = '테스티파이'), 3),
((select id from entity_templates where name = '썬데이워커'), '광고대행', '광고형 마케팅 대행', true, '결과 리포팅 및 고도화 설계', 20.0, (select id from entity_templates where name = '테스티파이'), 4);

-- down
delete from item_catalogs
where task_type = '광고대행' and module_name = '광고형 마케팅 대행'
  and entity_id in (
    select id from entity_templates where name in ('테스티파이', '썬데이워커')
  );

delete from item_catalogs
where task_type = '시장검증' and module_name in ('시장성 테스트', '설문형 시장검증') and alt_group = '미러링형(통합형)'
  and entity_id = (select id from entity_templates where name = '블렌디드랩');

update item_catalogs set
    module_name = '미러링형 - 시장성 테스트',
    alt_group = '미러링형',
    is_required = true
where task_type = '시장검증' and module_name = '시장성 테스트 (세부형)'
  and entity_id = (select id from entity_templates where name = '블렌디드랩');

update item_catalogs set
    module_name = '미러링형 - 설문형 시장검증',
    alt_group = '미러링형',
    is_required = true
where task_type = '시장검증' and module_name = '설문형 시장검증 (세부형)'
  and entity_id = (select id from entity_templates where name = '블렌디드랩');

update item_catalogs set historical_ratio = null
where task_type = '시장검증' and module_name = '독립형'
  and entity_id = (select id from entity_templates where name = '블렌디드랩');

-- 블렌디드랩 마케팅 비중 되돌리기는 017의 down에서 처리한다 (이 UP 블록의 마케팅 UPDATE 4개는
-- module_name 대신 item_name을 썼어야 해서 실제로는 대상이 없어 no-op이었음 — 017 참고).
