-- up
-- 법인 1곳이라도 과업종류/모듈에 따라 시트·셀 좌표가 달라서(예: 알파브라더스는 한 파일 안에
-- 5개 시트가 각각 다른 모듈), 이 정보는 entity_templates(법인당 1행)에 담을 수 없다.
-- PRD 5장 데이터모델에는 없는 테이블이지만, "법인별 양식 관리"(PRD 4.2)를 실제 파일 기반으로
-- 구현하기 위해 반드시 필요해 추가한다 (2026-07-07).
create table quote_templates (
    id uuid primary key default gen_random_uuid(),
    entity_id uuid not null references entity_templates(id),
    task_type text not null,                 -- 과업종류 (item_catalogs.task_type과 동일 값 사용)
    module_name text,                        -- 모듈명 (item_catalogs.module_name과 동일 값 사용, 없으면 null)
    storage_path text not null,              -- 마스터 원본 파일 경로 (현재: backend/templates/*.xlsx, 추후: Supabase Storage 경로)
    sheet_name text not null,                -- 파일 내 시트명
    cell_map jsonb not null,                 -- 가변 셀 좌표 정의 (아래 007/010 주석의 구조 참고)
    created_at timestamptz not null default now(),

    unique (entity_id, task_type, module_name)
);

create index idx_quote_templates_lookup on quote_templates (entity_id, task_type);

comment on table quote_templates is
    '(법인×과업종류×모듈)별 마스터 원본 파일 경로 + 가변 셀 좌표 매핑. '
    '고정정보(사업자정보/로고/도장/문구)는 파일 안에 이미 있으므로 이 테이블은 절대 건드리지 않고, '
    'Phase 5에서 openpyxl로 cell_map이 가리키는 셀만 채운 뒤 LibreOffice headless로 PDF 변환한다.';

-- down
drop table if exists quote_templates;
