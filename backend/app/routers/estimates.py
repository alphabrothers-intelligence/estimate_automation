from typing import List, Optional

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
    MarkupRatioUpdate,
    RenameItemsUpdate,
    LineItemsUpdateResult,
    QuoteDateUpdate,
    QuoteVersionOut,
    RecipientInfoUpdate,
    ServiceNameUpdate,
)
from app.services import chat_service, estimate_service, generation_service, pdf_service

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
    return chat_service.edit_entity_quote(
        entity_quote_id,
        payload.edit_request_text,
        payload.attachment.model_dump() if payload.attachment else None,
        [item.model_dump() for item in payload.current_items] if payload.current_items else None,
    )


@entity_quotes_router.patch("/{entity_quote_id}/service-name", response_model=EntityQuoteOut)
def update_service_name(entity_quote_id: str, payload: ServiceNameUpdate):
    return estimate_service.update_service_name(entity_quote_id, payload.service_name)


@entity_quotes_router.patch("/{entity_quote_id}/quote-date", response_model=EntityQuoteOut)
def update_quote_date(entity_quote_id: str, payload: QuoteDateUpdate):
    return estimate_service.update_quote_date(entity_quote_id, payload.quote_date)


@entity_quotes_router.patch("/{entity_quote_id}/recipient-info", response_model=EntityQuoteOut)
def update_recipient_info(entity_quote_id: str, payload: RecipientInfoUpdate):
    return estimate_service.update_recipient_info(entity_quote_id, payload)


@router.post("/{estimate_set_id}/regenerate-comparisons", response_model=EstimateSetOut)
def regenerate_comparisons(estimate_set_id: str):
    """확정된 본견적을 기준으로 비교견적만 다시 만든다. 본견적 저장이 비교견적을 자동으로
    건드리지 않게 되면서(sync_service 폐기, 2026-08-21) 이 버튼이 그 유일한 경로가 됐다."""
    return generation_service.regenerate_comparisons(estimate_set_id)


@entity_quotes_router.put("/{entity_quote_id}/line-items", response_model=LineItemsUpdateResult)
def update_line_items(entity_quote_id: str, payload: LineItemsUpdate):
    return estimate_service.update_line_items(
        entity_quote_id, payload.items, payload.edit_request_text or "직접편집", payload.comparison_mode
    )


@entity_quotes_router.put("/{entity_quote_id}/rename-items", response_model=EntityQuoteOut)
def update_rename_items(entity_quote_id: str, payload: RenameItemsUpdate):
    return estimate_service.update_rename_items(entity_quote_id, payload.rename_items)


@entity_quotes_router.put("/{entity_quote_id}/markup-ratio", response_model=EntityQuoteOut)
def update_markup_ratio(entity_quote_id: str, payload: MarkupRatioUpdate):
    return estimate_service.update_markup_ratio(entity_quote_id, payload.markup_ratio)


@entity_quotes_router.get("/{entity_quote_id}/versions", response_model=List[QuoteVersionOut])
def list_quote_versions(entity_quote_id: str):
    return estimate_service.list_quote_versions(entity_quote_id)


@entity_quotes_router.get("/{entity_quote_id}/pdf")
def download_entity_quote_pdf(entity_quote_id: str, inline: bool = False, v: Optional[str] = None):
    # inline=True는 프론트엔드 미리보기 iframe 전용(Content-Disposition: attachment면
    # 브라우저가 iframe 안에서 PDF를 렌더링하지 않고 무시한다). 다운로드 버튼은 기본값(attachment) 그대로 쓴다.
    estimate_service.assert_issuable(entity_quote_id)
    pdf_bytes = pdf_service.render_entity_quote_pdf(entity_quote_id)
    disposition = "inline" if inline else "attachment"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'{disposition}; filename="quote-{entity_quote_id[:8]}.pdf"',
            # v(견적 내용 해시)가 붙은 미리보기 요청만 캐시한다 — 내용이 바뀌면 URL이 바뀌므로
            # 낡은 PDF가 보일 일이 없다. 다운로드 버튼(v 없음)은 항상 새로 만든다.
            **({"Cache-Control": "private, max-age=3600"} if v else {"Cache-Control": "no-store"}),
        },
    )


@entity_quotes_router.get("/{entity_quote_id}/xlsx")
def download_entity_quote_xlsx(entity_quote_id: str):
    estimate_service.assert_issuable(entity_quote_id)
    xlsx_bytes = pdf_service.render_entity_quote_xlsx(entity_quote_id)
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="quote-{entity_quote_id[:8]}.xlsx"'},
    )
