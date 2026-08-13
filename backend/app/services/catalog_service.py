from functools import lru_cache
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
    return sorted(entities, key=lambda e: e.name)


def _fetch_catalog_rows(entity_id: str, task_type: str) -> List[dict]:
    supabase = get_supabase()
    res = (
        supabase.table("item_catalogs")
        .select(
            "module_name, item_name, historical_ratio, is_required, standard_description, "
            "sort_order, alt_group"
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
            item_name=r["item_name"],
            historical_ratio=float(r["historical_ratio"]) if r["historical_ratio"] is not None else None,
            is_required=r["is_required"],
            standard_description=r["standard_description"],
        )
        for r in filtered_rows
    ]
    return CatalogResult(items=items, is_borrowed=is_borrowed, source_entity_name=source_name, has_catalog=bool(rows))
