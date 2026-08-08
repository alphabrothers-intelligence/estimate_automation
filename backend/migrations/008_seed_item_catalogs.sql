-- up
-- PRD 6장 "항목 카탈로그"에 확인된 데이터를 그대로 시딩한다.
-- 과거 비중(%)이 확인되지 않은 항목만 historical_ratio를 NULL로 둔다 (임의로 수치를 만들어내지 않음).
-- 알파브라더스 4개 세부모듈(FGI/사용성테스트/기술성테스트/시장성테스트) + 통합 패키지는 실제 원본 파일
-- (backend/templates/alphabrothers.xlsx)에서 항목별 단가·상품구성 설명을 그대로 확인해 반영했다.
-- 테스티파이 마케팅도 실제 발급 샘플(미구, 260211)에서 항목별 비중을 확인해 반영했다.

-- ============================================================
-- 6.1 시장검증 — 테스티파이
-- ============================================================
insert into item_catalogs (entity_id, task_type, module_name, is_required, item_name, historical_ratio, sort_order) values
((select id from entity_templates where name = '테스티파이'), '시장검증', '시장성 테스트', true,  'BM 진단 및 고도화',            5.6,  1),
((select id from entity_templates where name = '테스티파이'), '시장검증', '시장성 테스트', true,  'MVP 광고안 기획(및 제작)',      44.4, 2),
((select id from entity_templates where name = '테스티파이'), '시장검증', '시장성 테스트', true,  '정량 데이터 시계열 분석',        22.2, 3),
((select id from entity_templates where name = '테스티파이'), '시장검증', '시장성 테스트', true,  '정량 데이터 클러스터 분석',      22.2, 4),
((select id from entity_templates where name = '테스티파이'), '시장검증', '시장성 테스트', true,  '결과 리포트 제공',              5.6,  5),
((select id from entity_templates where name = '테스티파이'), '시장검증', '설문형 시장검증', false, '설문 설계',                    5.6,  1),
((select id from entity_templates where name = '테스티파이'), '시장검증', '설문형 시장검증', false, '설문응답자 모집 및 운영 *리워드 포함', 44.4, 2),
((select id from entity_templates where name = '테스티파이'), '시장검증', '설문형 시장검증', false, '설문 데이터 가공 및 시각화',      38.9, 3),
((select id from entity_templates where name = '테스티파이'), '시장검증', '설문형 시장검증', false, '결과 리포트 제공',              11.1, 4);

-- [v0.4] "시장성 테스트" 모듈의 Fake-door test 변형 — 실제 발급 샘플(단아한화식, 2026-01-30,
-- 공급가액 합계 7,320,000원, 총 합계 8,052,000원 VAT포함) 확인 완료. 3번째 항목이 "정량 데이터
-- 시계열 분석" 대신 "Meta 광고 세팅 및 운영"으로 대체된 것 — 스키마 변경 없이 별도 모듈로 저장
-- (PM이 표준형/Fake-door형 중 선택하는 방식, Phase 4에서 모듈 선택 로직에 포함).
insert into item_catalogs (entity_id, task_type, module_name, is_required, item_name, historical_ratio, sort_order) values
((select id from entity_templates where name = '테스티파이'), '시장검증', '시장성 테스트 (Fake-door형)', false, 'BM 진단 및 고도화',      6.83,  1),
((select id from entity_templates where name = '테스티파이'), '시장검증', '시장성 테스트 (Fake-door형)', false, 'MVP 광고안 기획',        34.15, 2),
((select id from entity_templates where name = '테스티파이'), '시장검증', '시장성 테스트 (Fake-door형)', false, 'Meta 광고 세팅 및 운영', 49.45, 3),
((select id from entity_templates where name = '테스티파이'), '시장검증', '시장성 테스트 (Fake-door형)', false, '결과 리포트 제공',       9.56,  4);

