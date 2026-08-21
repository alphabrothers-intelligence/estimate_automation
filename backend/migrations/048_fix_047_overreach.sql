-- up
-- 047 과잉 적용 정정. 알파브라더스는 시트마다 수식이 다르다:
--   · 모듈 시트(FGI/사용성/기술성/시장성)  = SUM(작업일 × 수량 × 단가)  → 작업일 흡수 필요
--   · "통합 패키지" 시트(견적서)          = SUM(수량 × 단가)          → 원래부터 규칙과 같음
-- 047이 법인 전체에 곱해서 통합 패키지 단가가 작업일 배만큼 부풀었다(사용성 테스트
-- 5,000,000 → 150,000,000). 그 모듈만 되돌린다.
update item_catalogs c
set unit_price = round(c.unit_price / c.work_days)
from entity_templates e
where c.entity_id = e.id
  and e.name = '알파브라더스'
  and c.module_name = '통합 패키지'
  and c.unit_price is not null
  and c.work_days is not null
  and c.work_days <> 1;

-- down
-- (047과 함께 되돌린다)
