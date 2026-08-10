-- up
-- 034에서 "견적서" 시트에 두 번째 상품 블록(18~22행)을 끼워넣으면서 기존 18행(부가세·공급가액
-- 합계)은 23행으로 밀렸는데, 034는 item_blocks만 고치고 totals.vat_cell/supply_total_cell은
-- 예전 좌표(E18/T18)로 그대로 남겨뒀다 — 그 결과 두 번째 블록의 18행(구분(대)="시장검증"
-- 등 실제 상품 데이터)이 채워진 직후, 합계 계산이 그 같은 셀(E18/T18)에 부가세·공급가액
-- 합계 숫자를 덮어써 상품명·작업일 칸에 엉뚱한 큰 숫자가 찍히는 버그로 이어졌다
-- (2026-08-10 실제 발급 재현·확인). 새 행 위치(E23/T23)로 맞춘다.
update quote_templates
set cell_map = jsonb_set(
    jsonb_set(cell_map, '{totals,vat_cell}', '"E23"'::jsonb),
    '{totals,supply_total_cell}', '"T23"'::jsonb
)
where entity_id = (select id from entity_templates where name = '알파브라더스')
  and sheet_name = '견적서';

-- down
update quote_templates
set cell_map = jsonb_set(
    jsonb_set(cell_map, '{totals,vat_cell}', '"E18"'::jsonb),
    '{totals,supply_total_cell}', '"T18"'::jsonb
)
where entity_id = (select id from entity_templates where name = '알파브라더스')
  and sheet_name = '견적서';
