"""quote-templates Storage 버킷 접근 헬퍼.

법인 마스터 원본 xlsx/xls의 단일 소스를 로컬 backend/templates/에서 Supabase Storage로
이관한다(PRD 4.2 "이후 Supabase Storage로 이관" 계획을 실행). pdf_service가 견적 발급
시점에 원본을 읽어 가변 셀만 채우는 데 쓴다.
"""

from functools import lru_cache
from typing import Any, Dict

from fastapi import HTTPException

from app.config import get_supabase

BUCKET = "quote-templates"


@lru_cache(maxsize=32)
def download(storage_path: str) -> bytes:
    """마스터 양식 원본을 받아온다. 파일이 1MB 안팎이라 매번 받으면 0.8초씩 든다.

    이게 견적서 미리보기·발급·금액 규칙 판정(pdf_service.resolve_form_spec)마다 불려서,
    비교견적 2건을 다시 만드는 데만 1.7초가 다운로드였다(2026-08-21 프로파일링). 마스터
    양식은 관리 화면이 없어져(커밋 34c0892) 런타임 중에 바뀌지 않으므로 프로세스 수명 동안
    캐시해도 안전하다 — 그래도 upload()가 캐시를 비우게 해서 나중에 갱신 경로가 생겨도
    낡은 바이트를 쓰지 않는다.

    ponytail: 프로세스 로컬 캐시라 워커가 여러 개면 각자 한 벌씩 받는다. 사용자 1인이라
    그걸로 충분하고, 다중 워커에서 메모리가 문제되면 그때 공유 캐시로 바꾼다.
    """
    try:
        return get_supabase().storage.from_(BUCKET).download(storage_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"마스터 양식 파일을 찾을 수 없습니다: {storage_path}") from e


def upload(storage_path: str, data: bytes) -> None:
    get_supabase().storage.from_(BUCKET).upload(storage_path, data, file_options={"upsert": "true"})
    download.cache_clear()


def remove(storage_path: str) -> None:
    get_supabase().storage.from_(BUCKET).remove([storage_path])


def list_files(prefix: str) -> Dict[str, Dict[str, Any]]:
    files = get_supabase().storage.from_(BUCKET).list(prefix)
    return {f["name"]: f for f in files}
