-- up
-- 본견적서/비교견적서 둘 다 선택사항으로 바꾼다(2026-07-10 사용자 결정) — "비교견적서만 러프하게
-- 발행"해야 하는 실제 업무 상황 대응. 최소 한쪽은 있어야 한다는 제약은 API 레벨(pydantic
-- model_validator)에서 검증하고, DB는 단순히 NULL을 허용하도록만 푼다.
alter table estimate_sets
    alter column primary_entity_id drop not null;

-- down
alter table estimate_sets
    alter column primary_entity_id set not null;