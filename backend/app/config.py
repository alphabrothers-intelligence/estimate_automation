import os
from functools import lru_cache
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

CLAUDE_MODEL = "claude-sonnet-4-6"  # CLAUDE.md 2장 고정 — 임의 변경 금지


@lru_cache
def get_supabase() -> Client:
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SECRET_KEY"])


@lru_cache
def get_anthropic() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
