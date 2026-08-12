-- up
alter table entity_quotes
    add column markup_ratio numeric(8,4);

comment on column entity_quotes.markup_ratio is
    '비교견적서 전용 — 본견적서 총액 대비 현재 배율(예: 1.1000 = 110%). 본견적서(is_primary=true) '
    '행은 항상 null. 비교견적 최초 생성 시 COMPARISON_MARKUP(기본 1.10)으로 채워지고, 이후 그 '
    '비교견적을 직접 수정할 때마다 (새 총액 / 본견적 총액)으로 갱신된다. 본견적을 수정하면 이 '
    '배율을 유지한 채 비교견적 금액이 따라 움직인다 (PRD 8장 미해결 질문 3번 답, 2026-08-11 사용자 결정).';

-- 정합성: 본견적서 행은 배율 개념이 없으므로 markup_ratio가 항상 null이어야 한다.
-- (비교견적 행은 최초 생성 전엔 null일 수 있어 not null 제약은 걸지 않는다.)
alter table entity_quotes
    add constraint chk_entity_quotes_primary_no_markup_ratio
    check (not is_primary or markup_ratio is null);

-- 이미 생성된 비교견적서들도 배율을 채워둔다: 같은 세트의 본견적 총액 대비 현재 총액 비율로 백필.
-- 본견적이 없는 세트(비교견적만 발급된 세트)의 비교견적은 배율을 정할 기준이 없어 null로 남긴다.
update entity_quotes eq
set markup_ratio = eq.total_amount / p.total_amount
from entity_quotes p
where p.estimate_set_id = eq.estimate_set_id
  and p.is_primary = true
  and eq.is_primary = false
  and p.total_amount > 0;

-- down
alter table entity_quotes
    drop constraint if exists chk_entity_quotes_primary_no_markup_ratio;
alter table entity_quotes
    drop column if exists markup_ratio;
