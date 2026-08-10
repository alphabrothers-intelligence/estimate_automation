"""과업종류에 여러 대안 모듈 구성이 있을 때, 용역명·총액 등 맥락으로 어떤 구성을 쓸지 Claude가
정하게 한다 (PRD 7장 3~4단계 — PM이 매번 직접 고르는 대신 LLM이 자동 판단, MVP 방향).

예: 테스티파이·시장검증에서 용역명이 "정량, 정성 데이터 기반 시장 검증 용역"이면, 정량 분석
위주인 "시장성 테스트"와 정성(설문) 위주인 "설문형 시장검증"을 함께 고르는 것이 실제 과거
사례(미구 건, 19,800,000원)와 일치한다 — 이런 판단을 코드에 규칙으로 박아두는 대신 매번
Claude에게 맡긴다.
"""

import json
from typing import List, Optional

from pydantic import BaseModel, ValidationError

from app.config import CLAUDE_MODEL, get_anthropic
from app.models.catalog import ModuleGroup
from app.services.allocation_service import extract_json

SYSTEM_PROMPT = (
    "당신은 견적서에 어떤 항목 구성을 담을지 결정하는 담당자입니다. 카탈로그에는 두 종류의 "
    "그룹이 있습니다: '택1 그룹'은 서로 대체 관계라 그 그룹에서 반드시 정확히 하나의 옵션만 "
    "고르고, '추가 옵션 그룹'은 0개 이상 자유롭게 고를 수 있습니다. 용역명·총액·과업종류를 "
    "참고해 실제 상황에 가장 가까운 구성을 고르세요 — 예를 들어 용역명에 '정량'과 '정성'이 "
    "함께 언급되면, 정량 데이터 분석(시계열·클러스터 분석 등) 항목이 있는 옵션과 설문 조사 "
    "항목이 있는 옵션을 함께 고르는 식입니다. 단, 택1 그룹에서 이미 설문/인터뷰 성격의 옵션을 "
    "골랐다면(예: FGI, PMF Survey 등) 그 성격과 겹치는 추가 옵션(예: 설문형 시장검증)은 또 "
    "얹지 마세요 — 추가 옵션은 택1로 고른 구성이 다루지 못하는 성격을 보완할 때만 더하는 것"
    "입니다. 특별한 단서가 없으면 택1 그룹은 (기본값)이 표시된 옵션을 그대로 쓰세요. 반드시 "
    'JSON 객체 하나만 응답하세요(설명, 마크다운 코드블록 없이). 출력 형식: '
    '{"selected_option_keys": ["...", ...]}'
)


class ModuleSelectionResult(BaseModel):
    selected_option_keys: List[str]


def _build_prompt_block(groups: List[ModuleGroup]) -> str:
    lines = []
    for group in groups:
        header = "[택1 그룹 — 정확히 하나만 선택]" if group.kind == "variant" else "[추가 옵션 그룹 — 0개 이상 선택]"
        lines.append(header)
        for option in group.options:
            default_tag = " (기본값)" if option.is_default else ""
            items = ", ".join(name for group_item in option.item_groups for name in group_item.item_names)
            lines.append(f'- option_key="{option.option_key}"{default_tag}: {option.label} → {items}')
    return "\n".join(lines)


def _call_claude_for_selection(
    entity_name: str,
    task_type: str,
    total_amount: float,
    vat_included: bool,
    service_name: Optional[str],
    groups: List[ModuleGroup],
) -> List[str]:
    client = get_anthropic()
    service_line = f"[용역명] {service_name}\n" if service_name else ""
    user_content = (
        f"[법인] {entity_name}\n[과업종류] {task_type}\n{service_line}"
        f"[총액] {round(total_amount):,}원 ({'VAT 포함' if vat_included else 'VAT 별도'})\n\n"
        f"[선택 가능한 구성]\n{_build_prompt_block(groups)}"
    )

    last_error: Optional[Exception] = None
    for _ in range(2):
        message = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        text = next((b.text for b in message.content if b.type == "text"), "")
        try:
            data = extract_json(text)
            result = ModuleSelectionResult.model_validate(data)
            return result.selected_option_keys
        except (json.JSONDecodeError, ValidationError) as e:
            last_error = e
            user_content += "\n\n[재시도] 이전 응답이 올바른 JSON이 아니었습니다. JSON 객체 하나만 정확히 출력하세요."

    raise RuntimeError(f"Claude 응답을 JSON으로 파싱하지 못했습니다: {last_error}")


def choose_modules(
    entity_name: str,
    task_type: str,
    total_amount: float,
    vat_included: bool,
    service_name: Optional[str],
    groups: List[ModuleGroup],
) -> List[str]:
    """각 그룹에서 옵션을 골라, generate에 넘길 module_name 목록(평탄화)을 반환한다.

    Claude 응답이 그룹 제약(택1 그룹은 정확히 1개)을 어기면 그 그룹만 기본값으로 보정한다
    (예: 택1 그룹에서 0개 또는 2개 이상을 고른 경우).
    """
    selected_keys = set(
        _call_claude_for_selection(entity_name, task_type, total_amount, vat_included, service_name, groups)
    )

    module_names: List[str] = []
    for group in groups:
        picked = [o for o in group.options if o.option_key in selected_keys]
        if group.kind == "variant":
            if len(picked) != 1:
                picked = [o for o in group.options if o.is_default] or group.options[:1]
            module_names.extend(picked[0].module_names)
        else:
            for o in picked:
                module_names.extend(o.module_names)
    return module_names
