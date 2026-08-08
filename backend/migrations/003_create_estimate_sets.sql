-- up
create table estimate_sets (
    id uuid primary key default gen_random_uuid(),
    project_name text not null,                      -- 사업명
    total_amount numeric(14,2) not null,
    vat_included boolean not null,                   -- VAT포함여부
    task_type text not null,                         -- 과업종류 (본견적서 기준)
    primary_entity_id uuid not null references entity_templates(id), -- 본견적서_법인 (PM이 지정)
    created_at timestamptz not null default now()
);

comment on table estimate_sets is '견적 세트 = 사업 건 1개 (PRD 5장)';

-- down
drop table if exists estimate_sets;
