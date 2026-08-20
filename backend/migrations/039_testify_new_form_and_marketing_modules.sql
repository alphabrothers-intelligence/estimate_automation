-- up
-- 사용자 결정(2026-08-19):
--  1. 테스티파이 견적서 양식을 "우유곳간 자사몰 마케팅 견적서(260811)" 양식으로 전면 교체한다.
--     이 양식은 알파브라더스 양식과 같은 구조(구분(대)/구분(중)/상품명/상품구성/작업일/수량/
--     단가/공급가액)라, 테스티파이도 이제 그 컬럼들을 전부 채운다.
--     - 원본 파일 안에서 실제 이 양식이 들어있는 시트 이름은 "시장성테스트"다(알파브라더스
--       워크북을 복제해 만든 흔적으로 시트명과 내용이 어긋나 있다 — 내용은 마케팅 견적서).
--       시트를 옮기면 병합·인쇄영역·이미지 앵커를 전부 다시 잡아야 해서 이름은 그대로 둔다.
--     - 알파브라더스 워터마크(머리글/바닥글 VML)는 backend/templates/testify.xlsx를 만들면서
--       제거했다(사용자 요청 7번).
--  2. 마케팅 과업에 "런칭 마케팅 / 그로스해킹 / 퍼포먼스" 모듈을 추가한다. 이 3개는 구분(대)에
--     모듈명이 그대로 들어가고, 그 아래 구분(중) → 상품명 → 상품구성으로 3단 구성이 된다.
--     구분(중)을 담을 자리가 없어 item_catalogs에 mid_category 컬럼을 새로 만든다.

alter table item_catalogs add column mid_category text;
comment on column item_catalogs.mid_category is
    '구분(중) — 구분(대)(module_name)와 상품명(item_name) 사이의 중간 분류. 이 칸이 있는 양식
     (테스티파이 신양식·알파브라더스)에서만 쓰이고, 없는 양식에서는 무시된다 (2026-08-19)';

-- ============================================================
-- 1. 테스티파이 양식 교체 — 마케팅·시장검증 모두 새 양식 하나를 쓴다
-- ============================================================
update quote_templates
set storage_path = 'templates/testify.xlsx',
    sheet_name = '시장성테스트',
    cell_map = '{
        "header_fields": {
            "quote_code": "AB3",
            "quote_date_serial": "D4",
            "client_name": "D5",
            "client_contact": "D6",
            "client_phone": "D7",
            "client_email": "D8"
        },
        "item_blocks": [
            {"category_large_cell": "A13", "rows": [13, 14, 15, 16, 17]},
            {"category_large_cell": "A18", "rows": [18, 19]},
            {"category_large_cell": "A20", "rows": [20, 21]}
        ],
        "columns": {
            "category_mid": "C",
            "item_name": "E",
            "description": "I",
            "work_days": "T",
            "quantity": "V",
            "unit_price": "X",
            "supply_amount": "AA"
        },
        "column_labels": {
            "category_mid": "구분(중)",
            "item_name": "상품명",
            "description": "상품구성",
            "work_days": "작업일",
            "quantity": "수량",
            "unit_price": "단가",
            "supply_amount": "공급가액"
        },
        "detail_column_order": ["work_days", "quantity", "unit_price"],
        "totals": {"vat_cell": "E22", "supply_total_cell": "T22", "top_display_cell": "G10"},
        "notes": "우유곳간 260811 실제 발급본 그대로. 공급가액(AA열)은 =단가*수량 수식(작업일 미반영). 항목 행이 모자라면 pdf_service._grow_template이 실제로 행을 끼워 넣는다."
    }'::jsonb
where entity_id = (select id from entity_templates where name = '테스티파이');

-- ============================================================
-- 2. 마케팅 신규 모듈 — 런칭 마케팅 / 그로스해킹 / 퍼포먼스
--    (우유곳간 260811 실제 발급본의 상품명·상품구성·작업일·수량 그대로)
-- ============================================================
-- 기존 "그로스해킹" 모듈(033에서 분리한 주간단위 2항목)과 이름이 겹치므로 먼저 내린다 —
-- 새 "그로스해킹"이 상품구성까지 갖춘 상위 호환이다.
update item_catalogs set is_current = false
where task_type = '마케팅'
  and module_name = '그로스해킹'
  and entity_id = (select id from entity_templates where name = '테스티파이');

insert into item_catalogs
    (entity_id, task_type, module_name, mid_category, item_name, standard_description,
     historical_ratio, is_required, work_days, quantity, sort_order)
