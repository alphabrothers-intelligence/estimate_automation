-- up
create table entity_quotes (
    id uuid primary key default gen_random_uuid(),
    estimate_set_id uuid not null references estimate_sets(id) on delete cascade,
    entity_id uuid not null references entity_templates(id),
    is_primary boolean not null default false,       -- 본견적서 여부 (세트 내 정확히 1개만 true)
    task_type text not null,                         -- 본견적서와 다를 수 있음 (비교견적 카테고리 변경 지원)
    recipient_name text,                             -- 수신자(고객사명)
    quote_date date,
    service_name text,                               -- 용역명
    total_amount numeric(14,2) not null,
    line_items jsonb not null default '[]'::jsonb,   -- 항목/단가/수량/부가세/상품구성설명
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- 세트 내 본견적서는 정확히 1개만 존재해야 함
create unique index idx_entity_quotes_one_primary_per_set
    on entity_quotes (estimate_set_id)
    where is_primary;

create index idx_entity_quotes_set on entity_quotes (estimate_set_id);

comment on table entity_quotes is '법인별 견적서, 세트당 N개 — 건별 가변정보 (PRD 5장)';

-- down
drop table if exists entity_quotes;
