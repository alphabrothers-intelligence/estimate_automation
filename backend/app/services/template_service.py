from pathlib import PurePosixPath
from typing import List

from fastapi import HTTPException, UploadFile

from app.config import get_supabase
from app.models.template import QuoteTemplateSummary
from app.services import template_storage

ALLOWED_SUFFIXES = {".xlsx", ".xls"}
TEMPLATES_PREFIX = "templates"


def list_templates() -> List[QuoteTemplateSummary]:
    supabase = get_supabase()
    entities = supabase.table("entity_templates").select("id, name").execute().data
    mappings = (
        supabase.table("quote_templates")
        .select("entity_id, task_type, storage_path, sheet_name")
        .execute()
        .data
    )
    rows_by_entity: dict[str, list[dict]] = {}
    for row in mappings:
        rows_by_entity.setdefault(row["entity_id"], []).append(row)

    storage_files = template_storage.list_files(TEMPLATES_PREFIX)

    result: list[QuoteTemplateSummary] = []
    for entity in sorted(entities, key=lambda item: item["name"]):
        rows = rows_by_entity.get(entity["id"], [])
        storage_path = rows[0]["storage_path"] if rows else None
        file_name = PurePosixPath(storage_path).name if storage_path else None
        meta = storage_files.get(file_name) if file_name else None
        result.append(
            QuoteTemplateSummary(
                entity_id=entity["id"],
                entity_name=entity["name"],
                storage_path=storage_path,
                file_name=file_name if meta else None,
                file_size=meta["metadata"]["size"] if meta else None,
                updated_at=meta["updated_at"] if meta else None,
                is_available=meta is not None,
                task_types=sorted({row["task_type"] for row in rows}),
                sheet_names=sorted({row["sheet_name"] for row in rows}),
            )
        )
    return result


async def replace_template(entity_id: str, upload: UploadFile) -> QuoteTemplateSummary:
    suffix = PurePosixPath(upload.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=400, detail="XLSX 또는 XLS 파일만 업로드할 수 있습니다.")

    supabase = get_supabase()
    rows = (
        supabase.table("quote_templates")
        .select("storage_path")
        .eq("entity_id", entity_id)
        .execute()
        .data
    )
    if not rows:
        raise HTTPException(status_code=404, detail="이 법인의 셀 매핑 정보를 찾을 수 없습니다.")

    current_path = rows[0]["storage_path"]
    target_path = str(PurePosixPath(current_path).with_suffix(suffix))

    data = await upload.read()
    if not data:
        raise HTTPException(status_code=400, detail="빈 파일은 업로드할 수 없습니다.")
    if len(data) > 30 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="양식 파일은 30MB 이하여야 합니다.")

    template_storage.upload(target_path, data)
    if target_path != current_path:
        template_storage.remove(current_path)
    supabase.table("quote_templates").update({"storage_path": target_path}).eq("entity_id", entity_id).execute()

    return next(item for item in list_templates() if item.entity_id == entity_id)


def delete_template(entity_id: str) -> None:
    supabase = get_supabase()
    rows = (
        supabase.table("quote_templates")
        .select("storage_path")
        .eq("entity_id", entity_id)
        .execute()
        .data
    )
    if not rows:
        raise HTTPException(status_code=404, detail="이 법인의 양식 정보를 찾을 수 없습니다.")
    template_storage.remove(rows[0]["storage_path"])
