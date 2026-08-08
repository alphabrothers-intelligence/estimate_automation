-- up
-- selected_modules: 항목 자동생성 시 PM이 고른 module_name 목록 (PRD 7장 3~4단계, 옵션 모듈 선택).
--   카탈로그가 단일 모듈(module_name이 전부 null)이면 항상 null.
-- (service_name 컬럼은 004_create_entity_quotes.sql에서 이미 생성됨 — 지금까지 미사용이었을 뿐)
alter table entity_quotes
    add column selected_modules jsonb;

-- down
alter table entity_quotes
    drop column if exists selected_modules;
