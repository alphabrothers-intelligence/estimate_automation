-- up
-- 알파브라더스(D4)·썬데이워커(D6)의 견적일자 셀은 원본에서 엑셀 날짜 일련번호(예: 45397)로
-- 되어 있어 셀 서식이 알아서 날짜 형태로 보여준다. pdf_service._collect_header_updates가
-- 지금까지 여기에 ISO 문자열("2026-08-06")을 써 넣어 서식이 무시되고 엉뚱하게 찍혔다.
-- header_fields 키를 quote_date_serial로 바꿔, 문자열 대신 일련번호(숫자)를 쓰도록
-- 분기한다(ABBG는 D3 셀 자체가 "YYYY-MM-DD" 텍스트 플레이스홀더라 기존 quote_date를 그대로 둔다).
update quote_templates
set cell_map = jsonb_set(
    cell_map #- '{header_fields,quote_date}',
    '{header_fields,quote_date_serial}',
    cell_map->'header_fields'->'quote_date'
)
where entity_id in (select id from entity_templates where name in ('알파브라더스', '썬데이워커'))
  and cell_map->'header_fields' ? 'quote_date';

-- down
update quote_templates
set cell_map = jsonb_set(
    cell_map #- '{header_fields,quote_date_serial}',
    '{header_fields,quote_date}',
    cell_map->'header_fields'->'quote_date_serial'
)
where entity_id in (select id from entity_templates where name in ('알파브라더스', '썬데이워커'))
  and cell_map->'header_fields' ? 'quote_date_serial';
