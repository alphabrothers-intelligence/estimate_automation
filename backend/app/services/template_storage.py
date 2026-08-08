"""quote-templates Storage 버킷 접근 헬퍼.

법인 마스터 원본 xlsx/xls의 단일 소스를 로컬 backend/templates/에서 Supabase Storage로
이관한다(PRD 4.2 "이후 Supabase Storage로 이관" 계획을 실행). template_service(양식
관리 CRUD)와 pdf_service(견적 발급 시 원본을 읽어 가변 셀만 채움) 양쪽에서 공용으로 쓴다.
"""

from typing import Any, Dict

from fastapi import HTTPException

from app.config import get_supabase

BUCKET = "quote-templates"


def download(storage_path: str) -> bytes:
    try:
        return get_supabase().storage.from_(BUCKET).download(storage_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"마스터 양식 파일을 찾을 수 없습니다: {storage_path}") from e


def upload(storage_path: str, data: bytes) -> None:
    get_supabase().storage.from_(BUCKET).upload(storage_path, data, file_options={"upsert": "true"})


def remove(storage_path: str) -> None:
    get_supabase().storage.from_(BUCKET).remove([storage_path])


def list_files(prefix: str) -> Dict[str, Dict[str, Any]]:
    files = get_supabase().storage.from_(BUCKET).list(prefix)
    return {f["name"]: f for f in files}
