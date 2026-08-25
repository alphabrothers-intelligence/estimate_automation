-- up
-- 비교견적서 품명을 AI가 다시 쓸지 실무자가 고른다 (2026-08-25 요청).
--
-- 지금은 항상 다시 쓴다. 그런데 실무에서 갈리는 상황이 셋이다:
--   1) 다시 쓴 결과에 "보고서 발건", "데이터 해석" 같은 어색한 말이 섞인다.
--   2) 품목이 조금씩 달라야 하는 건이면 그 어색함을 대체로 신경 쓰지 않는다.
--   3) 반대로 품명이 본견적과 완전히 같아야 하는 건도 있다.
-- 어느 쪽이 맞는지는 건마다 다르므로 코드가 정하지 않고 체크박스 하나로 넘긴다.
--
-- true(기본값)  = 지금 동작 그대로. 구분·품명·상품구성을 다른 표현으로 다시 쓴다.
-- false        = 본견적 문구를 그대로 두고 금액만 이 양식·인상률에 맞춰 다시 잡는다.
alter table entity_quotes
    add column if not exists rename_items boolean not null default true;

comment on column entity_quotes.rename_items is
    '비교견적서 전용 — 품명·구분·상품구성을 AI가 다른 표현으로 바꿀지 여부. false면 본견적 '
    '문구를 그대로 쓰고 금액만 다시 산정한다. 본견적서(is_primary=true) 행에서는 의미가 없다.';

-- down
alter table entity_quotes drop column if exists rename_items;
