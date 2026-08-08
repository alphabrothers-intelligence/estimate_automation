-- up
-- 025에서 알파브라더스 전체를 quote_date_serial(숫자 일련번호)로 바꿨는데, "통합 패키지"
-- 모듈이 쓰는 "견적서" 시트만 다른 4개 시트(시장성테스트/FGI/사용성테스트/기술성테스트)와
-- 달리 D4 셀이 숫자 일련번호가 아니라 텍스트("2023.03.30")로 되어 있다(같은 파일 안에서도
-- 시트마다 원 작성자가 셀을 다르게 만들어 둔 것 — 실제로 값을 확인해서 발견함). 숫자를 써넣으면
-- 스타일이 안 맞아 서식 없이 raw 숫자가 그대로 찍힌다. 이 모듈만 quote_date(텍스트)로 되돌린다.
update quote_templates
set cell_map = jsonb_set(
    cell_map #- '{header_fields,quote_date_serial}',
    '{header_fields,quote_date}',
    cell_map->'header_fields'->'quote_date_serial'
)
where entity_id = (select id from entity_templates where name = '알파브라더스')
  and module_name = '통합 패키지'
  and cell_map->'header_fields' ? 'quote_date_serial';

-- down
update quote_templates
set cell_map = jsonb_set(
    cell_map #- '{header_fields,quote_date}',
    '{header_fields,quote_date_serial}',
    cell_map->'header_fields'->'quote_date'
)
where entity_id = (select id from entity_templates where name = '알파브라더스')
  and module_name = '통합 패키지'
  and cell_map->'header_fields' ? 'quote_date';
