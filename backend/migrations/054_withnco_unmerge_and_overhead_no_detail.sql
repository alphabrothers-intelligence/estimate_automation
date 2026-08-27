-- up
-- 2026-08-25 실무자 지적 3건을 데이터로 고친다.
--
-- (1) 위드앤코 양식의 빈 행·먹힌 금액
--     원본은 항목 하나가 여러 행에 걸친 세로 병합(C14:D17, F14:F17 …)이라 앵커 5행만 썼다.
--     항목이 9개면 _grow_template이 22행을 복제하는데, 세로 병합은 삽입 지점을 걸치면 Excel처럼
--     같이 늘어난다 — F22:F23 → F22:F27이 되어 이윤 아래 네 항목의 단가·수량·금액이 병합에
--     먹혀 사라졌다(로컬 렌더링으로 재현). 앵커가 아닌 행(15~17 등)도 값이 없는 빈 칸으로
--     그대로 찍혔다.
--     FLES에서 쓰던 방법(unmerge_cells + column_merge_end_cols)을 그대로 적용한다 — 발급
--     시점에 세로 병합을 걷어내고 항목 행마다 C:D만 가로로 다시 묶으면 14행이 전부 독립
--     항목 행이 된다. 안 쓰는 행은 pdf_service가 숨기므로 빈 행도 사라진다.
--     always_clear_cells는 필요 없어진다(그 행들이 이제 항목 행이라 매번 비워지고 숨겨진다).
--
-- (2) 간접비 항목의 상품구성 삭제
--     "경비 및 간접비"(교통비·회의 및 기타경비·일반관리비·이윤)는 원가계산 표준 항목이라
--     세부 설명이 3~4줄일 이유가 없다. 그렇다고 비우면 허전해서 **한 줄로 고정한다**
--     (2026-08-25 실무자 결정). 비교견적에서 품명을 다시 쓰든 안 쓰든 한 줄이다 —
--     리라이팅 결과도 generation_service._one_line이 첫 줄만 남긴다.
--
-- (3) 050에서 들어간 리터럴 "\n"
--     050은 standard_conforming_strings 환경에서 '...\n...'을 그대로 넣어 상품구성에 역슬래시
--     n이 문자 그대로 저장됐고, 발급 PDF에 "…교통비\n2. 방문 인원…"으로 찍혔다. (2)에서
--     그 행들의 상품구성을 한 줄짜리로 덮어쓰므로 같이 사라진다.

update quote_templates
set cell_map = cell_map
    - 'always_clear_cells'
    || jsonb_build_object(
        'item_blocks', '[{"rows": [14,15,16,17,18,19,20,21,22,23,24,25,26,27]}]'::jsonb,
        'column_merge_end_cols', '{"item_name": "D"}'::jsonb,
        'unmerge_cells', '["C14:D17","F14:F17","G14:G17","H14:H17","I14:I17","J14:J17",
                           "C18:D19","F18:F19","G18:G19","H18:H19","I18:I19","J18:J19",
                           "C20:D21","F20:F21","G20:G21","H20:H21","I20:I21","J20:J21",
                           "C22:D23","F22:F23","G22:G23","H22:H23","I22:I23","J22:J23",
                           "C24:D27","F24:F27","G24:G27","H24:H27","I24:I27","J24:J27"]'::jsonb,
        'notes', '타사(위드앤코) 양식. 항목 칸이 세로 병합 5덩어리라 발급 시점에 걷어내고(unmerge_cells) 행마다 C:D로 다시 묶는다 — 그래야 14~27행이 전부 독립 항목 행이 된다. 안 쓰는 행은 숨겨진다.'
    )
where storage_path = 'templates/comparison_forms.xlsx'
  and sheet_name = '위드앤코 (마케팅, 디자인)';

update item_catalogs c
set standard_description = d.one_line
from (values
    ('교통비 (수요처별 방문 기준)', '수요처 방문 왕복 교통비 실비'),
    ('회의 및 기타경비',           '회의 진행 실비 및 인쇄·소모품비'),
    ('일반관리비',                 '직접비 합계의 3~5% 요율 적용'),
    ('이윤',                       '직접비·일반관리비 합계의 10% 이내')
) as d(item_name, one_line)
where c.module_name = '경비 및 간접비' and c.item_name = d.item_name;

-- down
-- 지운 상품구성 문구는 되돌리지 않는다 — 050의 리터럴 "\n"이 그대로 돌아오는 값이라 복구할
-- 가치가 없다. 필요하면 050을 다시 실행할 것.
update quote_templates
set cell_map = cell_map
    - 'unmerge_cells'
    - 'column_merge_end_cols'
    || jsonb_build_object(
        'item_blocks', '[{"rows": [14,18,20,22,24]}]'::jsonb,
        'always_clear_cells', '["E15","E16","E17","E19","E21","E23","E25","E26","E27"]'::jsonb
    )
where storage_path = 'templates/comparison_forms.xlsx'
  and sheet_name = '위드앤코 (마케팅, 디자인)';
