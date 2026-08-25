"""법인 선택 목록 순서 자체 점검 — `python backend/tests/test_entity_ordering.py`.

실무자가 지정한 순서다(2026-08-25): 본견적서로 자주 쓰는 4곳을 지정한 순서 그대로 맨 앞,
썬데이워커는 맨 뒤(직인이 없어 고를 때마다 날인 요청이 붙는다), 나머지는 그 사이.

정렬 규칙 자체보다 **화면까지 그 순서가 살아서 가는지**가 실제로 깨졌던 부분이다 —
프론트엔드가 응답을 받아 localeCompare로 다시 정렬해서 서버 순서를 덮어쓰고 있었다.
프론트는 여기서 검증할 수 없으니, 서버 규칙만이라도 못 박아 둔다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.catalog_service import (
    DEPRIORITIZED_ENTITIES,
    PRIMARY_ENTITY_ORDER,
    _entity_sort_key,
)

ALL = [
    "테스티파이", "알파브라더스", "블렌디드랩", "썬데이워커", "ABBG",
    "안르", "위드앤코", "테키", "다름과이음", "스프린트",
]


def _sorted() -> list:
    return sorted(ALL, key=_entity_sort_key)


def test_frequently_used_entities_come_first_in_the_given_order():
    assert _sorted()[: len(PRIMARY_ENTITY_ORDER)] == list(PRIMARY_ENTITY_ORDER)


def test_sundaywalker_is_last():
    assert _sorted()[-1] == "썬데이워커"


def test_the_middle_is_everything_else_and_nothing_is_dropped():
    ordered = _sorted()
    middle = ordered[len(PRIMARY_ENTITY_ORDER) : -len(DEPRIORITIZED_ENTITIES)]
    assert set(middle) == set(ALL) - set(PRIMARY_ENTITY_ORDER) - DEPRIORITIZED_ENTITIES
    assert middle == sorted(middle), "가운데는 가나다순"
    assert sorted(ordered) == sorted(ALL), "정렬이 항목을 잃거나 만들지 않는다"


def test_unknown_entity_lands_in_the_middle_not_the_ends():
    """법인이 새로 추가돼도 자주 쓰는 4곳을 밀어내거나 맨 뒤로 가지 않는다."""
    ordered = sorted(ALL + ["새로운법인"], key=_entity_sort_key)
    assert ordered[: len(PRIMARY_ENTITY_ORDER)] == list(PRIMARY_ENTITY_ORDER)
    assert ordered[-1] == "썬데이워커"
    assert "새로운법인" in ordered[len(PRIMARY_ENTITY_ORDER) : -1]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("모두 통과")
