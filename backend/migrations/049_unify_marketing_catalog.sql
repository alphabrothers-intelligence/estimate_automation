-- up
-- 사용자 결정(2026-08-24): 마케팅 항목 정의를 법인별 카탈로그 대신 전체 법인 공통 '표준
-- 카탈로그'로 통합한다. 030이 시장검증에 한 것과 같은 방식이며, 기준은 테스티파이의 9개
-- 모듈이다 — 썬데이워커 7개가 이미 이 9개의 부분집합이라 유일한 상위 집합이기 때문이다.
--
-- 배경: 과업 선택 화면은 "기준 기업" 한 곳의 카탈로그만 그리고 나머지 법인은 그 선택을
-- 상품명 매칭으로 물려받는다(frontend/app/estimate-wizard.tsx referenceEntityId). 그래서
-- 카탈로그가 2행뿐인 블렌디드랩이 기준이 되면 화면 전체가 2개로 줄어, 같이 선택된 테스티파이의
-- 9개가 나올 기회조차 없었다(2026-08-24 사용자 신고). 알파브라더스·ABBG는 아예 0행이라
-- catalog_service.FALLBACK_SOURCE_BY_TASK_TYPE로 테스티파이 것을 빌려쓰던 중이었다.
-- 5개 법인을 같은 카탈로그로 맞추면 어느 법인이 기준이 되든 같은 9개가 뜬다.
--
-- 블렌디드랩 고유 상품 2개(Meta 광고 테스트 기획 및 운영 / 온라인 마케팅 패키지)와 썬데이워커
-- 자체 7개 모듈은 실제 발급 이력으로 검증된 데이터지만, "5개 법인 전부 정확히 9개로 통일"을
-- 사용자가 선택해 삭제한다 — 030 때와 마찬가지로 아래 down 블록으로 완전히 복원할 수 있다.
--
-- 단가는 환산 없이 그대로 복제한다. 2026-08-21에 금액 규칙이 "공급가액 = 단가 × 수량"으로
-- 통일됐고(047/048), 양식별 원본 수식 차이(블렌디드랩 =단가, 알파브라더스 모듈 시트
-- SUM(작업일×수량×단가))는 pdf_service가 그 칸의 수식을 지우고 값을 직접 써서 흡수한다.

-- 1) 블렌디드랩·썬데이워커의 기존 마케팅 카탈로그 제거 (알파브라더스·ABBG는 원래 0행)
delete from item_catalogs
where task_type = '마케팅'
  and entity_id in (
    select id from entity_templates where name in ('블렌디드랩', '썬데이워커')
  );

-- 2) 나머지 4개 법인에 테스티파이의 마케팅 카탈로그를 그대로 복제한다.
--    shared_source_entity_id로 출처를 남겨 down에서 정확히 이 행들만 지운다.
insert into item_catalogs (
    entity_id, task_type, module_name, mid_category, is_required, item_name,
    standard_description, historical_ratio, alt_group, module_weight,
    work_days, quantity, unit_price, shared_source_entity_id, sort_order
)
select target.id, tc.task_type, tc.module_name, tc.mid_category, tc.is_required, tc.item_name,
       tc.standard_description, tc.historical_ratio, tc.alt_group, tc.module_weight,
       tc.work_days, tc.quantity, tc.unit_price, testify.id, tc.sort_order
from item_catalogs tc
join entity_templates testify on testify.id = tc.entity_id and testify.name = '테스티파이'
cross join entity_templates target
where tc.task_type = '마케팅'
  and tc.is_current = true
  and target.name in ('블렌디드랩', '썬데이워커', '알파브라더스', 'ABBG');

-- down
-- 테스티파이에서 복제해 넣은 4개 법인분 마케팅 행 제거
delete from item_catalogs
where task_type = '마케팅'
  and shared_source_entity_id = (select id from entity_templates where name = '테스티파이')
  and entity_id in (
    select id from entity_templates where name in ('블렌디드랩', '썬데이워커', '알파브라더스', 'ABBG')
  );

-- 블렌디드랩 마케팅 5행 원복
insert into item_catalogs (entity_id, task_type, module_name, mid_category, is_required, item_name, standard_description, historical_ratio, alt_group, module_weight, work_days, quantity, unit_price, sort_order) values
((select id from entity_templates where name = '블렌디드랩'), '마케팅', 'Meta 광고 테스트 기획 및 운영', null, false, 'Meta 광고 테스트 기획 및 운영', '표본 1건뿐(단아한화식) — 세부항목 필요 여부·항상 단일항목형인지 불확실 (PRD 8장 질문 5)', 100.0, '단일광고형', null, 1.0, 1.0, null, 1),
((select id from entity_templates where name = '블렌디드랩'), '마케팅', '온라인 마케팅 패키지', null, true, '온라인 마케팅', '마케팅 전략, USP설정, 소재 제작, Meta 운영', 20.0, '마케팅기본형', null, 20.0, 1.0, 4000000, 1),
((select id from entity_templates where name = '블렌디드랩'), '마케팅', '온라인 마케팅 패키지', null, true, '퍼포먼스 마케팅', '테크니컬 SEO, SEO키워드제안, 결과보고', 60.0, '마케팅기본형', null, 90.0, 1.0, 12000000, 2),
((select id from entity_templates where name = '블렌디드랩'), '마케팅', '온라인 마케팅 패키지', null, true, '자사몰 데이터 세팅', 'GA4, GTM, 대시보드 구축', 10.0, '마케팅기본형', null, 60.0, 1.0, 2000000, 3),
((select id from entity_templates where name = '블렌디드랩'), '마케팅', '온라인 마케팅 패키지', null, true, '그로스해킹', '주간 단위 데이터분석 및 액션플랜', 10.0, '마케팅기본형', null, 60.0, 1.0, 2000000, 4);

