"""견적 금액 후처리 — AI가 산정한 항목을 발급 가능한 값으로 확정하는 유일한 지점.

2026-08-21 금액 로직 재설계. 이전에는 금액을 건드리는 곳이 6군데(_scale_standard_unit_prices의
이분탐색 환산 / reconcile_snapped_items의 최대항목 잔액흡수 / snap_unit_price의 무조건 10만원
스냅 / sync_service의 비례 스케일링 / 프론트 reconcileAmounts / 총합계 유지 재배분)였고, 서로를
순서대로 덮어써서 실무자가 고친 값이 계속 되돌아왔다. 이제 금액을 정하는 곳은 AI 1곳과 여기
1곳뿐이고, 여기서 움직인 항목은 전부 로그로 남아 화면에 표시된다.

핵심 전제는 **공급가액은 그 법인 양식의 수식이 정한다**는 것이다. 법인마다 마스터 xlsx의
수식이 다르다(2026-08-20 실측):
    - 알파브라더스 모듈 시트(FGI/사용성/기술성/시장성) 및 마케팅 = 단가 × 작업일 × 수량
    - 알파브라더스 통합 패키지 / 테스티파이 / ABBG / 썬데이워커      = 단가 × 수량
    - 블렌디드랩                                                    = 단가 (수량은 표기 전용)
그래서 코드는 AI가 준 amount를 절대 믿지 않고 항상 수식으로 다시 계산한다. 예전에 프론트엔드·
edit_service·pdf_service가 서로 다른 수식을 가정해 화면 총액과 발급본 총액이 어긋난 원인이 이거다.

이 모듈은 leaf다 — app.services 안의 다른 모듈을 import하지 않는다(pdf_service가 이쪽을
가져다 쓰는 방향).
"""

from dataclasses import dataclass, field
from itertools import combinations, product
from typing import Dict, List, Optional, Tuple

# 실무자가 못 견디는 건 "266,250원", "6,222,727원" 같은 잔돈이다. 단가·금액이 만원 단위로만
# 떨어지면 그 목적은 달성된다. 10만원 배수는 프롬프트로 유도하되 코드가 강제하지는 않는다 —
# 350,000원처럼 멀쩡한 단가를 400,000원으로 밀어 총액을 깨뜨리는 부작용이 규칙을 지켜서 얻는
# 것보다 크다(2026-08-20 검증에서 실제로 재현).
CLEAN_UNIT = 10_000

# 잔액을 흡수할 때 한 항목의 단가가 이 비율 넘게 움직이지 않는다. 100,000원짜리 항목이
# 300,000원이 되면 항목 간 상대 중요도가 깨진다(2026-08-20 사용자 지적).
MAX_MOVE_RATIO = 0.35

# 잔액 흡수에 동원할 수 있는 항목 수 상한. 1개로는 격자상 도달 못 하는 조합이 있고
# (수량 5/2/2/2/3짜리 구성에서 +10만원은 300,000 올리고 200,000 내려야 닿는다),
# 3개 이상 움직이면 "왜 바뀌었는지" 화면에서 따라가기 어렵다.
MAX_MOVED_ITEMS = 2

# AI 합계가 목표에서 이 비율 넘게 벗어나면 미세 조정 대신 전체 배율로 먼저 맞춘다.
_RESCALE_THRESHOLD = 0.02


