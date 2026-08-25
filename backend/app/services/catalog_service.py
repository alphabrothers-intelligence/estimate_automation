from functools import lru_cache
import re
from typing import List, Optional, Tuple

from app.config import get_supabase
from app.models.catalog import CatalogItem, CatalogResult, EntityOption, ModuleGroup, ModuleItemGroup, ModuleOption

# PRD 1.4/v0.6: 5개 법인 모두 3개 과업종류(마케팅/고객검증/시장검증)를 공통 취급하지만, 실제
# 카탈로그 데이터가 없는 조합은 아래 대표 법인의 카탈로그를 임시로 빌려쓴다 (부록 B).
# ("광고대행"은 별도 과업종류가 아니라 마케팅 안의 대안 상품이다 — v0.6 정정, 028 마이그레이션)
# [v0.7] 시장검증은 030 마이그레이션으로 5개 법인 공통 표준 카탈로그(알파브라더스 4개 모듈)로
# 통일되어 모든 법인이 자체 행을 가지므로 사실상 이 fallback을 탈 일이 없다 — 그래도 기준
# 법인을 테스티파이 대신 알파브라더스로 맞춰 둔다(새 법인이 추가되는 등 예외 상황 대비).
FALLBACK_SOURCE_BY_TASK_TYPE = {
    "시장검증": "알파브라더스",
    "마케팅": "테스티파이",
}

# [v0.7] 시장검증이 030 마이그레이션으로 전체 법인 공통 표준 카탈로그가 되면서 썬데이워커/ABBG도
# 다른 법인과 동일하게 실제 카탈로그 행을 갖게 되어 더 이상 숨길 이유가 없다 (이전에는 두 법인이
# 테스티파이 카탈로그를 자리채움으로 빌려쓰던 게 오해를 낳아 제외했었음 — 2026-07-10 결정, 이제 해제).
EXCLUDED_ENTITIES_BY_TASK_TYPE: dict = {}

# 법인 선택 목록의 순서 (2026-08-25 사용자 지정).
#
# 앞: 본견적서로 자주 쓰는 순서 그대로 고정한다. 가나다순으로 두면 자주 쓰는 법인이 흩어져
#     매번 눈으로 찾아야 한다.
# 뒤: 썬데이워커. 마스터 양식에 직인이 찍혀 있지 않아 고를 때마다 날인을 따로 요청해야 한다 —
#     그 번거로움을 없애려고 직인이 박힌 타사 양식들을 새로 받아 등록했다(마이그레이션 052).
#     숨기지는 않는다. 필요하면 여전히 쓸 수 있어야 한다.
# 가운데: 나머지(비교견적 전용 타사 양식들). 순서는 상관없어서 가나다순으로 둔다.
PRIMARY_ENTITY_ORDER = ("알파브라더스", "테스티파이", "블렌디드랩", "ABBG")
DEPRIORITIZED_ENTITIES = frozenset({"썬데이워커"})


def _entity_sort_key(name: str) -> tuple:
    if name in PRIMARY_ENTITY_ORDER:
        return (0, PRIMARY_ENTITY_ORDER.index(name), "")
    if name in DEPRIORITIZED_ENTITIES:
        return (2, 0, name)
    return (1, 0, name)


def list_task_types() -> List[str]:
    """item_catalogs에 실제로 존재하는 과업종류만 후보로 노출 (PRD 3.2, 7.1-2)."""
    supabase = get_supabase()
    res = supabase.table("item_catalogs").select("task_type").eq("is_current", True).execute()
    return sorted({row["task_type"] for row in res.data})


@lru_cache
def _fetch_all_entity_rows() -> tuple:
    # entity_templates는 5개 법인 고정 데이터라 배포 중에는 사실상 바뀌지 않는다. 위저드가
    # 과업종류마다(2번) 이 테이블 전체를 매번 새로 조회해 화면에서 "불러오는 중"이 눈에 띄게
    # 느렸다(2026-08-09 사용자 지적) — 서버 프로세스 생애주기 동안 한 번만 조회해 재사용한다.
    supabase = get_supabase()
    res = supabase.table("entity_templates").select("id, name").execute()
    return tuple((row["id"], row["name"]) for row in res.data)


