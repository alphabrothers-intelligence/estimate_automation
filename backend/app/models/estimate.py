from datetime import date
from typing import Literal, Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class EntitySelectionIn(BaseModel):
    entity_id: str
    is_primary: bool = False
    # 이 기업 몫으로 만들 과업종류들 — 과업종류 개수만큼 entity_quote row가 각각 생긴다
    # (2026-08 마법사 개편: 기업 하나가 마케팅+시장검증을 교차 선택하면 그 기업 명의
    # 견적서가 2건 나옴 — 법인마다 원본 양식이 과업종류별로 통째로 다르기 때문).
    task_types: List[str] = Field(min_length=1)
    # 비교견적 마크업 배율(예: 0.10 = 본견적 총액의 +10%) — is_primary=True면 무시된다.
    # None이면 generation_service의 기본값(+10%)을 쓴다(2026-08-14 사용자 요청 — 고정 +10%
    # 대신 기업마다 다르게 조절 가능해야 함).
    markup_ratio: Optional[float] = Field(default=None, ge=0)


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
    def primary_limit(self) -> "EstimateSetCreate":
        # 비교견적서는 개수 제한 없음(2026-08-12 사용자 결정 — PRD 3.2/4.3의 1~3개 상한 폐기).
        primaries = [e for e in self.entities if e.is_primary]
        if len(primaries) > 1:
            raise ValueError("본견적서 법인은 최대 1곳만 선택할 수 있습니다.")
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
    # 이 양식의 공급가액 수식이 작업일/수량을 곱하는가 — 화면 편집이 발급본과 같은 식으로
    # 금액을 계산하기 위해 내려준다(2026-08-21).
    amount_uses_work_days: bool = False
    amount_uses_quantity: bool = True
    # 후처리가 무엇을 움직였는지 한 문장(quote_pricing.finalize 로그). 화면에 그대로 띄운다 —
    # "안 건드린 항목이 왜 바뀌었나"를 사용자가 추적할 수 있어야 한다(2026-08-21).
    adjustment_note: Optional[str] = None
    # 비교견적의 인상률(1.10 = +10%). 화면에서 %를 고쳐 다시 생성할 때 현재 값이 필요하다.
    markup_ratio: Optional[float] = None
    # 비교견적서 품명을 AI가 다시 쓸지(마이그레이션 051). 본견적서에서는 의미 없다.
    rename_items: bool = True
    # 머리글의 업무/제작 기간 표기. 그 칸이 있는 양식에서만 쓰인다(마이그레이션 053).
    duration_text: Optional[str] = None


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
    # 업무/제작 기간 표기(마이그레이션 053). 생성 시 초안이 들어가고 여기서 고친다.
    duration_text: Optional[str] = None


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


class ChatAttachment(BaseModel):
    filename: str
    data: str  # base64. PDF는 API가 직접 읽고, xlsx는 서버가 표 텍스트로 펴서 넣는다.


class EditRequest(BaseModel):
    edit_request_text: str = Field(min_length=1)
    attachment: Optional[ChatAttachment] = None
    # 화면이 지금 보여주고 있는 항목들. "수정 반영하기"를 아직 안 눌렀으면 DB와 다르다.
    # 이걸 안 받으면 채팅이 매번 DB 상태를 기준으로 고쳐서, 반영 전에 두 번 연달아 요청하면
    # 첫 번째 수정이 통째로 사라진다 — 실무자 신고 "채팅으로 추가는 되지만 때때로 롤백됨"
    # (2026-08-24). 안 보내면(구버전 프론트) 예전처럼 DB 항목을 쓴다.
    current_items: Optional[List["LineItemIn"]] = None



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
    # 구분(중) — description과 같은 이유로 여기 없으면 저장할 때마다 지워진다(2026-08-19).
    mid_category: Optional[str] = None
    # 기술수준(특급/고급/중급/초급). 그 칸이 있는 양식에서만 쓰인다 — line_items가 jsonb라
    # 마이그레이션 없이 붙는다.
    grade: Optional[str] = None


class LineItemsUpdate(BaseModel):
    # 본견적을 고쳤을 때 비교견적을 어떻게 할지 사용자가 고른다(2026-08-21 요청).
    #   keep       — 본견적만 저장. 비교견적은 손대지 않는다(인상률이 어긋날 수 있고,
    #                그 상태로는 발급이 막힌다 — estimate_service.assert_issuable)
    #   sync       — 금액만 비교견적에 즉시 반영(AI 호출 없음, 0원·즉시). 기본값
    #   regenerate — 비교견적 항목 문장까지 새 본견적 기준으로 다시 쓴다(AI, 10~20초)
    comparison_mode: Literal["keep", "sync", "regenerate"] = "sync"
    items: List[LineItemIn] = Field(min_length=1)
    # 채팅 수정 미리보기를 "수정 반영하기"로 커밋할 때 채팅 원문을 넘겨 버전 이력에 남긴다
    # (2026-08-14). 없으면 직접편집으로 간주.
    edit_request_text: Optional[str] = None


class EditResult(BaseModel):
    scope: str  # "quote_only" | "catalog_update" | "ambiguous"
    # 모델이 사람에게 하는 답 — 채팅창에 그대로 표시한다. 예전엔 프론트엔드가
    # "요청하신 내용을 반영했습니다." 고정 문구를 띄워 대화가 아니라 폼 제출 같았다(2026-08-21).
    reply: str = ""
    entity_quote: EntityQuoteOut
    changed_items: List[Dict[str, Any]] = Field(default_factory=list)


class RenameItemsUpdate(BaseModel):
    rename_items: bool


class MarkupRatioUpdate(BaseModel):
    # 1.10 = +10%. 사용자가 화면에서 %만 고치는 입력 — 저장 후 비교견적 재생성을 부르면
    # 이 비율로 다시 쓴다(2026-08-21). 본견적보다 싼 비교견적은 존재 이유가 없으므로 1 초과.
    markup_ratio: float = Field(gt=1.0, le=3.0)


class LineItemsUpdateResult(BaseModel):
    entity_quote: EntityQuoteOut
    # 본견적 금액이 바뀌어 금액만 자동 반영된 비교견적들. 프론트엔드가 세트 전체를 다시
    # 조회하지 않고 이 값으로 화면을 갱신한다(2026-08-17).
    synced_comparison_quotes: List[EntityQuoteOut] = Field(default_factory=list)
    # 본견적 항목이 추가·삭제되어 1:1 대응이 깨진 비교견적들 — 금액만으로는 못 맞추므로
    # 화면이 "비교견적 다시 생성"을 안내한다(2026-08-21).
    comparisons_need_regeneration: List[str] = Field(default_factory=list)


class QuoteVersionOut(BaseModel):
    version_no: int
    edit_request_text: Optional[str] = None
    edited_at: str
    line_items: List[Dict[str, Any]] = Field(default_factory=list)
