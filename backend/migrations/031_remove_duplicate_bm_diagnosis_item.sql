-- up
-- 사용자 결정(2026-08-10): 시장검증의 4개 모듈(FGI/사용성 테스트/기술성 테스트/시장성 테스트)이
-- 030 마이그레이션으로 5개 법인 전체에 동일하게 복제되면서, "BM 진단 및 고도화"가 4개 모듈
-- 전부에 첫 세부항목으로 중복 등장하는 게 눈에 띄었다 — 실제로는 "시장성 테스트" 모듈에만
-- 남기고 나머지 3개 모듈에서는 세부항목에서 뺀다.
--
-- "통합 패키지"(알파브라더스 고유 번들 상품, 030에서 표준 카탈로그 복제 대상에서 제외됨)의
-- "BM 진단 및 고도화" 행은 이번 삭제 대상에서 제외했다 — 그 항목은 번들 5개 구성요소 중
-- 하나로 실제 원본 "견적서" 시트 금액(5,000,000원/10%)에 대응하는 별도 성격이라, 이번
-- 요청(모듈 간 중복 정리)과 범위가 다르다고 판단했다. 필요하면 사용자 확인 후 별도로 처리한다.
delete from item_catalogs
where task_type = '시장검증'
  and module_name in ('FGI (심층좌담회)', '사용성 테스트', '기술성 테스트')
  and item_name = 'BM 진단 및 고도화';

-- down
insert into item_catalogs (entity_id, task_type, module_name, is_required, item_name, standard_description, historical_ratio, alt_group, sort_order) values
((select id from entity_templates where name = '테스티파이'),   '시장검증', 'FGI (심층좌담회)', false, 'BM 진단 및 고도화',
 '1. Business Model 9 Canvas 작성 및 분석 / 2. Value Curve 작성 및 분석 / 3. 디자인씽킹 기반의 BM 분석 / 4. 진단 결과 보고', 3.0, 'FGI', 1),
((select id from entity_templates where name = '블렌디드랩'),   '시장검증', 'FGI (심층좌담회)', false, 'BM 진단 및 고도화',
 '1. Business Model 9 Canvas 작성 및 분석 / 2. Value Curve 작성 및 분석 / 3. 디자인씽킹 기반의 BM 분석 / 4. 진단 결과 보고', 3.0, 'FGI', 1),
((select id from entity_templates where name = '썬데이워커'),   '시장검증', 'FGI (심층좌담회)', false, 'BM 진단 및 고도화',
 '1. Business Model 9 Canvas 작성 및 분석 / 2. Value Curve 작성 및 분석 / 3. 디자인씽킹 기반의 BM 분석 / 4. 진단 결과 보고', 3.0, 'FGI', 1),
((select id from entity_templates where name = 'ABBG'),        '시장검증', 'FGI (심층좌담회)', false, 'BM 진단 및 고도화',
 '1. Business Model 9 Canvas 작성 및 분석 / 2. Value Curve 작성 및 분석 / 3. 디자인씽킹 기반의 BM 분석 / 4. 진단 결과 보고', 3.0, 'FGI', 1),
((select id from entity_templates where name = '알파브라더스'), '시장검증', 'FGI (심층좌담회)', false, 'BM 진단 및 고도화',
 '1. Business Model 9 Canvas 작성 및 분석 / 2. Value Curve 작성 및 분석 / 3. 디자인씽킹 기반의 BM 분석 / 4. 진단 결과 보고', 3.0, 'FGI', 1),

((select id from entity_templates where name = '테스티파이'),   '시장검증', '사용성 테스트', false, 'BM 진단 및 고도화',
 '1. Business Model 9 Canvas 작성 및 분석 / 2. Value Curve 작성 및 분석 / 3. 디자인씽킹 기반의 BM 분석 / 4. 진단 결과 보고', 3.0, '사용성테스트', 1),
((select id from entity_templates where name = '블렌디드랩'),   '시장검증', '사용성 테스트', false, 'BM 진단 및 고도화',
 '1. Business Model 9 Canvas 작성 및 분석 / 2. Value Curve 작성 및 분석 / 3. 디자인씽킹 기반의 BM 분석 / 4. 진단 결과 보고', 3.0, '사용성테스트', 1),
((select id from entity_templates where name = '썬데이워커'),   '시장검증', '사용성 테스트', false, 'BM 진단 및 고도화',
 '1. Business Model 9 Canvas 작성 및 분석 / 2. Value Curve 작성 및 분석 / 3. 디자인씽킹 기반의 BM 분석 / 4. 진단 결과 보고', 3.0, '사용성테스트', 1),
((select id from entity_templates where name = 'ABBG'),        '시장검증', '사용성 테스트', false, 'BM 진단 및 고도화',
 '1. Business Model 9 Canvas 작성 및 분석 / 2. Value Curve 작성 및 분석 / 3. 디자인씽킹 기반의 BM 분석 / 4. 진단 결과 보고', 3.0, '사용성테스트', 1),
((select id from entity_templates where name = '알파브라더스'), '시장검증', '사용성 테스트', false, 'BM 진단 및 고도화',
 '1. Business Model 9 Canvas 작성 및 분석 / 2. Value Curve 작성 및 분석 / 3. 디자인씽킹 기반의 BM 분석 / 4. 진단 결과 보고', 3.0, '사용성테스트', 1),

((select id from entity_templates where name = '테스티파이'),   '시장검증', '기술성 테스트', false, 'BM 진단 및 고도화',
 '1. Business Model 9 Canvas 작성 및 분석 / 2. Value Curve 작성 및 분석 / 3. 디자인씽킹 기반의 BM 분석 / 4. 진단 결과 보고', 3.0, '기술성테스트', 1),
((select id from entity_templates where name = '블렌디드랩'),   '시장검증', '기술성 테스트', false, 'BM 진단 및 고도화',
 '1. Business Model 9 Canvas 작성 및 분석 / 2. Value Curve 작성 및 분석 / 3. 디자인씽킹 기반의 BM 분석 / 4. 진단 결과 보고', 3.0, '기술성테스트', 1),
((select id from entity_templates where name = '썬데이워커'),   '시장검증', '기술성 테스트', false, 'BM 진단 및 고도화',
 '1. Business Model 9 Canvas 작성 및 분석 / 2. Value Curve 작성 및 분석 / 3. 디자인씽킹 기반의 BM 분석 / 4. 진단 결과 보고', 3.0, '기술성테스트', 1),
((select id from entity_templates where name = 'ABBG'),        '시장검증', '기술성 테스트', false, 'BM 진단 및 고도화',
 '1. Business Model 9 Canvas 작성 및 분석 / 2. Value Curve 작성 및 분석 / 3. 디자인씽킹 기반의 BM 분석 / 4. 진단 결과 보고', 3.0, '기술성테스트', 1),
((select id from entity_templates where name = '알파브라더스'), '시장검증', '기술성 테스트', false, 'BM 진단 및 고도화',
 '1. Business Model 9 Canvas 작성 및 분석 / 2. Value Curve 작성 및 분석 / 3. 디자인씽킹 기반의 BM 분석 / 4. 진단 결과 보고', 3.0, '기술성테스트', 1);
