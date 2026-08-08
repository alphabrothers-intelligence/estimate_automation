-- up
create table quote_versions (
    id uuid primary key default gen_random_uuid(),
    entity_quote_id uuid not null references entity_quotes(id) on delete cascade,
    version_no integer not null,
    edit_request_text text,                          -- 수정요청 원문 (채팅로그 또는 "직접편집" 표기)
    diff jsonb,                                       -- 변경내역
    edited_by text,                                   -- 수정자 (현재 인증 미도입 — 자유 텍스트/null)
    edited_at timestamptz not null default now(),
    internal_pdf_path text,                          -- 내부용 PDF 경로
    customer_pdf_path text,                          -- 고객발송용 PDF 경로
    created_at timestamptz not null default now(),
    unique (entity_quote_id, version_no)
);

create index idx_quote_versions_entity_quote on quote_versions (entity_quote_id);

comment on table quote_versions is '수정 이력 — 채팅 수정/직접 편집 모두 기록 (PRD 4.4, 5장)';

-- down
drop table if exists quote_versions;
