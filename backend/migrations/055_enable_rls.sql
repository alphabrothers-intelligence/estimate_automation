-- up
-- 2026-10-06 Supabase 보안 경고(rls_disabled_in_public) 대응.
-- public 스키마 테이블은 Supabase 공개 API로 노출되는데 RLS가 꺼져 있어, 공개 키(publishable/anon)만
-- 있으면 누구나 견적 데이터를 읽고·고치고·지울 수 있었다.
-- RLS만 켜고 정책은 하나도 만들지 않는다 — 공개 키 접근은 전부 막히고, 백엔드는 secret key
-- (RLS 우회)로 접속하므로(app/config.py) 동작이 그대로다. migrate.py는 DATABASE_URL의 postgres
-- 소유자 계정이라 역시 영향 없다.
-- 새 테이블을 만드는 마이그레이션은 같은 파일에서 RLS도 켜야 한다.

alter table entity_templates  enable row level security;
alter table estimate_sets     enable row level security;
alter table entity_quotes     enable row level security;
alter table quote_versions    enable row level security;
alter table item_catalogs     enable row level security;
alter table quote_templates   enable row level security;
alter table schema_migrations enable row level security;

-- down
alter table entity_templates  disable row level security;
alter table estimate_sets     disable row level security;
alter table entity_quotes     disable row level security;
alter table quote_versions    disable row level security;
alter table item_catalogs     disable row level security;
alter table quote_templates   disable row level security;
alter table schema_migrations disable row level security;