def list_entities_for_task_type(task_type: str) -> List[EntityOption]:
    """5개 법인 모두 마케팅/광고대행/시장검증을 공통 취급하며, 실제 발행 이력이 없는 조합이
    생기면 EXCLUDED_ENTITIES_BY_TASK_TYPE로 숨긴다 (v0.7 기준 비어 있음 — 030 마이그레이션으로
    시장검증이 전체 법인 공통 표준 카탈로그가 되어 더 이상 숨길 조합이 없음)."""
    excluded_names = EXCLUDED_ENTITIES_BY_TASK_TYPE.get(task_type, set())
    entities = [
        EntityOption(id=entity_id, name=name)
        for entity_id, name in _fetch_all_entity_rows()
        if name not in excluded_names
    ]
    return sorted(entities, key=lambda e: _entity_sort_key(e.name))


def _fetch_catalog_rows(entity_id: str, task_type: str) -> List[dict]:
    supabase = get_supabase()
    res = (
        supabase.table("item_catalogs")
        .select(
            "module_name, mid_category, item_name, historical_ratio, is_required, "
            "standard_description, sort_order, alt_group, module_weight, "
            "work_days, quantity, unit_price"
        )
        .eq("entity_id", entity_id)
        .eq("task_type", task_type)
        .eq("is_current", True)
        .order("module_name")
        .order("sort_order")
        .execute()
    )
    return res.data


def _resolve_catalog_rows(entity_id: str, entity_name: str, task_type: str) -> Tuple[List[dict], bool, str]:
    """법인×과업종류의 카탈로그 행을 가져온다. 실제 카탈로그가 없으면(예: ABBG+고객검증) 대표
    법인의 카탈로그를 임시로 빌려쓴다 (PRD 1.4/v0.4, 부록 B)."""
    rows = _fetch_catalog_rows(entity_id, task_type)
    is_borrowed = False
    source_name = entity_name

    if not rows:
        # FALLBACK_SOURCE_BY_TASK_TYPE에 없는 과업종류(예: 고객검증)는 차용 대상이 아예 없다 —
        # 이 경우도 source_name이 entity_name으로 남아 있어야 CatalogResult(source_entity_name:
        # str, not-null) 생성이 깨지지 않는다(전엔 None이 되어 카탈로그 없음 422 대신 500이 났음).
        fallback_source = FALLBACK_SOURCE_BY_TASK_TYPE.get(task_type)
        if fallback_source:
            source_name = fallback_source
        if source_name and source_name != entity_name:
            supabase = get_supabase()
            source_res = (
                supabase.table("entity_templates").select("id").eq("name", source_name).execute()
            )
            if source_res.data:
                rows = _fetch_catalog_rows(source_res.data[0]["id"], task_type)
                is_borrowed = True

    return rows, is_borrowed, source_name


# item_catalogs 조회가 module_name 알파벳순으로 정렬돼 있어(_fetch_catalog_rows), alt_group이
# 여러 module_name을 묶는 경우(현재는 테스티파이/썬데이워커 마케팅의 "그로스해킹형" 번들 하나뿐)
# 라벨의 "+"-조인 순서가 실제 발급 샘플(우유곳간 등, 008 마이그레이션 삽입 순서)과 달라지는
# 문제가 있었다(2026-08-09 사용자 지적). module_name 구성이 아래와 정확히 일치하면 이 순서로
# 강제 정렬한다 — 그 외 alt_group은 전부 module_name 1개짜리라 순서 문제가 없다.
_KNOWN_MODULE_ORDER = [
    ["온라인 광고", "SEO 마케팅", "자사몰 데이터 세팅", "그로스해킹"],
]

# 광고 대행 상품 3종의 alt_group 값 (027/028 마이그레이션) — variant 그룹에 전용 제목을 붙일지
# 판별하는 데 쓴다.
_AD_AGENCY_ALT_GROUPS = {"광고형", "네이버쇼핑형", "카카오톡스토어형"}


def _ordered_module_names(module_names: List[str]) -> List[str]:
    for known_order in _KNOWN_MODULE_ORDER:
        if set(module_names) == set(known_order):
            return known_order
    return module_names


