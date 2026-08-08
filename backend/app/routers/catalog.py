from typing import List

from fastapi import APIRouter, HTTPException

from app.config import get_supabase
from app.models.catalog import CatalogModuleOptions, EntityOption
from app.services import catalog_service

router = APIRouter(prefix="/api", tags=["catalog"])


@router.get("/task-types", response_model=List[str])
def get_task_types():
    return catalog_service.list_task_types()


@router.get("/entities", response_model=List[EntityOption])
def get_entities(task_type: str):
    return catalog_service.list_entities_for_task_type(task_type)


@router.get("/catalog/module-options", response_model=CatalogModuleOptions)
def get_catalog_module_options(entity_id: str, task_type: str):
    """견적서 생성 마법사가 entity_quote를 만들기 전에 기업×과업종류 체크박스를 보여줄 때 쓴다."""
    supabase = get_supabase()
    entity_res = supabase.table("entity_templates").select("name").eq("id", entity_id).execute()
    if not entity_res.data:
        raise HTTPException(status_code=404, detail="법인을 찾을 수 없습니다.")
    entity_name = entity_res.data[0]["name"]
    has_modules, groups = catalog_service.get_module_options(entity_id, entity_name, task_type)
    return CatalogModuleOptions(has_modules=has_modules, groups=groups)