@dataclass(frozen=True)
class FormSpec:
    """한 법인 양식(정확히는 한 시트)의 금액 계산 규칙."""

    # 공급가액 = 단가 × 수량. 작업일은 금액과 무관한 정보성 값이다(2026-08-21 사용자 확정).
    #
    # 마스터 xlsx 두 곳은 원본 수식이 이 규칙과 다르다 — 알파브라더스 모듈 시트는
    # SUM(작업일×수량×단가), 블렌디드랩은 =단가(수량 없음). 원본을 고치는 대신 발급 시점에
    # 그 셀의 수식을 지우고 우리가 계산한 값을 쓴다(pdf_service._collect_item_block_updates).
    # 그래야 화면에서 본 금액과 발급본이 절대 갈리지 않는다.
    uses_work_days: bool = False
    uses_quantity: bool = True
    # 프롬프트에서 AI에게 요구할 단가 단위. 코드가 강제하는 하한은 CLEAN_UNIT이고
    # 이 값은 "그 양식의 실제 발급본이 쓰는 단위"다(알파브라더스만 만원, 나머지는 10만원).
    unit_price_unit: int = 100_000
    # 양식의 컬럼 라벨(작업일/소요일, 수량/작업수량 …). 프롬프트에 그대로 넣는다.
    labels: Dict[str, str] = field(default_factory=dict)

    @property
    def formula_text(self) -> str:
        """프롬프트와 화면에 그대로 보여줄 수식 설명."""
        parts = ["단가"]
        if self.uses_work_days:
            parts.append(self.labels.get("work_days", "작업일"))
        if self.uses_quantity:
            parts.append(self.labels.get("quantity", "수량"))
        if len(parts) == 1:
            return "공급가액 = 단가 (다른 칸은 표기 전용, 금액에 영향 없음)"
        return "공급가액 = " + " × ".join(parts)

    def divisor(self, item: dict) -> float:
        """단가에 곱해지는 값. 단가를 1원 올리면 공급가액이 이만큼 오른다."""
        d = 1.0
        if self.uses_work_days:
            d *= item.get("work_days") or 1
        if self.uses_quantity:
            d *= item.get("quantity") or 1
        return d

    def amount_of(self, item: dict) -> int:
        return round((item.get("unit_price") or 0) * self.divisor(item))

    def derived(self, item: dict) -> Dict[str, float]:
        """카탈로그에 없어 파생식으로 채우는 칸(썬데이워커의 투입 MM·세액).

        발급 시점에는 pdf_service._collect_item_block_updates가 다시 계산하지만, 미리보기
        화면은 저장된 line_items를 그대로 읽으므로 여기서도 채워둬야 "—"로 비지 않는다.
        """
        out: Dict[str, float] = {}
        if "tax_amount" in self.labels:
            out["tax_amount"] = round(item["amount"] * 0.1)
        if "input_mm" in self.labels:
            # ponytail: 실제 "역할별 투입 MM" 데이터가 카탈로그에 없어서 작업일×수량을 20영업일로
            # 나눈 근사치(PRD 7.4) — 사용자가 이후 직접 고치는 걸 전제로 한 임시값.
            out["input_mm"] = round((item.get("work_days") or 0) * (item.get("quantity") or 0) / 20, 2)
        return out


def detect_form(
    sheet_xml: str, columns: Dict[str, str], row: int, labels: Optional[Dict[str, str]] = None
) -> FormSpec:
    """양식의 표시 정보(컬럼 라벨·단가 단위)를 만든다.

    금액 규칙은 더 이상 시트마다 읽지 않는다 — 다섯 법인 전부 "단가 × 수량"으로 통일했고
    (2026-08-21 사용자 확정), 원본 수식이 다른 양식은 발급 시 그 수식을 지우고 값을 쓴다.
    예전엔 시트 수식을 읽어 법인마다 다르게 계산했는데, 화면·채팅·발급이 서로 다른 규칙을
    가정하면서 금액이 갈리는 사고가 반복됐다.
    """
    return FormSpec(labels=labels or {})


def _is_ugly(item: dict) -> bool:
    return (item.get("unit_price") or 0) % CLEAN_UNIT != 0 or item["amount"] % CLEAN_UNIT != 0


def _absorb(items: List[dict], diff: int, form: FormSpec, log: List[str]) -> List[str]:
    """잔액을 최대 MAX_MOVED_ITEMS개 항목의 단가로 흡수한다.

    한 걸음은 단가 1단위(=금액 unit×divisor)다. 단일 항목으로 목표에 못 닿는 조합이 있어서
    (수량이 제각각이면 걸음 크기도 제각각) 쌍까지 완전탐색한다 — 항목 수가 수십 개라
    조합 수가 수천 개 수준이고 순수 산술이라 비용은 무시할 만하다.

    굵은 단위로 못 닿으면 만원 단위로 한 번 더 시도한다. 블렌디드랩처럼 공급가액이 단가
    그대로인 양식은 걸음이 전부 10만원이라 도달 가능한 총액이 10만원 배수뿐인데, 목표가
    30,030,000원(본견적 27,300,000 × 1.1)이면 30,000원이 남아 사용자가 지정한 +10%가
    화면에 +9.9%로 찍혔다(2026-08-21 사용자 지적).
    """
    # 굵은 격자 → 잔 격자 순으로 정확히 맞춰보고, 둘 다 정확히는 못 맞추면 마지막으로
    # "가장 가까이" 가는 조합이라도 적용한다. 예전엔 정확히 못 맞추면 아무것도 안 해서
    # 목표에서 크게 벗어난 채 저장됐다(2026-08-21).
    for step in (min(form.unit_price_unit, 100_000), CLEAN_UNIT):
        if _absorb_at(items, diff, form, log, step, exact=True):
            return log
    _absorb_at(items, diff, form, log, CLEAN_UNIT, exact=False)
    return log