-- ============================================================
-- 6.2 마케팅 — 테스티파이 ("그로스해킹 마케팅 대행 용역")
-- 실제 발급 샘플(미구, 260211, 공급가액 합계 18,000,000원) 기준 비중 반영.
-- ============================================================
insert into item_catalogs (entity_id, task_type, module_name, is_required, item_name, historical_ratio, sort_order) values
((select id from entity_templates where name = '테스티파이'), '마케팅', '온라인 광고',        true, '마케팅 전략안',                2.78,  1),
((select id from entity_templates where name = '테스티파이'), '마케팅', '온라인 광고',        true, 'USP 설정 및 제안',             2.78,  2),
((select id from entity_templates where name = '테스티파이'), '마케팅', '온라인 광고',        true, '이미지형 광고 소재 제작',        22.22, 3),
((select id from entity_templates where name = '테스티파이'), '마케팅', '온라인 광고',        true, 'Meta 광고 세팅 및 운영',        16.67, 4),
((select id from entity_templates where name = '테스티파이'), '마케팅', 'SEO 마케팅',         true, 'SEO 키워드 분석 및 제안',        2.78,  1),
((select id from entity_templates where name = '테스티파이'), '마케팅', 'SEO 마케팅',         true, '테크니컬 SEO 최적화',           8.33,  2),
((select id from entity_templates where name = '테스티파이'), '마케팅', 'SEO 마케팅',         true, 'SEO 성능 측정 및 보고',         1.11,  3),
((select id from entity_templates where name = '테스티파이'), '마케팅', '자사몰 데이터 세팅',  true, '자사몰 데이터 연결',            2.78,  1),
((select id from entity_templates where name = '테스티파이'), '마케팅', '자사몰 데이터 세팅',  true, 'GA4·GTM 데이터 연결',          2.78,  2),
((select id from entity_templates where name = '테스티파이'), '마케팅', '자사몰 데이터 세팅',  true, '대시보드 구축 및 데이터 시각화', 11.11, 3),
((select id from entity_templates where name = '테스티파이'), '마케팅', '그로스해킹',         true, '주간 단위 데이터 분석',         13.33, 1),
((select id from entity_templates where name = '테스티파이'), '마케팅', '그로스해킹',         true, '주간 단위 액션플랜 수행',        13.33, 2);

-- ============================================================
-- 6.2 마케팅 — 블렌디드랩 (미러링형: 테스티파이 대분류명 재사용, 세부항목 압축)
-- ============================================================
insert into item_catalogs (entity_id, task_type, module_name, is_required, item_name, standard_description, shared_source_entity_id, sort_order) values
((select id from entity_templates where name = '블렌디드랩'), '마케팅', null, true, '온라인 마케팅',   '테스티파이 "온라인 광고" 미러링(압축)', (select id from entity_templates where name = '테스티파이'), 1),
((select id from entity_templates where name = '블렌디드랩'), '마케팅', null, true, '퍼포먼스 마케팅', '테스티파이 "SEO 마케팅" 미러링(압축). 재발급 시 "SEO 마케팅"으로 항목명이 바뀐 사례 있음', (select id from entity_templates where name = '테스티파이'), 2),
((select id from entity_templates where name = '블렌디드랩'), '마케팅', null, true, '자사몰 데이터 세팅', '테스티파이 항목명 그대로 사용', (select id from entity_templates where name = '테스티파이'), 3),
((select id from entity_templates where name = '블렌디드랩'), '마케팅', null, true, '그로스해킹',      '재발급 시 "자사몰 데이터 세팅"+"그로스해킹"이 "SNS 마케팅" 1개로 통합된 사례 있음', (select id from entity_templates where name = '테스티파이'), 4);

-- ============================================================
-- 6.3 광고대행 — 블렌디드랩 (표본 1건, 단일 항목형)
-- ============================================================
insert into item_catalogs (entity_id, task_type, module_name, is_required, item_name, standard_description, historical_ratio, sort_order) values
((select id from entity_templates where name = '블렌디드랩'), '광고대행', null, true, 'Meta 광고 테스트 기획 및 운영',
 '표본 1건뿐(단아한화식) — 세부항목 필요 여부·항상 단일항목형인지 불확실 (PRD 8장 질문 5)', 100.0, 1);

