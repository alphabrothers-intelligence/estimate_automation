from typing import List, Optional, Tuple

from app.config import get_supabase
from app.models.catalog import CatalogItem, CatalogResult, EntityOption, ModuleGroup, ModuleOption

# PRD 1.4/v0.4: 5개 법인 모두 3개 과업종류를 공통 취급하지만, 실제 카탈로그 데이터가 없는 조합은
# 아래 대표 법인의 카탈로그를 임시로 빌려쓴다 (부록 B).
FALLBACK_SOURCE_BY_TASK_TYPE = {
    "시장검증": "테스티파이",
    "마케팅": "테스티파이",
    "광고대행": "블렌디드랩",
}

# 썬데이워커/ABBG는 실제 시장검증 발행 이력이 없다(둘 다 테스티파이 카탈로그를 그대로 빌려쓰던
# 자리채움용 데이터였음) — 2026-07-10 사용자 결정으로 이 조합은 선택지에서 제외한다. 두 법인의
# 실제 발행 사례는 디자인/마케팅(ABBG), 컨설팅·AI·개발(ABBG/썬데이워커) 쪽이라, 새 task_type을
# 만들지 않는 한 이 부분은 계속 보류.
EXCLUDED_ENTITIES_BY_TASK_TYPE = {
    "시장검증": {"썬데이워커", "ABBG"},
}


def list_task_types() -> List[str]:
    """item_catalogs에 실제로 존재하는 과업종류만 후보로 노출 (PRD 3.2, 7.1-2)."""
    supabase = get_supabase()
    res = supabase.table("item_catalogs").select("task_type").eq("is_current", True).execute()
    return sorted({row["task_type"] for row in res.data})


def list_entities_for_task_type(task_type: str) -> List[EntityOption]:
    """5개 법인 모두 마케팅/광고대행/시장검증을 공통 취급하지만, 실제 발행 이력이 없는 조합은
    EXCLUDED_ENTITIES_BY_TASK_TYPE로 숨긴다 (2026-07-10 결정 — 썬데이워커/ABBG × 시장검증)."""
    supabase = get_supabase()
    res = supabase.table("entity_templates").select("id, name").execute()
    excluded_names = EXCLUDED_ENTITIES_BY_TASK_TYPE.get(task_type, set())
    entities = [
        EntityOption(id=row["id"], name=row["name"])
        for row in res.data
        if row["name"] not in excluded_names
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
    """법인×과업종류의 카탈로그 행을 가져온다. 실제 카탈로그가 없으면(예: ABBG+시장검증) 대표
    법인의 카탈로그를 임시로 빌려쓴다 (PRD 1.4/v0.4, 부록 B)."""
    rows = _fetch_catalog_rows(entity_id, task_type)
    is_borrowed = False
    source_name = entity_name

    if not rows:
        source_name = FALLBACK_SOURCE_BY_TASK_TYPE.get(task_type)
        if source_name and source_name != entity_name:
            supabase = get_supabase()
            source_res = (
                supabase.table("entity_templates").select("id").eq("name", source_name).execute()
            )
            if source_res.data:
                rows = _fetch_catalog_rows(source_res.data[0]["id"], task_type)
                is_borrowed = True

    return rows, is_borrowed, source_name


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
        item_names = [n for m in module_names for n in names[m]]
        return ModuleOption(
            option_key=option_key,
            label=" + ".join(module_names),
            module_names=module_names,
            item_count=len(item_names),
            is_default=is_default,
            item_names=item_names,
        )

    groups: List[ModuleGroup] = []

    if alt_group_modules:
        options = [
            _make_option(ag, mods, is_default=alt_group_is_default.get(ag, False))
            for ag, mods in alt_group_modules.items()
        ]
        if options and not any(o.is_default for o in options):
            options[0].is_default = True
        groups.append(ModuleGroup(kind="variant", options=options))

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

    return len(groups) > 0, groups


def get_catalog_for_generation(
    entity_id: str,
    entity_name: str,
    task_type: str,
    selected_modules: Optional[List[str]] = None,
) -> CatalogResult:
    """항목 자동생성(7.1-2)에 쓸 항목 카탈로그를 가져온다.

    이 법인×과업종류 조합에 실제 카탈로그가 없으면(예: ABBG+시장검증), 대표 법인의
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
    return CatalogResult(items=items, is_borrowed=is_borrowed, source_entity_name=source_name)
