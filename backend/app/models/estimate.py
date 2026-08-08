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
    recipient_name: str = Field(min_length=1)  # 견적서 수신자(고객사명) — 실제 발급 시 "OOO 귀하"에 들어감
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
    task_type: str
    total_amount: float = 0
    line_items: List[Dict[str, Any]] = Field(default_factory=list)
    is_catalog_borrowed: bool = False
    catalog_source_entity_name: Optional[str] = None
    service_name: Optional[str] = None
    # 법인마다 실제 원본 양식의 컬럼 명칭·순서가 다르다(예: 작업일/소요일, 수량/작업수량) —
    # 미리보기 UI가 이 값 그대로 표시한다(2026-07-10).
    column_labels: Dict[str, str] = Field(default_factory=dict)
    detail_column_order: List[str] = Field(default_factory=list)


class GenerateRequest(BaseModel):
    selections: Dict[str, List[str]] = Field(default_factory=dict)  # entity_quote_id -> 선택된 module_name 목록


class ServiceNameUpdate(BaseModel):
    service_name: str = Field(min_length=1)


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


class LineItemsUpdate(BaseModel):
    items: List[LineItemIn] = Field(min_length=1)


class EditResult(BaseModel):
    scope: str  # "quote_only" | "catalog_update" | "ambiguous"
    entity_quote: EntityQuoteOut
    changed_items: List[Dict[str, Any]] = Field(default_factory=list)