-- ============================================================
-- 6.4 [v0.4: task_type을 '고객검증'→'시장검증'으로 통합] 블렌디드랩 (미러링형 / 독립형 두 모드)
-- 고객검증과 시장검증은 실제로 동일 과업이며 견적서마다 명칭만 다르게 표기된 것으로 확인됨(2026-07-07).
-- ============================================================
insert into item_catalogs (entity_id, task_type, module_name, is_required, item_name, shared_source_entity_id, sort_order) values
((select id from entity_templates where name = '블렌디드랩'), '시장검증', '미러링형 - 시장성 테스트',   true, 'BM 진단 및 고도화', (select id from entity_templates where name = '테스티파이'), 1),
((select id from entity_templates where name = '블렌디드랩'), '시장검증', '미러링형 - 시장성 테스트',   true, 'MVP 제작',          (select id from entity_templates where name = '테스티파이'), 2),
((select id from entity_templates where name = '블렌디드랩'), '시장검증', '미러링형 - 시장성 테스트',   true, '데이터 분석',        (select id from entity_templates where name = '테스티파이'), 3),
((select id from entity_templates where name = '블렌디드랩'), '시장검증', '미러링형 - 시장성 테스트',   true, '결과 리포트 제공',   (select id from entity_templates where name = '테스티파이'), 4),
((select id from entity_templates where name = '블렌디드랩'), '시장검증', '미러링형 - 설문형 시장검증', true, '설문 설계',         (select id from entity_templates where name = '테스티파이'), 1),
((select id from entity_templates where name = '블렌디드랩'), '시장검증', '미러링형 - 설문형 시장검증', true, '모집 운영',         (select id from entity_templates where name = '테스티파이'), 2),
((select id from entity_templates where name = '블렌디드랩'), '시장검증', '미러링형 - 설문형 시장검증', true, '설문 가공',         (select id from entity_templates where name = '테스티파이'), 3),
((select id from entity_templates where name = '블렌디드랩'), '시장검증', '미러링형 - 설문형 시장검증', true, '결과 리포트 제공',   (select id from entity_templates where name = '테스티파이'), 4);

insert into item_catalogs (entity_id, task_type, module_name, is_required, item_name, sort_order) values
((select id from entity_templates where name = '블렌디드랩'), '시장검증', '독립형', true, 'PMF Survey 기획 및 운영',      1),
((select id from entity_templates where name = '블렌디드랩'), '시장검증', '독립형', true, '고객 인터뷰 기획 및 운영',      2);

-- ============================================================
-- 6.5 시장검증 — 알파브라더스 (4개 세부모듈 + 통합 패키지)
-- 5개 시트(FGI/사용성테스트/기술성테스트/시장성테스트/견적서=통합패키지) 전체를 원본 파일에서 확인,
-- 항목별 상품구성 설명·단가·비중을 실제 값 그대로 반영한다 (원본 파일: backend/templates/alphabrothers.xlsx).
-- 4개 모듈 모두 공급가액 합계 5,000,000원으로 동일 (표준 모듈 단가).
-- ============================================================
insert into item_catalogs (entity_id, task_type, module_name, is_required, item_name, standard_description, historical_ratio, sort_order) values
((select id from entity_templates where name = '알파브라더스'), '시장검증', 'FGI (심층좌담회)', false, 'BM 진단 및 고도화',
 '1. Business Model 9 Canvas 작성 및 분석 / 2. Value Curve 작성 및 분석 / 3. 디자인씽킹 기반의 BM 분석 / 4. 진단 결과 보고', 3.0, 1),
((select id from entity_templates where name = '알파브라더스'), '시장검증', 'FGI (심층좌담회)', false, '인터뷰이 모집',
 '1. 잠재고객 기반 특성과 유사한 인터뷰이 모집 (3~5인) / 2. 고객여정지도 분석 / 3. Macro/Micro 기반의 스크립트 작성 / 4. 그룹인터뷰 실시 / 5. 인터뷰 결과 보고서 제작', 27.0, 2),
((select id from entity_templates where name = '알파브라더스'), '시장검증', 'FGI (심층좌담회)', false, '인터뷰 스크립트 작성',
 '1. Macro/Micro 분석 스크립트 / 2. 기능적 관점의 Pain Point 및 Gain Point 도출 / 3. 경쟁사 비교 만족도 분석, NPS 지수 조사, 4대 가치별 만족도 조사', 54.0, 3),
((select id from entity_templates where name = '알파브라더스'), '시장검증', 'FGI (심층좌담회)', false, '인터뷰 진행',
 '1. 인터뷰 장소 대관 / 2. 2~3시간 인터뷰 진행 / 3. 모더레이터 및 스크립터 투입 및 운영', 12.0, 4),
((select id from entity_templates where name = '알파브라더스'), '시장검증', 'FGI (심층좌담회)', false, '결과 리포트 제공',
 '1. FGI 결과 및 분석 리포트 제작 / 2. 분석 결과 보고', 4.0, 5),

((select id from entity_templates where name = '알파브라더스'), '시장검증', '사용성 테스트', false, 'BM 진단 및 고도화',
 '1. Business Model 9 Canvas 작성 및 분석 / 2. Value Curve 작성 및 분석 / 3. 디자인씽킹 기반의 BM 분석 / 4. 진단 결과 보고', 3.0, 1),