def get_module_options(entity_id: str, entity_name: str, task_type: str) -> Tuple[bool, List[ModuleGroup]]:
    """카탈로그가 여러 모듈로 구성된 경우 PM에게 보여줄 선택지를 만든다 (PRD 7장 3~4단계).

    alt_group 컬럼으로 명시적으로 판별한다 (015 마이그레이션):
    - alt_group이 있는 행들은 서로 배타적인 "대안 구성"이다. 같은 alt_group 값을 공유하는
      module_name들은 하나의 선택지로 합쳐진다 — 예: 테스티파이의 "PMF Survey"와
      "FGI (심층그룹인터뷰)"는 alt_group='서베이인터뷰형'을 공유해 "PMF Survey + FGI" 하나의
      라디오 옵션이 되고, 이 옵션을 고르면 "시장성 테스트"(alt_group='표준형')는 빠진다.
    - alt_group이 없고 is_required=false인 모듈(예: "설문형 시장검증")만 필수 구성에 얹는
      체크박스(추가 옵션)로 노출한다.
    - alt_group이 없고 is_required=true인 모듈은 항상 포함되며 선택 UI에 노출하지 않는다.
    반환하는 bool은 "PM이 실제로 고를 것이 있는지" 여부다.
    """
    rows, _, _ = _resolve_catalog_rows(entity_id, entity_name, task_type)

    counts: dict[str, int] = {}
    names: dict[str, List[str]] = {}
    for r in rows:
        if r["module_name"]:
            counts[r["module_name"]] = counts.get(r["module_name"], 0) + 1
            names.setdefault(r["module_name"], []).append(r["item_name"])

    # alt_group -> 그 그룹에 속한 module_name들 (등장 순서 유지), 그리고 그 그룹의 기본값 여부
    alt_group_modules: dict[str, List[str]] = {}
    alt_group_is_default: dict[str, bool] = {}
    for r in rows:
        if r["module_name"] and r["alt_group"]:
            mods = alt_group_modules.setdefault(r["alt_group"], [])
            if r["module_name"] not in mods:
                mods.append(r["module_name"])
            if r["is_required"]:
                alt_group_is_default[r["alt_group"]] = True

    def _make_option(option_key: str, module_names: List[str], is_default: bool) -> ModuleOption:
        module_names = _ordered_module_names(module_names)
        item_groups = [ModuleItemGroup(module_name=m, item_names=names[m]) for m in module_names]
        return ModuleOption(
            option_key=option_key,
            label=" / ".join(module_names),
            module_names=module_names,
            item_count=sum(len(g.item_names) for g in item_groups),
            is_default=is_default,
            item_groups=item_groups,
        )

    groups: List[ModuleGroup] = []

    # 사용자 요청(2026-08-10): "추가 옵션"(체크박스, 필수 구성에 얹는 항목)을 화면 맨 위로 —
    # 예전엔 variant(택1 라디오)가 먼저 나와 추가 옵션이 아래로 밀려 있었다.
    additive_modules = sorted(
        {r["module_name"] for r in rows if r["module_name"] and not r["alt_group"] and not r["is_required"]}
    )
    if additive_modules:
        groups.append(
            ModuleGroup(
                kind="additive",
                options=[_make_option(m, [m], is_default=False) for m in additive_modules],
            )
        )

    if alt_group_modules:
        options = [
            _make_option(ag, mods, is_default=alt_group_is_default.get(ag, False))
            for ag, mods in alt_group_modules.items()
        ]
        if task_type == "시장검증":
            # 사용자 결정(2026-08-11): 시장검증 세부 항목(통합 패키지/FGI/사용성/기술성/시장성
            # 테스트)은 서로 배타적인 대안이 아니라 다수 선택 가능해야 한다 — alt_group으로
            # 나뉜 그룹이라도 variant(택1 라디오) 대신 additive(체크박스)로 노출한다.
            for o in options:
                o.is_default = False
            groups.append(ModuleGroup(kind="additive", options=options))
        else:
            if options and not any(o.is_default for o in options):
                options[0].is_default = True
            # "광고형"/"네이버쇼핑형"/"카카오톡스토어형"(광고 대행 상품 3종, 027/028 마이그레이션)이
            # 서로 배타적인 대안이라 variant 그룹이 되는데, 화면에는 아무 제목도 안 붙어 있었다.
            # 이 3개짜리 조합일 때만 전용 제목을 붙인다 — 다른 법인·과업의 variant 그룹(예: 시장검증
            # 서베이형/표준형)까지 이 제목으로 덮어쓰면 안 되므로 alt_group 이름 자체로 판별한다.
            label = "광고·마케팅 대행" if set(alt_group_modules) == _AD_AGENCY_ALT_GROUPS else None
            groups.append(ModuleGroup(kind="variant", options=options, label=label))

    return len(groups) > 0, groups