select (select id from entity_templates where name = '테스티파이'), '마케팅', m, mid, item, descr, ratio, false, wd, qty, ord
from (values
    ('런칭 마케팅', '자사몰 구축', '자사몰 구축',
     '1. 레퍼런스 리서치 및 정리

2. 홈페이지 주요 기능 정의

3. 스킨 list up 및 선택

4.스킨 구매 및 세부 퍼블리싱 진행

※ 카페24 기준으로 구축되며, 스킨 구매 및 PG 연결 비용 별도(20~40만원)
※ 이외 운영을 위해 필요한 월구독 플러그인 비용 별도(월 5~10만원)',
     55.0, 1.0, 1.0, 10),
    ('런칭 마케팅', '전략수립', '마케팅 전략안',
     '1. 전반적인 마케팅 수행 내용 요약 정리

2. USP, Persona 1page 기획안 작성 ',
     2.0, 3.0, 1.0, 20),
    ('런칭 마케팅', '기본 세팅', 'SEO 키워드 세팅',
     '1. SEO 키워드 분석 및 제안

2. 자사몰 SEO 키워드 세팅
(meta tag, opengraph 등)',
     11.0, 1.0, 1.0, 30),
    ('런칭 마케팅', '기본 세팅', 'Meta 계정 및 Pixel 세팅',
     '1. Meta 광고 계정 세팅

2. Meta Pixel 카페 24 설치 및 연동

3. Meta Pixel 결제 이벤트 설정 및 연동',
     14.0, 3.0, 1.0, 40),
    ('런칭 마케팅', '기본 세팅', '데이터 연동',
     '1. GA4 계정 생성 및 카페24 연동

2. 카페24 및 Meta 데이터 연동 스프레드시트 구축

3. UTM 작명 규칙 및 빌더 시트 구축',
     18.0, 1.0, 1.0, 50),
    ('그로스해킹', '주간단위 그로스해킹', '주간 Wrap-Up',
     '1. 주간 목표 설정 및 주간 데이터 측정

2. 목표 달성 여부 점검 및 개선 필요 사항 분석

3. 주요 지표별 분석 인사이트 도출

4. 액션플랜 설정

※ 매주 1회를 기점으로 지난 7일간의 데이터를 분석
※ 월 4회를 기준으로 견적 산출 (3개월 운영시 12회)',
     62.5, 1.0, 16.0, 10),
    ('그로스해킹', '주간단위 그로스해킹', '주간 액션플랜 수행',
     '1. 주간 Wrap-Up을 통해 설정한 주간 액션플랜 수행

[주간 액션플랜 포함 항목]
 - 신규 광고안 제작을 통한 Meta 성과 고도화 (디자인 포함)
 - 상세페이지 및 전환율 개선을 위한 배너 제작 (디자인 포함)
 - 퍼널 개선을 위한 카페24 구조 고도화 퍼블리싱 (개발 포함)
 - 재구매 고객 획득을 위한 CRM 캠페인 기획 및 실행 (결과 측정 포함)
 - 신규 프로모션, 광고안 제작을 위한 리서치 포함 (서면화 포함)
 - 협의를 통해 성과 개선을 위해 필요한 추가 업무 산정 가능',
     37.5, 1.0, 16.0, 20),
    ('퍼포먼스', 'Meta 광고', 'Meta 광고 실비',
     '- 대행사 결제수단을 통해 Meta 광고 집행(실비)',
     90.9, 1.0, 1.0, 10),
    ('퍼포먼스', 'Meta 광고', 'Meta 광고 운영',
     '1. Meta 광고 캠페인 세팅

2. Meta 광고 성과 측정 및 운영

※ 광고 실비의 10% 책정',
     9.1, 1.0, 1.0, 20)
) as t(m, mid, item, descr, ratio, wd, qty, ord);

-- down
delete from item_catalogs
where task_type = '마케팅'
  and module_name in ('런칭 마케팅', '퍼포먼스')
  and entity_id = (select id from entity_templates where name = '테스티파이');
delete from item_catalogs
where task_type = '마케팅' and module_name = '그로스해킹' and mid_category = '주간단위 그로스해킹'
  and entity_id = (select id from entity_templates where name = '테스티파이');
update item_catalogs set is_current = true
where task_type = '마케팅' and module_name = '그로스해킹' and mid_category is null
  and entity_id = (select id from entity_templates where name = '테스티파이');
alter table item_catalogs drop column if exists mid_category;
-- quote_templates는 010/038이 만든 예전 좌표로 되돌려야 하므로 down에서는 다루지 않는다
-- (되돌릴 일이 생기면 010_seed_quote_templates.sql의 테스티파이 블록을 다시 실행할 것).