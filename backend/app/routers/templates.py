from typing import List

from fastapi import APIRouter, File, Response, UploadFile

from app.models.template import QuoteTemplateSummary
from app.services import template_service

router = APIRouter(prefix="/api/templates", tags=["templates"])


@router.get("", response_model=List[QuoteTemplateSummary])
def list_templates():
    return template_service.list_templates()


@router.put("/{entity_id}", response_model=QuoteTemplateSummary)
async def replace_template(entity_id: str, file: UploadFile = File(...)):
    return await template_service.replace_template(entity_id, file)


@router.delete("/{entity_id}", status_code=204)
def delete_template(entity_id: str):
    template_service.delete_template(entity_id)
    return Response(status_code=204)
