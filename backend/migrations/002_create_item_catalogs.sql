-- up
create table item_catalogs (
    id uuid primary key default gen_random_uuid(),
    entity_id uuid not null references entity_templates(id),
    task_type text not null,                        -- 과업종류 (예: 시장검증, 마케팅, 광고대행, 고객검증, UXUI/디자인 제작)
    module_name text,                                -- 모듈명 (예: "설문형 시장검증", "미러링형"). 단일 모듈이면 null
    is_required boolean not null default true,       -- 필수여부 (옵션 모듈 판단용)
    item_name text not null,
    standard_description text,                       -- 표준 상품구성 설명
    historical_ratio numeric(6,3),                   -- 과거 비중(%). 데이터 없으면 null
    shared_source_entity_id uuid references entity_templates(id), -- 공유출처 법인 (예: 썬데이워커 → 테스티파이)
    sort_order integer not null default 0,
    version_no integer not null default 1,           -- 카탈로그 버전 (PRD 4.6 — 마스터 데이터도 이력 관리)
    is_current boolean not null default true,
    created_at timestamptz not null default now()
);

create index idx_item_catalogs_lookup
    on item_catalogs (entity_id, task_type, is_current);

comment on table item_catalogs is '법인×과업종류별 표준 항목 카탈로그 — 마스터 데이터, 세트와 별개로 관리 (PRD 5장)';

-- down
drop table if exists item_catalogs;