((select id from entity_templates where name = '알파브라더스'), '시장검증', '사용성 테스트', false, '테스터 설계',
 '1. MVP TEST 플랫폼 내 모집, 체험, 데이터 수집 기간 시스템 설정 / 2. 기능별 설문지 기획 / 3. NPS, 4대 가치 만족도, 경쟁사 대비 우위·열위 영역 설문지 기획', 27.0, 2),
((select id from entity_templates where name = '알파브라더스'), '시장검증', '사용성 테스트', false, '일반테스터 모집',
 '1. B2C 제품 100명 내외 / B2B 제품 30명 내외 잠재고객 테스터 모집 / 2. MVP TEST 플랫폼을 통해 참석 의향 및 테스터 승인', 20.0, 3),
((select id from entity_templates where name = '알파브라더스'), '시장검증', '사용성 테스트', false, '테스트 운영',
 '1. 2주간 체험 기간 운영 / 2. 설문 참여율, 성실도 추적 관리 / 3. 리워드 보상 관리 / 4. 우수 테스터 선정', 20.0, 4),
((select id from entity_templates where name = '알파브라더스'), '시장검증', '사용성 테스트', false, '결과 리포트 제공',
 '1. 사용성테스트 결과 및 분석 리포트 제작 / 2. 분석 결과 보고', 30.0, 5),

((select id from entity_templates where name = '알파브라더스'), '시장검증', '기술성 테스트', false, 'BM 진단 및 고도화',
 '1. Business Model 9 Canvas 작성 및 분석 / 2. Value Curve 작성 및 분석 / 3. 디자인씽킹 기반의 BM 분석 / 4. 진단 결과 보고', 3.0, 1),
((select id from entity_templates where name = '알파브라더스'), '시장검증', '기술성 테스트', false, '기술성 테스트 설계',
 '1. 기능별 결함 발견 설문지 기획 / 2. 결함 수준별 카테고리화 설계', 15.0, 2),
((select id from entity_templates where name = '알파브라더스'), '시장검증', '기술성 테스트', false, '전문테스터 모집',
 '1. ISTQB 자격증 소지자 테스터 모집 / 2. SW개발 경력 10년 이상 테스터 모집 / 3. MVP TEST 플랫폼 내 모집 운영', 30.0, 3),
((select id from entity_templates where name = '알파브라더스'), '시장검증', '기술성 테스트', false, '1·2차 테스트 운영',
 '1. 오류 및 결함 발견 1차 테스트를 통한 150개 이상 도출 / 2. 개선 기간 이후 2차 결함 발견 및 진단 테스트', 42.0, 4),
((select id from entity_templates where name = '알파브라더스'), '시장검증', '기술성 테스트', false, '결과 리포트 제공',
 '1. 기술성테스트 결과 및 분석 리포트 제작 / 2. 분석 결과 보고', 10.0, 5);

-- 시장성 테스트: 실제 발급 샘플(고객사 "어니티", 견적일 2024.7.24, 공급가액 합계 5,000,000원) 기준.
insert into item_catalogs (entity_id, task_type, module_name, is_required, item_name, standard_description, historical_ratio, sort_order) values
((select id from entity_templates where name = '알파브라더스'), '시장검증', '시장성 테스트', false, 'BM 진단 및 고도화',
 '1. Business Model 9 Canvas 작성 및 분석 / 2. Value Curve 작성 및 분석 / 3. 디자인씽킹 기반의 BM 분석 / 4. 진단 결과 보고', 3.0, 1),
((select id from entity_templates where name = '알파브라더스'), '시장검증', '시장성 테스트', false, 'MVP 광고안 기획',
 '1. P-S-S-T 기반 Value Proposition MVP 기획 / 2. 15,000~20,000px, 3~4개 분량의 상세페이지 기획 / 3. MVP A/B 테스트 기반 3~4개 분량 썸네일 기획', 27.0, 2),
((select id from entity_templates where name = '알파브라더스'), '시장검증', '시장성 테스트', false, 'MVP 제작',
 '1. 3개 분량의 MVP 상세페이지 디자인 작업 / 2. 3개 분량의 MVP 썸네일 디자인 작업 / 3. MVP별 랜딩페이지 구축 / 4. GA 등 데이터 분석 Tool 구축', 48.0, 3),
