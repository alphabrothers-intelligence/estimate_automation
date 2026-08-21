-- up
-- 후처리(quote_pricing.finalize)가 무엇을 움직였는지 화면에 그대로 보여주기 위한 칸
-- (2026-08-21 금액 로직 재설계). "왜 내가 안 건드린 항목이 바뀌었는지 알 수 없다"가
-- 실무자의 가장 큰 불만이었고, 이제 움직인 항목·잔액이 전부 여기에 문장으로 남는다.
-- quote_versions.edit_request_text에도 같은 내용이 쌓이지만, 미리보기 화면이 견적서
-- 한 건을 읽을 때마다 버전 테이블을 조인하지 않도록 최신 값만 여기에 둔다.
alter table entity_quotes add column if not exists adjustment_note text;

-- down
-- alter table entity_quotes drop column if exists adjustment_note;
