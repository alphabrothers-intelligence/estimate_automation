-- up
-- 견적서 생성 마법사 개편: 기업 1곳이 과업종류를 여러 개 선택하면 그 기업 몫으로
-- entity_quote row가 과업종류별로 여러 개 생긴다(예: 테스티파이가 마케팅+시장검증을
-- 고르면 2 row). 본견적 기업의 row는 전부 is_primary=true가 되어야 하는데, 기존
-- "세트당 is_primary=true row 정확히 1개" 유니크 인덱스가 이를 막는다. "본견적은 기업
-- 1곳"이라는 진짜 제약은 estimate_sets.primary_entity_id(단일 FK)가 그대로 지킨다.
drop index if exists idx_entity_quotes_one_primary_per_set;

-- down
create unique index idx_entity_quotes_one_primary_per_set
    on entity_quotes (estimate_set_id)
    where is_primary;
