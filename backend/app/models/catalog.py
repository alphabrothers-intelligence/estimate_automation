from typing import Optional

from pydantic import BaseModel, Field


class EntityOption(BaseModel):
    id: str
    name: str


class CatalogItem(BaseModel):
    module_name: Optional[str] = None
    item_name: str
    historical_ratio: Optional[float] = None
    is_required: bool
    standard_description: Optional[str] = None


class CatalogResult(BaseModel):
    items: list[CatalogItem]
    is_borrowed: bool
    source_entity_name: str
    has_catalog: bool = True  # False면 이 법인×과업종류 자체에 카탈로그 행이 없다(차용 대상도 없음) —
    # items가 비어 있어도 has_catalog=True면 단지 이번에 선택된 모듈이 없을 뿐, 데이터 자체는 존재한다.


class ModuleItemGroup(BaseModel):
    module_name: str
    item_names: list[str]


class ModuleOption(BaseModel):
    option_key: str  # alt_group 값(또는 alt_group이 없으면 module_name) — 선택 시 고유 식별자
    label: str  # 화면 표시용 라벨. module_names가 여럿이면 "A + B" 형태
    module_names: list[str]  # 이 옵션을 선택하면 generate 시 함께 포함되는 실제 module_name들
    item_count: int
    is_default: bool
    item_groups: list[ModuleItemGroup] = Field(default_factory=list)  # module_name별로 묶은 항목명(펼쳐보기 UI, 개조식 표시용)


class ModuleGroup(BaseModel):
    kind: str  # "variant"(표준형/대안형 중 택1) | "additive"(필수 모듈에 추가로 얹는 옵션)
    options: list[ModuleOption]
    label: Optional[str] = None  # 화면에 보여줄 그룹 제목. 없으면 프론트가 kind별 기본 제목을 쓴다.


class EntityModuleOptions(BaseModel):
    entity_quote_id: str
    entity_name: str
    has_modules: bool  # PM이 실제로 고를 것이 있는지 (False면 모듈 선택 UI를 건너뛴다)
    groups: list[ModuleGroup] = Field(default_factory=list)


class CatalogModuleOptions(BaseModel):
    """entity_quote 생성 전, 기업×과업종류만으로 모듈 선택지를 미리 보여줄 때 쓴다
    (견적서 생성 마법사 — 기업/과업 선택 단계)."""

    has_modules: bool
    groups: list[ModuleGroup] = Field(default_factory=list)
