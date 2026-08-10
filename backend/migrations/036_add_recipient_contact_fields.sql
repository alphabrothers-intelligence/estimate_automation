-- up
-- ABBG 마스터(templates/abbg.xlsx)에는 이미 담당자/연락처/이메일 칸(cell_map.header_fields의
-- client_contact/client_phone/client_email)이 있었지만, entity_quotes에 대응하는 컬럼이 없어
-- 실제로는 아무것도 채워지지 않고 있었다(2026-08-10 발견). recipient_name과 같은 방식으로
-- estimate_sets 단계에서 한 번 입력받아 모든 entity_quote에 복사한다.
alter table entity_quotes
    add column recipient_contact text,
    add column recipient_phone text,
    add column recipient_email text;

-- down
alter table entity_quotes
    drop column recipient_contact,
    drop column recipient_phone,
    drop column recipient_email;
