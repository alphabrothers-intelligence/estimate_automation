-- up
-- 채팅 수정의 대화 이력 (2026-08-21 채팅 리뉴얼).
-- 예전 채팅은 매 요청이 단발 호출이라 "아까 그거 다시" 같은 말이 통하지 않았고, 사용자가
-- 실제로 쓰던 Claude 채팅창과 가장 크게 달랐던 지점이다. Anthropic messages 배열을 그대로
-- 담는다(assistant의 tool_use 블록 포함) — 다음 턴에 그대로 되돌려 보내야 맥락이 이어진다.
alter table entity_quotes add column if not exists chat_history jsonb not null default '[]'::jsonb;

-- down
-- alter table entity_quotes drop column if exists chat_history;