def _absorb_at(items: List[dict], diff: int, form: FormSpec, log: List[str], unit: int, exact: bool) -> bool:
    steps = [unit * form.divisor(it) for it in items]
    limits = [max(1, int((it.get("unit_price") or 0) * MAX_MOVE_RATIO // unit)) for it in items]

    def valid(idx: Tuple[int, ...], ks: Tuple[int, ...]) -> bool:
        return all(
            abs(k) <= limits[i] and (items[i]["unit_price"] + k * unit) > 0
            for i, k in zip(idx, ks)
        )

    candidates = [
        ((i,), (k,))
        for i in range(len(items))
        for k in range(-limits[i], limits[i] + 1)
        if k
    ]
    if MAX_MOVED_ITEMS >= 2:
        candidates += [
            (pair, ks)
            for pair in combinations(range(len(items)), 2)
            for ks in product(range(-3, 4), repeat=2)
            if all(ks)
        ]

    best = None  # (|잔여|, 움직인 항목 수, 총 이동량, idx, ks)
    for idx, ks in candidates:
        if not valid(idx, ks):
            continue
        rest = abs(diff - sum(k * steps[i] for i, k in zip(idx, ks)))
        score = (rest, len(idx), sum(abs(k) for k in ks))
        if best is None or score < best[0]:
            best = (score, idx, ks)

    if not best or (best[0][0] != 0 if exact else best[0][0] >= abs(diff)):
        return False
    for i, k in zip(best[1], best[2]):
        it = items[i]
        before = it["unit_price"]
        it["unit_price"] = before + k * unit
        it["amount"] = form.amount_of(it)
        log.append(f"총액 맞춤: {it['name']} 단가 {int(before):,} → {int(it['unit_price']):,}")
    return True


def finalize(
    items: List[dict], target_supply: Optional[int], form: FormSpec
) -> Tuple[List[dict], int, List[str]]:
    """AI가 산정한 항목을 발급 가능한 값으로 확정한다. (항목, 잔액, 로그)를 돌려준다.

    1단계 — 금액은 언제나 양식 수식으로 재계산한다(AI가 준 amount는 버린다).
    2단계 — 만원 단위로 안 떨어지는 '지저분한' 단가만 정리한다.
    3단계 — 남은 차액을 최대 2개 항목의 단가로만 흡수하고, 움직인 항목을 전부 로그로 남긴다.

    target_supply가 None이면 3단계를 건너뛴다 — **사용자가 직접 고친 값에는 절대 이 함수를
    쓰지 않는다**는 게 재설계의 핵심이지만, 목표 없이 수식 정합성만 맞추고 싶은 경로
    (예: 발급 직전 검산)가 있어서 열어둔다.

    잔액이 0이 아닌 채 돌아올 수 있다. 격자상 목표에 못 닿는 구성이면 가장 가까운 값까지만
    가고 그대로 둔다 — 억지로 맞추려고 항목을 더 움직이는 게 실무자가 싫어하던 동작이다.
    화면이 이 잔액을 그대로 보여주고, 필요하면 사용자가 직접 고친다(2026-08-20 결정).
    """
    items = [dict(it) for it in items]
    log: List[str] = []

    # 작업일·수량은 "며칠", "몇 회/몇 인"이라 소수가 될 수 없다. AI가 본견적 대비 0.7~1.5배로
    # 조정하다 13.44회·1.08개 같은 값을 내놨고, 그 값을 금액에 곱하는 양식(알파브라더스)에서
    # 금액이 만원 단위로 안 떨어졌다(2026-08-21 재현). 프롬프트에도 정수라고 못 박았지만
    # 지켜지지 않을 수 있으므로 여기서 확정한다.
    for it in items:
        for key in ("work_days", "quantity"):
            if it.get(key) is not None:
                it[key] = max(1, round(float(it[key])))
        it["amount"] = form.amount_of(it)

    if target_supply is not None:
        # ── 0단계. AI 합계가 목표에서 크게 벗어나면 전 항목 단가에 같은 배율을 곱해 먼저 좁힌다.
        # 흡수(3단계)는 항목당 35%까지만 움직이는 미세 조정이라 큰 격차를 못 메운다. 실제로
        # 블렌디드랩(공급가액=단가) 양식에서 AI가 수량을 곱하는 줄 알고 45% 낮게 산정했는데,
        # finalize가 "격자상 도달 불가"라며 아무것도 안 해 본견적보다 싼 비교견적이 나왔다
        # (2026-08-21 사용자 지적). 같은 배율을 곱하면 항목 간 상대 중요도는 그대로 유지된다.
        current = sum(it["amount"] for it in items)
        if current > 0 and abs(target_supply - current) > target_supply * _RESCALE_THRESHOLD:
            factor = target_supply / current
            for it in items:
                it["unit_price"] = (it.get("unit_price") or 0) * factor
                it["amount"] = form.amount_of(it)
            log.append(f"전체 배율 조정 ×{factor:.3f} (AI 산정 {current:,}원 → 목표 {target_supply:,}원)")

    for it in items:
        if not _is_ugly(it):
            continue
        before = it.get("unit_price") or 0
        snapped = max(form.unit_price_unit, round(before / form.unit_price_unit) * form.unit_price_unit)
        it["unit_price"] = snapped
        it["amount"] = form.amount_of(it)
        if snapped != before:
            log.append(f"단가 정리: {it['name']} {int(before):,} → {int(snapped):,}")

    if target_supply is None:
        for it in items:
            it.update(form.derived(it))
        return items, 0, log

    diff = target_supply - sum(it["amount"] for it in items)
    if diff and items:
        _absorb(items, diff, form, log)
    for it in items:
        it.update(form.derived(it))
    residual = target_supply - sum(it["amount"] for it in items)
    if residual:
        log.append(f"격자상 도달 불가 잔액 {residual:+,}원 — 자동 흡수하지 않고 그대로 표시")
    return items, residual, log


def grand_total(supply_amount: float, vat_included: bool) -> int:
    """공급가액 소계 -> VAT 포함 총액."""
    return round(supply_amount * 1.1) if vat_included else round(supply_amount + round(supply_amount * 0.1))


# ═══════════════════════════════════════════════════════════════════════
# 불변식 검사 — 저장 직전 마지막 관문
# ═══════════════════════════════════════════════════════════════════════
# 2026-08-21까지 잘못된 견적서가 여러 번 그대로 저장돼 사용자가 화면에서 먼저 발견했다
# (부가세 이중 계산, 인상률 9.9%, 목표의 55%만 채운 비교견적, 13.44회 같은 소수 수량).
# finalize가 "고치려고 시도"는 하지만 결과를 아무도 검사하지 않은 게 원인이다. 이제
# 구조적 위반은 저장 자체가 막힌다 — 조용히 틀린 견적서가 나가느니 생성이 실패하는 게 낫다.


def structural_violations(items: List[dict], form: FormSpec) -> List[str]:
    """절대 일어나면 안 되는 위반. 하나라도 있으면 저장하지 않는다.

    잔액(목표와의 차이)은 여기 넣지 않는다 — 격자상 도달 불가는 정당한 결과이고 화면에
    표시하면 되지만, 아래 셋은 어떤 이유로도 정상일 수 없다.
    """
    bad: List[str] = []
    for it in items:
        name = it.get("name", "?")
        if form.amount_of(it) != it.get("amount"):
            bad.append(f"{name}: 금액 {it.get('amount'):,}이 양식 수식({form.formula_text}) 결과 {form.amount_of(it):,}와 다름")
        if (it.get("unit_price") or 0) % CLEAN_UNIT or (it.get("amount") or 0) % CLEAN_UNIT:
            bad.append(f"{name}: 단가/금액이 만원 단위가 아님 ({it.get('unit_price')}, {it.get('amount')})")
        for key in ("work_days", "quantity"):
            v = it.get(key)
            if v is not None and float(v) != int(v):
                bad.append(f"{name}: {key}가 정수가 아님 ({v})")
    return bad


def assert_storable(items: List[dict], form: FormSpec, label: str) -> None:
    """저장 직전 호출한다. 위반이 있으면 예외를 던져 잘못된 견적서를 막는다."""
    bad = structural_violations(items, form)
    if bad:
        raise ValueError(f"{label} 견적서가 불변식을 위반했습니다:\n  - " + "\n  - ".join(bad))