((select id from entity_templates where name = '알파브라더스'), '시장검증', '시장성 테스트', false, '데이터 분석',
 '1. 페이스북, 인스타그램 광고 데이터 분석 / 2. 고관여자 설문 데이터 분석 / 3. 정성데이터(주관식 설문) 자연어 처리 / 4. 정량데이터 시각화 처리 / 5. 경쟁사 시장성데이터 비교 분석', 18.0, 4),
((select id from entity_templates where name = '알파브라더스'), '시장검증', '시장성 테스트', false, '결과 리포트 제공',
 '1. 시장성 데이터 분석 리포트 제작 / 2. 분석 결과 보고', 4.0, 5);

-- 통합 패키지: "견적서" 시트에 실제 번들 항목·단가가 있음 (BM진단 5M / FGI 10M / 사용성 10M / 기술성 10M / 시장성 15M = 50M)
insert into item_catalogs (entity_id, task_type, module_name, is_required, item_name, standard_description, historical_ratio, sort_order) values
((select id from entity_templates where name = '알파브라더스'), '시장검증', '통합 패키지', true, 'BM 진단 및 고도화',
 '1. Business Model 9 Canvas 작성 및 분석 / 2. Value Curve 작성 및 분석 / 3. 디자인씽킹 기반의 BM 분석 / 4. 진단 결과 보고', 10.0, 1),
((select id from entity_templates where name = '알파브라더스'), '시장검증', '통합 패키지', true, 'FGI (심층 그룹 인터뷰)',
 '1. 잠재고객 기반의 인터뷰이 6인 모집 / 2. 고객여정지도 분석 / 3. Macro/Micro 기반의 스크립트 작성 / 4. 그룹인터뷰 실시 / 5. 인터뷰 결과 보고서 제작', 20.0, 2),
((select id from entity_templates where name = '알파브라더스'), '시장검증', '통합 패키지', true, '사용성 테스트',
 '1. 잠재고객 기반의 사용성 테스터 100인 모집 / 2. 고객여정지도 분석 기반의 테스트 설계 / 3. 경쟁사 비교 만족도 분석, NPS 지수 조사, 4대 가치별 만족도 조사 / 4. 테스트 결과 보고', 20.0, 3),
((select id from entity_templates where name = '알파브라더스'), '시장검증', '통합 패키지', true, '기술성 테스트',
 '1. ISTQB 자격증 소지자 및 개발 경력 10년 이상 테스터 5인 모집 / 2. 오류 및 결함 발견 1차 테스트를 통한 150개 이상 도출 / 3. 개선 기간 이후 2차 결함 발견 및 진단 테스트 / 4. 진단 결과 보고', 20.0, 4),
((select id from entity_templates where name = '알파브라더스'), '시장검증', '통합 패키지', true, '시장성 테스트',
 '1. 진단 결과를 기반으로 MVP 가설 수립 / 2. MVP 광고안 제작 / 3. 메타 플랫폼 기반의 시장성 테스트 / 4. 시장성데이터 분석 및 결과보고', 30.0, 5);

-- ============================================================
-- 6.6 썬데이워커 — 항목 내용은 시장검증/마케팅 공유 카탈로그를 그대로 사용 (양식만 자체 템플릿)
-- ⚠️ 가정: PRD가 "6.1(시장검증)/6.2(마케팅) 카탈로그를 그대로 사용"이라고만 명시하고
--    마케팅의 경우 테스티파이/블렌디드랩 중 어느 버전인지 특정하지 않아, 더 상세한 테스티파이 버전을
--    기본 참조로 채택함 (사용자 확인 필요 — PRD 8장 질문 6 연장선).
-- ============================================================
insert into item_catalogs (entity_id, task_type, module_name, is_required, item_name, historical_ratio, shared_source_entity_id, sort_order) values
((select id from entity_templates where name = '썬데이워커'), '시장검증', '시장성 테스트', true,  'BM 진단 및 고도화',            5.6,  (select id from entity_templates where name = '테스티파이'), 1),
((select id from entity_templates where name = '썬데이워커'), '시장검증', '시장성 테스트', true,  'MVP 광고안 기획(및 제작)',      44.4, (select id from entity_templates where name = '테스티파이'), 2),
((select id from entity_templates where name = '썬데이워커'), '시장검증', '시장성 테스트', true,  '정량 데이터 시계열 분석',        22.2, (select id from entity_templates where name = '테스티파이'), 3),
((select id from entity_templates where name = '썬데이워커'), '시장검증', '시장성 테스트', true,  '정량 데이터 클러스터 분석',      22.2, (select id from entity_templates where name = '테스티파이'), 4),
((select id from entity_templates where name = '썬데이워커'), '시장검증', '시장성 테스트', true,  '결과 리포트 제공',              5.6,  (select id from entity_templates where name = '테스티파이'), 5),
((select id from entity_templates where name = '썬데이워커'), '시장검증', '설문형 시장검증', false, '설문 설계',                    5.6,  (select id from entity_templates where name = '테스티파이'), 1),
((select id from entity_templates where name = '썬데이워커'), '시장검증', '설문형 시장검증', false, '설문응답자 모집 및 운영 *리워드 포함', 44.4, (select id from entity_templates where name = '테스티파이'), 2),
((select id from entity_templates where name = '썬데이워커'), '시장검증', '설문형 시장검증', false, '설문 데이터 가공 및 시각화',      38.9, (select id from entity_templates where name = '테스티파이'), 3),
((select id from entity_templates where name = '썬데이워커'), '시장검증', '설문형 시장검증', false, '결과 리포트 제공',              11.1, (select id from entity_templates where name = '테스티파이'), 4);

