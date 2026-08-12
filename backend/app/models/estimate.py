from datetime import date
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class EntitySelectionIn(BaseModel):
    entity_id: str
    is_primary: bool = False
    # 이 기업 몫으로 만들 과업종류들 — 과업종류 개수만큼 entity_quote row가 각각 생긴다
    # (2026-08 마법사 개편: 기업 하나가 마케팅+시장검증을 교차 선택하면 그 기업 명의
    # 견적서가 2건 나옴 — 법인마다 원본 양식이 과업종류별로 통째로 다르기 때문).
    task_types: List[str] = Field(min_length=1)


class EstimateSetCreate(BaseModel):
    project_name: str = Field(min_length=1)
    # 견적서 수신자(고객사명) — 실제 발급 시 "OOO 귀하"에 들어감. 생성 시점엔 선택값이고
    # 발급 전에만 채우면 된다(발급 시 pdf_service._build_filled_xlsx_from_quote가 검증함,
    # 2026-08-12 사용자 요청 — 화면에서 나중에 수정 가능).
    recipient_name: Optional[str] = None
    # ABBG·알파브라더스 양식 전용 칸(cell_map.header_fields의 client_contact/client_phone/client_email) —
    # 다른 법인 양식엔 대응 칸이 없어 그냥 무시된다(pdf_service._collect_header_updates).
    recipient_contact: Optional[str] = None
    recipient_phone: Optional[str] = None
    recipient_email: Optional[str] = None
    total_amount: float = Field(gt=0)
    vat_included: bool
    entities: List[EntitySelectionIn] = Field(min_length=1)
    service_name: Optional[str] = None  # 본견적이 테스티파이면 필수 (4.2 — 테스티파이 템플릿 전용 필드)

    @field_validator("entities")
    @classmethod
    def no_duplicate_entities(cls, v: List[EntitySelectionIn]) -> List[EntitySelectionIn]:
        ids = [e.entity_id for e in v]
        if len(set(ids)) != len(ids):
            raise ValueError("같은 법인을 두 번 선택할 수 없습니다.")
        return v

    @model_validator(mode="after")
    def primary_and_comparison_limits(self) -> "EstimateSetCreate":
        primaries = [e for e in self.entities if e.is_primary]
        comparisons = [e for e in self.entities if not e.is_primary]
        if len(primaries) > 1:
            raise ValueError("본견적서 법인은 최대 1곳만 선택할 수 있습니다.")
        if len(comparisons) > 3:
            raise ValueError("비교견적서 법인은 최대 3곳까지 선택할 수 있습니다.")
        return self


class EntityQuoteOut(BaseModel):
    id: str
    entity_id: str
    entity_name: str
    is_primary: bool
    task_type: str  # 표시용 라벨 ("+"로 합쳐진 과업종류들, 예: "마케팅+시장검증")
    task_types: List[str] = Field(default_factory=list)
    total_amount: float = 0
    line_items: List[Dict[str, Any]] = Field(default_factory=list)
    is_catalog_borrowed: bool = False
    catalog_source_entity_name: Optional[str] = None
    service_name: Optional[str] = None
    quote_date: Optional[str] = None  # ISO date(YYYY-MM-DD) — 견적서 상단 "년/월/일"에 채워지는 값
    recipient_name: Optional[str] = None
    recipient_contact: Optional[str] = None
    recipient_phone: Optional[str] = None
    recipient_email: Optional[str] = None
    # 법인마다 실제 원본 양식의 컬럼 명칭·순서가 다르다(예: 작업일/소요일, 수량/작업수량) —
    # 미리보기 UI가 이 값 그대로 표시한다(2026-07-10).
    column_labels: Dict[str, str] = Field(default_factory=dict)
    detail_column_order: List[str] = Field(default_factory=list)
    # 알파브라더스처럼 항목 블록마다 구분(대)/구분(중)이 있는 양식인지 (item.task_type로 채움)
    show_category_split: bool = False


class GenerateRequest(BaseModel):
    selections: Dict[str, List[str]] = Field(default_factory=dict)  # entity_quote_id -> 선택된 module_name 목록


class ServiceNameUpdate(BaseModel):
    service_name: str = Field(min_length=1)


class QuoteDateUpdate(BaseModel):
    quote_date: date


class RecipientInfoUpdate(BaseModel):
    recipient_name: Optional[str] = None
    recipient_contact: Optional[str] = None
    recipient_phone: Optional[str] = None
    recipient_email: Optional[str] = None


class EstimateSetOut(BaseModel):
    id: str
    project_name: str
    total_amount: float
    vat_included: bool
    task_type: str
    primary_entity_id: Optional[str] = None
    entity_quotes: List[EntityQuoteOut]


class EstimateSetSummary(BaseModel):
    id: str
    project_name: str
    total_amount: float
    vat_included: bool
    task_type: str
    created_at: str
    quote_count: int = 0
    entity_names: List[str] = Field(default_factory=list)


class EditRequest(BaseModel):
    edit_request_text: str = Field(min_length=1)


class LineItemIn(BaseModel):
    category: str = Field(min_length=1)
    name: str = Field(min_length=1)
    amount: int = Field(ge=0)
    # 2026-08-09 직접편집 범위 확장 — 단가/작업일/투입인력/비고도 화면에서 직접 고칠 수 있다.
    # 프론트엔드가 셋 중 하나를 고치면 나머지로 amount를 다시 계산해서 보내므로(또는 반대로
    # amount를 고치면 단가를 역산), 여기서 받은 값을 그대로 저장하고 PDF 발급 시에도 카탈로그
    # 재계산 없이 그대로 쓴다(pdf_service._compute_item_pricing 참고).
    unit_price: Optional[float] = None
    work_days: Optional[float] = None
    quantity: Optional[float] = None
    note: Optional[str] = None
    # 과업종류를 교차 선택한 견적서(마케팅+시장검증)에서 이 항목이 어느 과업종류 카탈로그
    # 소속인지 — PDF 발급 시 work_days/quantity를 어느 법인 카탈로그에서 찾을지 결정한다
    # (pdf_service._compute_item_pricing). 프론트엔드가 기존 값을 그대로 되돌려 보낸다.
    task_type: Optional[str] = None
    # 알파브라더스·ABBG처럼 "상품구성" 컬럼에 세부 항목을 세로형 개조식으로 나열하는 양식용 —
    # 이 필드가 없으면 직접편집 저장 시 model_dump()가 통째로 지워버린다(2026-08-11 발견).
    description: Optional[str] = None


class LineItemsUpdate(BaseModel):
    items: List[LineItemIn] = Field(min_length=1)


class EditResult(BaseModel):
    scope: str  # "quote_only" | "catalog_update" | "ambiguous"
    entity_quote: EntityQuoteOut
    changed_items: List[Dict[str, Any]] = Field(default_factory=list)
