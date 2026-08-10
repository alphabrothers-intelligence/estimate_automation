-- up
-- 견적서_자동화_PRD_v0.1.md 6.2 요구사항: 알파브라더스가 마케팅+시장검증을 함께 견적낼 때
-- 구분(대)/구분(중)을 과업종류별로 따로 보여줘야 한다. 기존 "견적서" 시트의 상품 블록은
-- 13~17행(5줄, 구분(대)/구분(중) 라벨 1개)뿐이라 두 과업종류를 한 블록에 같이 담을 수
-- 없었다 — backend/templates/alphabrothers.xlsx를 직접 열어 13~17행 블록을 복제해
-- 18~22행에 새 블록을 추가했다(합계 수식·은행 조회 수식·인쇄영역 등 아래 내용은 전부 5행씩
-- 밀어서 다시 계산, LibreOffice 렌더링으로 한 페이지 안에 들어오는 것까지 확인함).
-- 이 마이그레이션은 그 새 블록을 cell_map에 반영한다 — 과업종류가 1개뿐이면 pdf_service가
-- 첫 번째 블록만 쓰고 두 번째 블록은 자동으로 숨겨져 기존 출력과 동일하다.
update quote_templates
set cell_map = jsonb_set(
    cell_map,
    '{item_blocks}',
    '[
        {"category_large_cell": "A13", "category_mid_cell": "C13", "rows": [13, 14, 15, 16, 17]},
        {"category_large_cell": "A18", "category_mid_cell": "C18", "rows": [18, 19, 20, 21, 22]}
    ]'::jsonb
)
where entity_id = (select id from entity_templates where name = '알파브라더스')
  and sheet_name = '견적서';

-- down
update quote_templates
set cell_map = jsonb_set(
    cell_map,
    '{item_blocks}',
    '[
        {"category_large_cell": "A13", "category_mid_cell": "C13", "rows": [13, 14, 15, 16, 17]}
    ]'::jsonb
)
where entity_id = (select id from entity_templates where name = '알파브라더스')
  and sheet_name = '견적서';
