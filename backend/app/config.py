import os
from functools import lru_cache
from pathlib import Path

import anthropic
import httpx
from dotenv import load_dotenv
from supabase import Client, ClientOptions, create_client

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

CLAUDE_MODEL = "claude-sonnet-5"  # CLAUDE.md 2장 고정 — 임의 변경 금지 (2026-08-21 사용자 승인)

# Sonnet 5는 thinking이 기본으로 켜지고 max_tokens가 thinking+응답을 합쳐 제한한다.
# 4-6 시절의 1024·2048을 그대로 쓰면 추론에 예산을 다 쓰고 응답이 잘려 JSON 파싱이
# 실패한다. 모든 호출부가 이 값을 기준으로 잡는다(2026-08-21 모델 교체와 함께 상향).
CLAUDE_MAX_TOKENS = 16000


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
