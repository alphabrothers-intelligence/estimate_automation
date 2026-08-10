-- up
-- 사용자 결정(2026-08-10): 한 기업이 마케팅+시장검증을 교차 선택하면 지금까지는 entity_quote가
-- 과업종류 개수만큼(2건) 따로 생성돼 견적서도 2개로 나뉘어 나왔다 — 이를 "하나의 견적서"로
-- 합쳐 달라는 요청. entity_quotes.task_type(단일 문자열, "마케팅+시장검증"처럼 표시용 라벨로
-- 유지)과 별도로, 실제로 이 견적서가 포함하는 과업종류 목록을 배열 컬럼으로 추가한다.
alter table entity_quotes add column task_types text[];
update entity_quotes set task_types = array[task_type] where task_types is null;
alter table entity_quotes alter column task_types set not null;

-- down
alter table entity_quotes drop column task_types;
