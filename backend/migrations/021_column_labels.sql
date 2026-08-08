-- up
-- 미리보기 UI 컬럼 라벨을 법인마다 실제 원본 양식 그대로 보여주기 위해 추가한다(2026-07-10 사용자
-- 지적 — 의미는 같아도 법인마다 실제 컬럼 명칭이 다름: 예) 작업일/소요일, 수량/작업수량,
-- 공급가액/금액(부가세 별도)). 값은 각 법인 실제 발급 샘플(브릿지오 시장검증 견적서_260616,
-- 직접 생성해 확인한 알파브라더스/ABBG PDF, 미구 마케팅 견적서_260424_수정)에서 그대로 확인한
-- 텍스트다. detail_column_order는 단가/작업일/수량 3개 컬럼의 실제 표시 순서 — 테스티파이만
-- 단가→작업일→투입 인력 순이고 나머지는 작업일→수량→단가 순이다.

-- 테스티파이 (시장검증/마케팅 공용)
update quote_templates
set cell_map = cell_map
    || jsonb_build_object(
        'column_labels', jsonb_build_object(
            'item_name', '항목',
            'unit_price', '단가(원)',
            'work_days', '작업일',
            'quantity', '투입 인력',
            'supply_amount', '공급가액(원)',
            'note', '비고'
        ),
        'detail_column_order', jsonb_build_array('unit_price', 'work_days', 'quantity')
    )
where entity_id = (select id from entity_templates where name = '테스티파이');

-- 알파브라더스 (5개 모듈 시트 전부 동일 라벨)
update quote_templates
set cell_map = cell_map
    || jsonb_build_object(
        'column_labels', jsonb_build_object(
            'item_name', '상품명',
            'unit_price', '단가',
            'work_days', '작업일',
            'quantity', '수량',
            'description', '상품구성',
            'supply_amount', '공급가액'
        ),
        'detail_column_order', jsonb_build_array('work_days', 'quantity', 'unit_price')
    )
where entity_id = (select id from entity_templates where name = '알파브라더스');

-- ABBG (마케팅/광고대행/시장검증 공용 — 같은 라벨인데 알파브라더스와 명칭이 다름에 유의)
update quote_templates
set cell_map = cell_map
    || jsonb_build_object(
        'column_labels', jsonb_build_object(
            'item_name', '상품명',
            'unit_price', '단가',
            'work_days', '소요일',
            'quantity', '작업수량',
            'description', '상세내용',
            'supply_amount', '공급가액'
        ),
        'detail_column_order', jsonb_build_array('work_days', 'quantity', 'unit_price')
    )
where entity_id = (select id from entity_templates where name = 'ABBG');

-- 썬데이워커 (시장검증/마케팅/광고대행 공용 — work_days 컬럼 자체가 없음)
update quote_templates
set cell_map = cell_map
    || jsonb_build_object(
        'column_labels', jsonb_build_object(
            'item_name', '품명',
            'unit_price', '단가',
            'quantity', '수량',
            'input_mm', '투입 MM',
            'supply_amount', '공급가액',
            'tax_amount', '세액'
        ),
        'detail_column_order', jsonb_build_array('quantity', 'unit_price')
    )
where entity_id = (select id from entity_templates where name = '썬데이워커');

-- 블렌디드랩 (마케팅/광고대행/시장검증 공용 — 공급가액이 아니라 "금액(부가세 별도)")
update quote_templates
set cell_map = cell_map
    || jsonb_build_object(
        'column_labels', jsonb_build_object(
            'item_name', '품명',
            'unit_price', '단가',
            'work_days', '작업일',
            'quantity', '수량',
            'amount', '금액(부가세 별도)'
        ),
        'detail_column_order', jsonb_build_array('work_days', 'quantity', 'unit_price')
    )
where entity_id = (select id from entity_templates where name = '블렌디드랩');

-- down
update quote_templates
set cell_map = cell_map - 'column_labels' - 'detail_column_order';