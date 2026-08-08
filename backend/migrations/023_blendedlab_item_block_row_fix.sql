-- up
-- 블렌디드랩 마스터의 항목 블록은 13~16행 4줄인데(합계 수식이 SUM(AB13:AF16)*1.1로 4행을
-- 참조함, 16행도 13~15행과 동일한 셀 서식을 가진 빈 4번째 항목행으로 확인됨), 원래
-- cell_map에는 13~15행 3줄만 들어있었다 — .xls라 PDF 발급이 막혀있어 지금까지 발견되지
-- 못한 버그. 실제 마케팅 카탈로그가 4개 항목(온라인 마케팅/퍼포먼스 마케팅/자사몰 데이터
-- 세팅/그로스해킹)이라 xlsx 변환 후 첫 발급 시도에서 "담을 곳이 없다" 오류로 드러났다.
update quote_templates
set cell_map = jsonb_set(
    cell_map,
    '{item_blocks,0,rows}',
    '[13, 14, 15, 16]'::jsonb
)
where entity_id = (select id from entity_templates where name = '블렌디드랩');

-- down
update quote_templates
set cell_map = jsonb_set(
    cell_map,
    '{item_blocks,0,rows}',
    '[13, 14, 15]'::jsonb
)
where entity_id = (select id from entity_templates where name = '블렌디드랩');