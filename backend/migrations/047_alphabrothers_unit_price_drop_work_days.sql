-- up
-- 금액 규칙 통일: 모든 법인이 "공급가액 = 단가 × 수량"이고 작업일은 금액과 무관한 정보성 값이다
-- (2026-08-21 사용자 확정). 알파브라더스만 마스터 원본 수식이 SUM(작업일×수량×단가)라서
-- 마이그레이션 044가 단가를 "공급가액 ÷ (작업일×수량)"으로 넣어 놨다 — 작업일이 빠지면
-- 그 단가는 작업일 배만큼 작다.
--
-- 단가에 작업일을 곱해 흡수시키면 금액이 그대로 보존된다:
--   기존: 단가 × 작업일 × 수량
--   신규: (단가 × 작업일) × 수량   ← 같은 값
-- 그래서 실제 발급본 금액은 이 마이그레이션 전후로 달라지지 않는다. 22행 중 14행이 대상
-- (작업일이 1이 아닌 행).
update item_catalogs c
set unit_price = round(c.unit_price * c.work_days)
from entity_templates e
where c.entity_id = e.id
  and e.name = '알파브라더스'
  and c.unit_price is not null
  and c.work_days is not null
  and c.work_days <> 1;

-- down
-- update item_catalogs c set unit_price = round(c.unit_price / c.work_days)
-- from entity_templates e where c.entity_id = e.id and e.name = '알파브라더스'
--   and c.unit_price is not null and c.work_days is not null and c.work_days <> 1;
