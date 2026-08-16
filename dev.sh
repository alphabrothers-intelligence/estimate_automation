#!/usr/bin/env bash
# 프론트(Next.js)와 백엔드(FastAPI)를 함께 기동한다.
# 이 스크립트가 없으면 둘 중 하나만 켠 채로 작업하기 쉽고, 그 경우 백엔드 API 호출이
# 전부 실패한다(2026-08-11 "법인 목록을 불러오지 못했습니다" 장애 원인).
set -euo pipefail
cd "$(dirname "$0")"

pids=()
cleanup() { kill "${pids[@]}" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

(cd backend && python3 -m uvicorn app.main:app --reload --port 8001) &
pids+=($!)

(cd frontend && npm run dev -- -p 3001) &
pids+=($!)

# macOS 기본 bash(3.2)엔 `wait -n`(bash 4.3+)이 없어 스크립트가 죽고 trap이 두 서버를
# 바로 종료시켰다(2026-08-16 발견) — 그냥 둘 다 끝날 때까지 기다리는 것으로 대체.
wait