insert into item_catalogs (entity_id, task_type, module_name, is_required, item_name, shared_source_entity_id, sort_order) values
((select id from entity_templates where name = '썬데이워커'), '마케팅', '온라인 광고',       true, '마케팅 전략안',                (select id from entity_templates where name = '테스티파이'), 1),
((select id from entity_templates where name = '썬데이워커'), '마케팅', '온라인 광고',       true, 'USP 설정 및 제안',             (select id from entity_templates where name = '테스티파이'), 2),
((select id from entity_templates where name = '썬데이워커'), '마케팅', '온라인 광고',       true, '이미지형 광고 소재 제작',        (select id from entity_templates where name = '테스티파이'), 3),
((select id from entity_templates where name = '썬데이워커'), '마케팅', '온라인 광고',       true, 'Meta 광고 세팅 및 운영',        (select id from entity_templates where name = '테스티파이'), 4),
((select id from entity_templates where name = '썬데이워커'), '마케팅', 'SEO 마케팅',        true, 'SEO 키워드 분석 및 제안',        (select id from entity_templates where name = '테스티파이'), 1),
((select id from entity_templates where name = '썬데이워커'), '마케팅', 'SEO 마케팅',        true, '테크니컬 SEO 최적화',           (select id from entity_templates where name = '테스티파이'), 2),
((select id from entity_templates where name = '썬데이워커'), '마케팅', 'SEO 마케팅',        true, 'SEO 성능 측정 및 보고',         (select id from entity_templates where name = '테스티파이'), 3),
((select id from entity_templates where name = '썬데이워커'), '마케팅', '자사몰 데이터 세팅', true, '자사몰 데이터 연결',            (select id from entity_templates where name = '테스티파이'), 1),
((select id from entity_templates where name = '썬데이워커'), '마케팅', '자사몰 데이터 세팅', true, 'GA4·GTM 데이터 연결',          (select id from entity_templates where name = '테스티파이'), 2),
((select id from entity_templates where name = '썬데이워커'), '마케팅', '자사몰 데이터 세팅', true, '대시보드 구축 및 데이터 시각화', (select id from entity_templates where name = '테스티파이'), 3),
((select id from entity_templates where name = '썬데이워커'), '마케팅', '그로스해킹',        true, '주간 단위 데이터 분석',         (select id from entity_templates where name = '테스티파이'), 1),
((select id from entity_templates where name = '썬데이워커'), '마케팅', '그로스해킹',        true, '주간 단위 액션플랜 수행',        (select id from entity_templates where name = '테스티파이'), 2);

-- ============================================================
-- 6.6 ABBG — [v0.4 삭제] "UXUI/디자인 제작"은 ABBG의 실제 취급 업무가 아니라 원본 파일의
-- 예시 내용이었음이 확인되어(2026-07-07) 카탈로그 시딩 대상에서 제외했다. 011 마이그레이션에서
-- 이미 적용된 DB의 해당 데이터를 삭제한다. ABBG의 실제 과업종류(마케팅/광고대행/고객검증/시장검증)
-- 카탈로그는 아직 미확보 상태 — Phase 4에서 타 법인 카탈로그 임시 차용으로 처리 (PRD 부록 B).
-- ============================================================

-- down
delete from item_catalogs;
