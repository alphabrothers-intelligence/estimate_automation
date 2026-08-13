import os
from functools import lru_cache
from pathlib import Path

import anthropic
import httpx
from dotenv import load_dotenv
from supabase import Client, ClientOptions, create_client

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

CLAUDE_MODEL = "claude-sonnet-4-6"  # CLAUDE.md 2장 고정 — 임의 변경 금지


@lru_cache
def get_supabase() -> Client:
    # get_supabase()가 lru_cache로 앱 전체에 클라이언트 하나를 공유하는데, postgrest-py가
    # 기본으로 켜는 HTTP/2는 이 클라이언트 하나의 커넥션을 여러 요청이 멀티플렉싱으로 나눠
    # 쓴다. FastAPI의 동기 라우트는 스레드풀에서 병렬 실행되므로(위저드가 법인 여러 곳을
    # 고르면 모듈옵션 API를 동시에 여러 개 호출), 같은 HTTP/2 커넥션에 여러 스레드가 동시에
    # 접근하면서 간헐적으로 `httpx.ReadError: [Errno 35] Resource temporarily unavailable`가
    # 발생해 500 에러로 이어졌다(2026-08-12 확인). HTTP/1.1로 고정하면 동시 요청마다 커넥션
    # 풀에서 별도 연결을 쓰게 되어 이 경합이 사라진다.
    httpx_client = httpx.Client(http2=False, limits=httpx.Limits(max_connections=100, max_keepalive_connections=20))
    return create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SECRET_KEY"],
        options=ClientOptions(httpx_client=httpx_client),
    )


@lru_cache
def get_anthropic() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