-- 썬데이워커 마케팅 22행 원복
insert into item_catalogs (entity_id, task_type, module_name, mid_category, is_required, item_name, standard_description, historical_ratio, alt_group, module_weight, work_days, quantity, unit_price, sort_order) values
((select id from entity_templates where name = '썬데이워커'), '마케팅', 'SEO 마케팅', null, false, 'SEO 키워드 분석 및 제안', null, null, null, 2200000, 1.0, 1.0, 500000, 1),
((select id from entity_templates where name = '썬데이워커'), '마케팅', 'SEO 마케팅', null, false, '테크니컬 SEO 최적화', null, null, null, 2200000, 1.0, 1.0, 1500000, 2),
((select id from entity_templates where name = '썬데이워커'), '마케팅', 'SEO 마케팅', null, false, 'SEO 성능 측정 및 보고', null, null, null, 2200000, 1.0, 1.0, 200000, 3),
((select id from entity_templates where name = '썬데이워커'), '마케팅', '광고형 마케팅 대행', null, false, '광고 대시보드 구축', null, 13.33, '광고형', 15000000, 1.0, 1.0, 2000000, 1),
((select id from entity_templates where name = '썬데이워커'), '마케팅', '광고형 마케팅 대행', null, false, '광고 집행 및 운영', null, 33.33, '광고형', 15000000, 1.0, 1.0, 5000000, 2),
((select id from entity_templates where name = '썬데이워커'), '마케팅', '광고형 마케팅 대행', null, false, '데이터 분석', null, 33.33, '광고형', 15000000, 1.0, 1.0, 5000000, 3),
((select id from entity_templates where name = '썬데이워커'), '마케팅', '광고형 마케팅 대행', null, false, '결과 리포팅 및 고도화 설계', null, 20.0, '광고형', 15000000, 1.0, 1.0, 3000000, 4),
((select id from entity_templates where name = '썬데이워커'), '마케팅', '그로스해킹', null, false, '주간 단위 데이터 분석', null, 50.0, null, 4800000, 1.0, 1.0, 2400000, 1),
((select id from entity_templates where name = '썬데이워커'), '마케팅', '그로스해킹', null, false, '주간 단위 액션플랜 수행', null, 50.0, null, 4800000, 1.0, 1.0, 2400000, 2),
((select id from entity_templates where name = '썬데이워커'), '마케팅', '네이버 쇼핑 광고 대행', null, false, '전략 기획', null, 28.57, '네이버쇼핑형', 3500000, 1.0, 1.0, 1000000, 1),
((select id from entity_templates where name = '썬데이워커'), '마케팅', '네이버 쇼핑 광고 대행', null, false, '광고 운영', null, 57.14, '네이버쇼핑형', 3500000, 1.0, 1.0, 2000000, 2),
((select id from entity_templates where name = '썬데이워커'), '마케팅', '네이버 쇼핑 광고 대행', null, false, '결과 보고', null, 14.29, '네이버쇼핑형', 3500000, 1.0, 1.0, 500000, 3),
((select id from entity_templates where name = '썬데이워커'), '마케팅', '온라인 광고', null, false, '마케팅 전략안', null, null, null, 8000000, 1.0, 1.0, 500000, 1),
((select id from entity_templates where name = '썬데이워커'), '마케팅', '온라인 광고', null, false, 'USP 설정 및 제안', null, null, null, 8000000, 1.0, 1.0, 500000, 2),
((select id from entity_templates where name = '썬데이워커'), '마케팅', '온라인 광고', null, false, '이미지형 광고 소재 제작', null, null, null, 8000000, 1.0, 1.0, 4000000, 3),
((select id from entity_templates where name = '썬데이워커'), '마케팅', '온라인 광고', null, false, 'Meta 광고 세팅 및 운영', null, null, null, 8000000, 1.0, 1.0, 3000000, 4),
((select id from entity_templates where name = '썬데이워커'), '마케팅', '자사몰 데이터 세팅', null, false, '자사몰 데이터 연결', null, null, null, 3000000, 1.0, 1.0, 500000, 1),
((select id from entity_templates where name = '썬데이워커'), '마케팅', '자사몰 데이터 세팅', null, false, 'GA4·GTM 데이터 연결', null, null, null, 3000000, 1.0, 1.0, 500000, 2),
((select id from entity_templates where name = '썬데이워커'), '마케팅', '자사몰 데이터 세팅', null, false, '대시보드 구축 및 데이터 시각화', null, null, null, 3000000, 1.0, 1.0, 2000000, 3),
((select id from entity_templates where name = '썬데이워커'), '마케팅', '카카오 톡스토어 광고 대행', null, false, '전략 기획', null, 28.57, '카카오톡스토어형', 3500000, 1.0, 1.0, 1000000, 1),
((select id from entity_templates where name = '썬데이워커'), '마케팅', '카카오 톡스토어 광고 대행', null, false, '광고 운영', null, 57.14, '카카오톡스토어형', 3500000, 1.0, 1.0, 2000000, 2),
((select id from entity_templates where name = '썬데이워커'), '마케팅', '카카오 톡스토어 광고 대행', null, false, '결과 보고', null, 14.29, '카카오톡스토어형', 3500000, 1.0, 1.0, 500000, 3);