def get_catalog_for_generation(
    entity_id: str,
    entity_name: str,
    task_type: str,
    selected_modules: Optional[List[str]] = None,
) -> CatalogResult:
    """항목 자동생성(7.1-2)에 쓸 항목 카탈로그를 가져온다.

    이 법인×과업종류 조합에 실제 카탈로그가 없으면(예: ABBG+고객검증), 대표 법인의
    카탈로그를 임시로 빌려쓴다 (PRD 1.4/v0.4, 부록 B).

    selected_modules가 None이면(옵션 모듈이 없는 조합) 필수(is_required=true) 항목만 사용한다.
    selected_modules가 주어지면(PM이 모듈 선택을 마친 경우) 그 module_name 목록에 해당하는
    행만 사용한다 — 모듈 구분이 없는 카탈로그(module_name이 전부 null)는 선택과 무관하게
    항상 포함된다.
    """
    rows, is_borrowed, source_name = _resolve_catalog_rows(entity_id, entity_name, task_type)

    if selected_modules:
        # alt_group이 없는 필수 모듈(대안 구성 자체가 없는 항상-포함 모듈)은 PM이 선택지에서
        # 볼 일이 없으므로, 프론트엔드가 보낸 목록에 없더라도 안전하게 항상 포함시킨다.
        always_on = {
            r["module_name"] for r in rows if r["module_name"] and r["is_required"] and not r["alt_group"]
        }
        selected_set = set(selected_modules) | always_on
        filtered_rows = [r for r in rows if r["module_name"] is None or r["module_name"] in selected_set]
    else:
        filtered_rows = [r for r in rows if r["is_required"]]

    items = [
        CatalogItem(
            module_name=r["module_name"],
            mid_category=r.get("mid_category"),
            item_name=r["item_name"],
            historical_ratio=float(r["historical_ratio"]) if r["historical_ratio"] is not None else None,
            is_required=r["is_required"],
            standard_description=normalize_description(r["standard_description"]),
            work_days=float(r.get("work_days") or 1),
            quantity=float(r.get("quantity") or 1),
            unit_price=float(r["unit_price"]) if r.get("unit_price") is not None else None,
            module_weight=float(r["module_weight"]) if r.get("module_weight") is not None else None,
        )
        for r in filtered_rows
    ]
    return CatalogResult(items=items, is_borrowed=is_borrowed, source_entity_name=source_name, has_catalog=bool(rows))


# 상품구성은 "1. A / 2. B / 3. C"처럼 슬래시로 이어 붙은 카탈로그가 있고(알파브라더스),
# 줄바꿈으로 저장된 카탈로그가 있다(테스티파이). 발급 양식의 "상품구성" 칸은 PRD 6.2가
# 명시한 대로 세로형 개조식이어야 하는데, 슬래시 버전은 한 줄로 죽 이어져 읽기 어려웠다
# (2026-08-21 사용자 지적). 번호 앞에서만 줄을 나눠 두 형식을 하나로 맞춘다.
# 번호 표기가 카탈로그마다 다르고(1. / 1)) 구분자도 다르다(슬래시 / 공백만). 뒤에 "숫자." 또는
# "숫자)"가 오는 자리에서만 자른다 — 내용에 들어있는 슬래시("Macro/Micro")나 숫자("카페24
# 기반", "20~40만원")는 마커가 아니라서 그대로 남는다.
_NUMBERED_SPLIT = re.compile(r"\s*/?\s+(?=\d{1,2}[.)]\s)")


def normalize_description(text: Optional[str]) -> Optional[str]:
    """상품구성을 세로형 개조식(줄바꿈 구분)으로 통일한다.

    "1. A / 2. B" -> "1. A\n2. B". 번호가 없는 설명("- 대행사 결제수단을 통해 …")이나 이미
    줄바꿈으로 나뉜 설명은 건드리지 않는다 — 슬래시가 내용의 일부인 경우(예: "Macro/Micro
    기반의 스크립트 작성")를 자르면 안 되므로, 뒤에 "숫자."가 오는 슬래시만 자른다.
    """
    if not text:
        return text
    return _NUMBERED_SPLIT.sub("\n", text)
