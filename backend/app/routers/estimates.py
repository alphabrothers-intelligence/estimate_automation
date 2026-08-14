from typing import List

from fastapi import APIRouter, Response

from app.models.catalog import EntityModuleOptions
from app.models.estimate import (
    EditRequest,
    EditResult,
    EstimateSetCreate,
    EstimateSetOut,
    EstimateSetSummary,
    GenerateRequest,
    EntityQuoteOut,
    LineItemsUpdate,
    QuoteDateUpdate,
    QuoteVersionOut,
    RecipientInfoUpdate,
    ServiceNameUpdate,
)
from app.services import estimate_service, generation_service, pdf_service
from app.services import edit_service

router = APIRouter(prefix="/api/estimate-sets", tags=["estimates"])
entity_quotes_router = APIRouter(prefix="/api/entity-quotes", tags=["entity-quotes"])


@router.get("", response_model=List[EstimateSetSummary])
def list_estimate_sets():
    return estimate_service.list_estimate_sets()


@router.post("", response_model=EstimateSetOut)
def create_estimate_set(payload: EstimateSetCreate):
    return estimate_service.create_estimate_set(payload)


@router.get("/{estimate_set_id}", response_model=EstimateSetOut)
def get_estimate_set(estimate_set_id: str):
    return estimate_service.get_estimate_set(estimate_set_id)


@router.delete("/{estimate_set_id}", status_code=204)
def delete_estimate_set(estimate_set_id: str):
    estimate_service.delete_estimate_set(estimate_set_id)


@router.get("/{estimate_set_id}/module-options", response_model=List[EntityModuleOptions])
def get_module_options(estimate_set_id: str):
    return estimate_service.get_module_options_for_set(estimate_set_id)


@router.post("/{estimate_set_id}/generate", response_model=EstimateSetOut)
def generate_estimate_set(estimate_set_id: str, payload: GenerateRequest = GenerateRequest()):
    return generation_service.generate_estimate_set(estimate_set_id, payload.selections)


@entity_quotes_router.post("/{entity_quote_id}/edit", response_model=EditResult)
def edit_entity_quote(entity_quote_id: str, payload: EditRequest):
    return edit_service.edit_entity_quote(entity_quote_id, payload.edit_request_text)


@entity_quotes_router.patch("/{entity_quote_id}/service-name", response_model=EntityQuoteOut)
def update_service_name(entity_quote_id: str, payload: ServiceNameUpdate):
    return estimate_service.update_service_name(entity_quote_id, payload.service_name)


@entity_quotes_router.patch("/{entity_quote_id}/quote-date", response_model=EntityQuoteOut)
def update_quote_date(entity_quote_id: str, payload: QuoteDateUpdate):
    return estimate_service.update_quote_date(entity_quote_id, payload.quote_date)


@entity_quotes_router.patch("/{entity_quote_id}/recipient-info", response_model=EntityQuoteOut)
def update_recipient_info(entity_quote_id: str, payload: RecipientInfoUpdate):
    return estimate_service.update_recipient_info(entity_quote_id, payload)


@entity_quotes_router.put("/{entity_quote_id}/line-items", response_model=EntityQuoteOut)
def update_line_items(entity_quote_id: str, payload: LineItemsUpdate):
    return estimate_service.update_line_items(
        entity_quote_id, payload.items, payload.edit_request_text or "직접편집"
    )


@entity_quotes_router.get("/{entity_quote_id}/versions", response_model=List[QuoteVersionOut])
def list_quote_versions(entity_quote_id: str):
    return estimate_service.list_quote_versions(entity_quote_id)


@entity_quotes_router.get("/{entity_quote_id}/pdf")
def download_entity_quote_pdf(entity_quote_id: str, inline: bool = False):
    # inline=True는 프론트엔드 미리보기 iframe 전용(Content-Disposition: attachment면
    # 브라우저가 iframe 안에서 PDF를 렌더링하지 않고 무시한다). 다운로드 버튼은 기본값(attachment) 그대로 쓴다.
    pdf_bytes = pdf_service.render_entity_quote_pdf(entity_quote_id)
    disposition = "inline" if inline else "attachment"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="quote-{entity_quote_id[:8]}.pdf"'},
    )


@entity_quotes_router.get("/{entity_quote_id}/xlsx")
def download_entity_quote_xlsx(entity_quote_id: str):
    xlsx_bytes = pdf_service.render_entity_quote_xlsx(entity_quote_id)
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="quote-{entity_quote_id[:8]}.xlsx"'},
    )
