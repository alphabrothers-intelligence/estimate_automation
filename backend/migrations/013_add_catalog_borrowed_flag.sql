-- up
-- 견적 생성 시 이 법인×과업종류에 실제 카탈로그가 없어 다른 법인 카탈로그를 임시로 빌려썼는지
-- 투명하게 표시하기 위한 컬럼 (PRD 1.4/v0.4, 부록 B).
alter table entity_quotes
    add column is_catalog_borrowed boolean not null default false,
    add column catalog_source_entity_name text;

-- down
alter table entity_quotes
    drop column if exists is_catalog_borrowed,
    drop column if exists catalog_source_entity_name;
