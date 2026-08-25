-- up
-- 용역 사업(대학·공공 발주) 견적서에 들어가는 간접비 3종을 선택 과업으로 추가한다.
-- 근거는 실제 발급본 "(테스티파이) 한양대학교 시장검증 프로그램_견적서(수정안)" —
-- 원본 xlsx는 남아 있지 않아 PDF를 보고 옮겼다(2026-08-24 사용자 확인).
--
-- 그 견적서의 구조와 숫자:
--   (4) 경비        600,000   ├ 교통비(수요처별 2회 방문) 30,000 × 2명 × 2회 × 3기업 = 360,000
--                             └ 회의 및 기타경비          20,000 × 4명 × 3회        = 240,000
--   (6) 일반관리비  387,000   합계의 3.0%   (양식 비고: "5% 이내")
--   (7) 이윤        349,364   합계의 2.629365%  (양식 비고: "10% 이내")
--
-- 이윤의 2.629365%라는 소수점 여섯 자리가 이 모듈의 존재 이유를 그대로 보여준다 — 총액을
-- 15,000,000원에 정확히 떨어뜨리려고 역산한 값이다. 사용자가 말한 목적이 이것이다:
-- "각 과업의 단가를 낮추고, 딱 떨어지게 맞추기 위함". 직접비 항목을 억지로 흔들지 않고
-- 이윤 한 줄이 잔액을 먹는다.
--
-- is_required=false + alt_group=null → 추가 옵션(체크박스) 그룹으로 노출된다
-- (catalog_service.get_module_options). 용역 사업이 아닌 견적서에는 얹지 않는다.

insert into item_catalogs (
    entity_id, task_type, module_name, is_required, item_name, standard_description,
    unit_price, work_days, quantity, alt_group, sort_order
)
select e.id, t.task_type, '경비 및 간접비', false, i.item_name, i.standard_description,
       i.unit_price, 1, i.quantity, null, i.sort_order
from entity_templates e
cross join (values ('시장검증'), ('마케팅'), ('광고대행')) as t(task_type)
cross join (values
    ('교통비 (수요처별 방문 기준)',
     '1. 수요처 방문 왕복 교통비\n2. 방문 인원·횟수·수요처 수를 곱한 실비 기준\n3. 수요처당 출장비 포함',
     30000, 12, 1),
    ('회의 및 기타경비',
     '1. 정기 회의 진행에 드는 실비\n2. 회의 인원·횟수 기준\n3. 인쇄·소모품 등 기타경비 포함',
     20000, 12, 2),
    ('일반관리비',
     '1. 직접비 합계에 요율을 곱한 간접비\n2. 통상 3% 내외로 산정하며 5%를 넘기지 않음',
     387000, 1, 3),
    ('이윤',
     '1. 직접비와 일반관리비 합계에 요율을 곱한 이윤\n2. 10% 이내에서 산정\n3. 총액을 맞추기 위한 조정 항목 — 요율은 정수로 떨어지지 않아도 된다',
     349364, 1, 4)
) as i(item_name, standard_description, unit_price, quantity, sort_order)
where e.name in ('테스티파이', '알파브라더스', '블렌디드랩', '썬데이워커', 'ABBG');

-- down
delete from item_catalogs where module_name = '경비 및 간접비';
