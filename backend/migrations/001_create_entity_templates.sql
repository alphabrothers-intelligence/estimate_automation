-- up
create extension if not exists pgcrypto;

-- 법인 고정정보(사업자등록번호/대표자/주소/로고/도장/고정문구 등)는 DB에 별도로 중복 저장하지 않는다.
-- 실제 법인별 마스터 xlsx 원본 파일 안에 이미 값·이미지가 박혀 있고, 우리 로직은 그 파일을 절대 건드리지
-- 않기 때문 (2026-07-07 결정 — quote_templates 테이블, 009 참고). entity_templates는 법인을 가리키는
-- 얇은 참조 키 역할만 한다. 화면에 법인 정보를 표시해야 하는 등 필요가 생기면 그때 컬럼을 추가한다.
create table entity_templates (
    id uuid primary key default gen_random_uuid(),
    name text not null unique,          -- 법인 짧은 이름 (예: 테스티파이) — 카탈로그/템플릿 참조 키
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

comment on table entity_templates is '법인 참조 키 — 고정정보 자체는 quote_templates가 가리키는 마스터 xlsx 안에 있음 (PRD 4.2)';

-- down
drop table if exists entity_templates;
