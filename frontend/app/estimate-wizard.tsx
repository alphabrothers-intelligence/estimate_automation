"use client";

import { useEffect, useRef, useState } from "react";
import {
  ApiError,
  createEstimateSet,
  editEntityQuote,
  fetchCatalogModuleOptions,
  fetchEntities,
  fetchEstimateSet,
  fetchModuleOptions,
  generateEstimateSet,
  getEntityQuotePdfUrl,
  getEntityQuoteXlsxUrl,
  updateLineItems,
  updateServiceName,
  type CatalogModuleOptions,
  type EntityModuleOptions,
  type EntityOption,
  type EntityQuote,
  type EstimateSet,
  type LineItem,
  type ModuleGroup,
  type ModuleOption,
} from "@/lib/api";

// 견적 내용이 바뀔 때만 PDF 미리보기를 다시 불러오게 하는 캐시버스터 키.
// LibreOffice 변환이 매 요청 1~2초 걸려서, 무관한 리렌더마다 새로 부르면 안 된다.
function hashKey(value: unknown): string {
  const str = JSON.stringify(value);
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = (hash * 31 + str.charCodeAt(i)) | 0;
  }
  return hash.toString(36);
}

const MAX_COMPARISON = 3;
const TESTIFY_NAME = "테스티파이"; // '용역명' 필드는 테스티파이 템플릿에만 있음 (4.2)

// 2026-08 마법사 개편: 기업을 먼저 고르고 과업(마케팅/시장검증)을 나중에, 기업별로 교차
// 선택한다. 두 과업종류만 이 마법사에서 다룬다 — "고객검증"은 이번 개편 범위 밖.
// ("광고대행"은 별도 과업종류가 아니라 마케팅 안의 대안 상품(alt_group)이라 여기 포함됨 — v0.6)
const FIXED_TASK_TYPES = ["마케팅", "시장검증"] as const;
type FixedTaskType = (typeof FIXED_TASK_TYPES)[number];

// MVP 방향: "과업종류 + 총액만 입력하면 바로 항목·금액이 자동 생성"이 핵심 가치라서, 항목 구성을
// PM이 직접 고르는 단계는 지금 단계에서는 건너뛴다 (각 대안 그룹의 기본값으로 자동 생성하고,
// 결과가 안 맞으면 채팅/직접 수정으로 고치는 흐름). 이미 만들어둔 선택 UI/API는 지우지 않고
// 이 플래그로 꺼두는 것뿐이라, 나중에 PM이 직접 고르는 기능이 다시 필요해지면 true로 되돌리면 된다.
const ENABLE_MODULE_SELECTION_UI = false;

const SCOPE_LABEL: Record<string, string> = {
  quote_only: "이번 견적만",
  catalog_update: "카탈로그 갱신 필요",
  ambiguous: "범위 확인 필요",
};

type ChatMessage = {
  role: "user" | "assistant";
  text: string;
  scope?: string;
};

// 단계 제목 앞의 번호를 원 배지로 보여준다 — 실제 서비스 마법사 화면의 흔한 패턴.
function StepHeader({ n, title, hint }: { n: number; title: string; hint?: string }) {
  return (
    <legend className="flex flex-wrap items-center gap-2.5 text-base font-semibold text-gray-900">
      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-indigo-600 text-xs font-bold text-white">
        {n}
      </span>
      {title}
      {hint && <span className="text-sm font-normal text-gray-400">{hint}</span>}
    </legend>
  );
}

// 토글 스위치(마케팅/시장검증 포함 여부)와 라디오/체크박스 카드(variant·additive 모듈 선택) 전부
// 네이티브 input 그대로 두면 못생겨 보인다는 피드백(2026-08-09)에 따라 만든 커스텀 표시자.
// 접근성을 위해 실제 input은 남기고 화면에서만 숨긴다(sr-only).
function ToggleSwitch({ checked, onLabel }: { checked: boolean; onLabel: string }) {
  return (
    <span className="flex items-center gap-2.5">
      <span
        className={
          "relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors " +
          (checked ? "bg-indigo-600" : "bg-gray-300")
        }
      >
        <span
          className={
            "inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform " +
            (checked ? "translate-x-6" : "translate-x-1")
          }
        />
      </span>
      <span className="text-sm font-semibold text-gray-900">{onLabel}</span>
    </span>
  );
}

function OptionIndicator({ checked, shape }: { checked: boolean; shape: "circle" | "check" }) {
  if (shape === "circle") {
    return (
      <span
        className={
          "mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border-2 transition-colors " +
          (checked ? "border-indigo-600" : "border-gray-300")
        }
      >
        {checked && <span className="h-1.5 w-1.5 rounded-full bg-indigo-600" />}
      </span>
    );
  }
  return (
    <span
      className={
        "mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded border-2 transition-colors " +
        (checked ? "border-indigo-600 bg-indigo-600" : "border-gray-300 bg-white")
      }
    >
      {checked && (
        <svg viewBox="0 0 12 12" fill="none" className="h-2.5 w-2.5">
          <path d="M2 6l2.5 2.5L10 3" stroke="white" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )}
    </span>
  );
}

// 클릭 가능한 카드 하나 전체가 라디오/체크박스 역할을 한다 — 작은 원형 버튼만 누를 수 있던
// 기존 방식보다 클릭 영역이 넓고, 선택 상태가 카드 배경・테두리 색으로 바로 보인다.
function OptionRow({
  shape,
  checked,
  name,
  onChange,
  children,
}: {
  shape: "circle" | "check";
  checked: boolean;
  name?: string;
  onChange: () => void;
  children: React.ReactNode;
}) {
  return (
    <label
      className={
        "flex cursor-pointer items-start gap-2.5 rounded-lg border px-3 py-2.5 transition-colors " +
        (checked ? "border-indigo-300 bg-indigo-50/70" : "border-gray-200 bg-white hover:border-gray-300")
      }
    >
      <input
        type={shape === "circle" ? "radio" : "checkbox"}
        name={name}
        checked={checked}
        onChange={onChange}
        className="sr-only"
      />
      <OptionIndicator checked={checked} shape={shape} />
      <div className="min-w-0 flex-1 text-sm text-gray-800">{children}</div>
    </label>
  );
}

// 예전엔 "용역명 입력 필요" 배지를 먼저 보여주고 클릭해야 입력창이 나왔는데, 그 문구를
// 입력칸 자체의 placeholder로 옮겨서 클릭 한 번 없이 바로 타이핑해 채울 수 있게 한다
// (2026-08-09 사용자 피드백). InlineEditCell과 같은 blur/Enter 저장 패턴을 그대로 따른다.
function ServiceNameField({
  quote,
  onSave,
}: {
  quote: EntityQuote;
  onSave: (value: string) => Promise<void>;
}) {
  const [value, setValue] = useState(quote.service_name ?? "");
  const [saving, setSaving] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  async function handleSave() {
    const trimmed = value.trim();
    if (!trimmed || trimmed === quote.service_name || saving) return;
    setSaving(true);
    setErrorMsg(null);
    try {
      await onSave(trimmed);
    } catch (e) {
      setErrorMsg(e instanceof ApiError ? e.message : "저장에 실패했습니다.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mt-2 flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
      <input
        type="text"
        value={value}
        disabled={saving}
        onChange={(e) => setValue(e.target.value)}
        onBlur={handleSave}
        onKeyDown={(e) => e.key === "Enter" && handleSave()}
        placeholder="용역명을 입력하세요 (예: 정량, 정성 데이터 기반 시장 검증 용역) — 발급 전 필수"
        className={
          "flex-1 rounded-md border px-2 py-1 text-sm focus:border-indigo-500 focus:outline-none " +
          (quote.service_name ? "border-gray-300" : "border-amber-300 bg-amber-50")
        }
      />
      {saving && <span className="shrink-0 text-xs text-gray-400">저장 중…</span>}
      {errorMsg && <p className="text-sm text-red-600">{errorMsg}</p>}
    </div>
  );
}

function ModuleOptionRow({
  option,
  label,
  inputType,
  name,
  checked,
  onChange,
}: {
  option: ModuleOption;
  label: string;
  inputType: "radio" | "checkbox";
  name?: string;
  checked: boolean;
  onChange: () => void;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <OptionRow shape={inputType === "radio" ? "circle" : "check"} checked={checked} name={name} onChange={onChange}>
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
        <span className="font-medium text-gray-900">{label}</span>
        <button
          type="button"
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            setExpanded((v) => !v);
          }}
          className="shrink-0 text-xs font-medium text-indigo-600 hover:underline"
        >
          {expanded ? "항목 접기" : `${option.item_count}개 항목 보기`}
        </button>
      </div>
      {expanded && (
        <div className="mt-1.5 space-y-2 border-t border-indigo-100 pt-1.5">
          {option.item_groups.map((group) => (
            <div key={group.module_name}>
              {option.item_groups.length > 1 && (
                <p className="text-xs font-semibold text-gray-700">{group.module_name}</p>
              )}
              <ul className="space-y-1">
                {group.item_names.map((name, i) => (
                  <li key={i} className="flex gap-1.5 text-xs leading-relaxed text-gray-500">
                    <span className="text-gray-400">•</span>
                    {name}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </OptionRow>
  );
}

function TaskModulePicker({
  entityId,
  taskType,
  included,
  moduleNames,
  options,
  onToggleIncluded,
  onSetVariant,
  onToggleAdditive,
}: {
  entityId: string;
  taskType: string;
  included: boolean;
  moduleNames: string[];
  options: CatalogModuleOptions | undefined;
  onToggleIncluded: (included: boolean) => void;
  onSetVariant: (group: ModuleGroup, option: ModuleOption) => void;
  onToggleAdditive: (option: ModuleOption, checked: boolean) => void;
}) {
  const hasModules = options?.has_modules ?? false;

  return (
    <div
      className={
        "rounded-xl border p-4 transition-colors " +
        (included ? "border-indigo-200 bg-indigo-50/40" : "border-gray-200 bg-white")
      }
    >
      <label className="flex cursor-pointer items-center justify-between">
        <ToggleSwitch checked={included} onLabel={`${taskType} 포함`} />
        <input
          type="checkbox"
          checked={included}
          onChange={(e) => onToggleIncluded(e.target.checked)}
          className="sr-only"
        />
      </label>
      {included && hasModules && (
        <div className="mt-3 space-y-3 border-t border-indigo-100 pt-3">
          {(options?.groups ?? []).map((group, gi) => (
            <div key={gi} className="space-y-1.5">
              {(group.label || group.kind === "additive") && (
                <p className="text-xs font-semibold text-gray-400">
                  {group.label ?? "추가 옵션"}
                </p>
              )}
              {group.options.map((o) => {
                const isChecked = o.module_names.every((m) => moduleNames.includes(m));
                return (
                  <ModuleOptionRow
                    key={o.option_key}
                    option={o}
                    label={o.label}
                    inputType={group.kind === "variant" ? "radio" : "checkbox"}
                    name={group.kind === "variant" ? `variant-${entityId}-${taskType}-${gi}` : undefined}
                    checked={isChecked}
                    onChange={() =>
                      group.kind === "variant" ? onSetVariant(group, o) : onToggleAdditive(o, !isChecked)
                    }
                  />
                );
              })}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// 원본 배열에서 몇 번째 항목인지(_index)를 들고 있어야, 직접 편집으로 그룹 안의 항목 하나를
// 고쳤을 때 원본 line_items 배열의 어느 자리를 바꿔야 하는지 알 수 있다.
type IndexedLineItem = LineItem & { _index: number };
type LineItemGroup = { category: string; amount: number; items: IndexedLineItem[] };
type LineItemPatch = Partial<
  Pick<
    LineItem,
    "category" | "name" | "amount" | "unit_price" | "work_days" | "quantity" | "note" | "description" | "input_mm" | "tax_amount"
  >
>;

function groupLineItems(items: LineItem[]): LineItemGroup[] {
  const groups: LineItemGroup[] = [];
  items.forEach((item, index) => {
    const last = groups[groups.length - 1];
    if (last && last.category === item.category) {
      last.items.push({ ...item, _index: index });
      last.amount += item.amount;
    } else {
      groups.push({ category: item.category, amount: item.amount, items: [{ ...item, _index: index }] });
    }
  });
  return groups;
}

// 클릭하면 입력창이 되는 셀 — Enter/포커스 아웃으로 저장, Esc로 취소(ServiceNameField와 같은
// 인라인 편집 패턴). 항목명・카테고리・금액뿐 아니라 단가/작업일/투입인력/비고도 이 컴포넌트로
// 편집한다(2026-08-09 편집 범위 확장 — LineItemTable.handleEditItem 참고).
function InlineEditCell({
  value,
  display,
  align = "left",
  inputType = "text",
  onSave,
}: {
  value: string;
  display: string;
  align?: "left" | "right";
  inputType?: "text" | "number";
  onSave: (nextValue: string) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const [saving, setSaving] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  async function handleSave() {
    if (saving) return;
    if (draft === value) {
      setEditing(false);
      return;
    }
    if (inputType === "number" && (draft.trim() === "" || Number.isNaN(Number(draft)))) {
      setErrorMsg("숫자를 입력하세요.");
      return;
    }
    setSaving(true);
    setErrorMsg(null);
    try {
      await onSave(draft);
      setEditing(false);
    } catch (e) {
      setErrorMsg(e instanceof ApiError ? e.message : "저장에 실패했습니다.");
    } finally {
      setSaving(false);
    }
  }

  if (editing) {
    return (
      <div onClick={(e) => e.stopPropagation()}>
        <input
          type={inputType}
          autoFocus
          value={draft}
          disabled={saving}
          onChange={(e) => setDraft(e.target.value)}
          onFocus={(e) => e.target.select()}
          onBlur={handleSave}
          onKeyDown={(e) => {
            if (e.key === "Enter") handleSave();
            if (e.key === "Escape") {
              setDraft(value);
              e.currentTarget.blur();
            }
          }}
          className={
            "w-full rounded border border-indigo-400 px-1.5 py-0.5 text-sm focus:outline-none " +
            (align === "right" ? "text-right" : "text-left")
          }
        />
        {errorMsg && <p className="mt-0.5 text-xs text-red-600">{errorMsg}</p>}
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        setDraft(value);
        setEditing(true);
      }}
      title="클릭해서 수정"
      className={
        "w-full whitespace-pre-line rounded px-1 py-0.5 hover:bg-indigo-50 " +
        (align === "right" ? "text-right" : "text-left")
      }
    >
      {display}
    </button>
  );
}

// 법인마다 실제 원본 양식의 컬럼 명칭·순서가 다르다(예: 알파브라더스는 "작업일/수량", ABBG는
// 같은 의미인데 "소요일/작업수량", 테스티파이는 순서 자체가 단가→작업일→투입 인력). 백엔드가
// 각 법인의 실제 템플릿에서 계산해 내려주는 column_labels/detail_column_order를 그대로 쓰고,
// 혹시 못 받아온 경우(구형 데이터 등)에만 아래 기본값으로 대체한다(2026-07-10).
const DEFAULT_COLUMN_LABELS: Record<string, string> = {
  item_name: "항목",
  unit_price: "단가",
  work_days: "작업일",
  quantity: "수량",
  supply_amount: "공급가액",
};
const DEFAULT_DETAIL_ORDER = ["work_days", "quantity", "unit_price"];

// 텍스트로 다루는 상세 컬럼(예: 알파브라더스 상품구성) — 나머지는 전부 숫자 컬럼.
const TEXT_DETAIL_KEYS = new Set(["description"]);

function renderDetailValue(item: LineItem, key: string): string {
  if (key === "unit_price") return item.unit_price != null ? `${item.unit_price.toLocaleString()}원` : "—";
  if (key === "work_days") return item.work_days != null ? `${item.work_days}일` : "—";
  if (key === "quantity") return item.quantity != null ? String(item.quantity) : "—";
  if (key === "description") return item.description ?? "—";
  if (key === "input_mm") return item.input_mm != null ? `${item.input_mm}MM` : "—";
  if (key === "tax_amount") return item.tax_amount != null ? `${item.tax_amount.toLocaleString()}원` : "—";
  return "—";
}

function renderDetailEditValue(item: LineItem, key: string): string {
  if (key === "description") return item.description ?? "";
  const raw =
    key === "unit_price"
      ? item.unit_price
      : key === "work_days"
        ? item.work_days
        : key === "input_mm"
          ? item.input_mm
          : key === "tax_amount"
            ? item.tax_amount
            : item.quantity;
  return raw != null ? String(raw) : "0";
}

// 단가/작업일/투입인력은 서로 맞물려 있다 — 실제 발급되는 PDF의 공급가액 칸이 원본 수식
// (단가×작업일×투입인력)으로 계산되므로, 셋 중 하나를 편집키로 저장하면(LineItemTable.
// handleEditItem) 화면과 실제 발급본이 어긋난다. 그래서 각 칸을 patch key로 구분해 보낸다.
function ItemDetailCells({
  item,
  order,
  onEditItem,
}: {
  item: LineItem;
  order: string[];
  onEditItem: (patch: LineItemPatch) => Promise<void>;
}) {
  return (
    <>
      {order.map((key) => {
        const isText = TEXT_DETAIL_KEYS.has(key);
        return (
          <td
            key={key}
            className={"py-2 pr-3 text-sm text-gray-600 " + (isText ? "text-left" : "text-right")}
          >
            <InlineEditCell
              value={renderDetailEditValue(item, key)}
              display={renderDetailValue(item, key)}
              align={isText ? "left" : "right"}
              inputType={isText ? "text" : "number"}
              onSave={(v) => onEditItem({ [key]: isText ? v : Number(v) } as LineItemPatch)}
            />
          </td>
        );
      })}
    </>
  );
}

function CategoryRows({
  group,
  order,
  hasNote,
  showCategorySplit,
  highlightKeys,
  onEditItem,
}: {
  group: LineItemGroup;
  order: string[];
  hasNote: boolean;
  showCategorySplit: boolean;
  highlightKeys?: Set<string>;
  onEditItem: (index: number, patch: LineItemPatch) => Promise<void>;
}) {
  const [expanded, setExpanded] = useState(true);
  const isFlat = group.items.length === 1 && group.items[0].name === group.category;
  // 채팅 수정으로 방금 바뀐 항목에 왼쪽 강조선 + 옅은 배경을 준다 — "어디가 수정되고 있는지
  // 모르겠다"는 피드백(2026-08-10) 대응. 다음 수정이나 항목 재생성 전까지 유지된다.
  const isChanged = (item: { category: string; name: string }) =>
    highlightKeys?.has(`${item.category}::${item.name}`) ?? false;
  // 알파브라더스 원본 양식은 구분(대)/구분(중) 두 칸에 같은 과업종류명을 그대로 쓴다
  // (pdf_service._collect_item_block_updates의 group_task_type과 동일한 값).
  const splitCells = (taskType?: string) =>
    showCategorySplit && (
      <>
        <td className="px-3 py-2.5 text-sm text-gray-600">{taskType ?? "—"}</td>
        <td className="px-3 py-2.5 text-sm text-gray-600">{taskType ?? "—"}</td>
      </>
    );

  if (isFlat) {
    const item = group.items[0];
    return (
      <tr
        className={
          "border-b border-gray-200 last:border-b-0 " +
          (isChanged(item) ? "border-l-4 border-l-amber-400 bg-amber-50" : "bg-white")
        }
      >
        {splitCells(item.task_type)}
        <td className="px-3 py-2.5 text-gray-800">
          <InlineEditCell
            value={group.category}
            display={group.category}
            onSave={(v) => onEditItem(item._index, { category: v, name: v })}
          />
        </td>
        <ItemDetailCells item={item} order={order} onEditItem={(patch) => onEditItem(item._index, patch)} />
        <td className="px-3 py-2.5 text-right font-semibold text-gray-900">
          <InlineEditCell
            value={String(item.amount)}
            display={`${group.amount.toLocaleString()}원`}
            align="right"
            inputType="number"
            onSave={(v) => onEditItem(item._index, { amount: Number(v) })}
          />
        </td>
        {hasNote && (
          <td className="px-3 py-2.5 text-sm text-gray-600">
            <InlineEditCell
              value={item.note ?? ""}
              display={item.note ?? ""}
              onSave={(v) => onEditItem(item._index, { note: v })}
            />
          </td>
        )}
      </tr>
    );
  }

  return (
    <>
      <tr className="border-b border-gray-200 bg-white last:border-b-0">
        {splitCells(group.items[0]?.task_type)}
        <td className="px-3 py-2.5 font-bold text-gray-900">
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="flex items-center gap-1.5"
          >
            <svg
              viewBox="0 0 20 20"
              fill="currentColor"
              className={"h-3.5 w-3.5 shrink-0 text-gray-500 transition-transform " + (expanded ? "rotate-90" : "")}
            >
              <path fillRule="evenodd" d="M6 4l8 6-8 6V4z" clipRule="evenodd" />
            </svg>
            {group.category}
          </button>
        </td>
        <td className="py-2 pr-3 text-right text-sm text-gray-400" colSpan={order.length} />
        <td className="px-3 py-2.5 text-right font-bold text-gray-900">
          {group.amount.toLocaleString()}원
        </td>
        {hasNote && <td className="px-3 py-2.5" />}
      </tr>
      {expanded &&
        group.items.map((item) => (
          <tr
            key={item._index}
            className={
              "border-b border-gray-200 last:border-b-0 " +
              (isChanged(item) ? "border-l-4 border-l-amber-400 bg-amber-50" : "bg-gray-50")
            }
          >
            {splitCells(item.task_type)}
            <td className="py-2 pl-9 pr-3 text-sm text-gray-700">
              <InlineEditCell
                value={item.name}
                display={item.name}
                onSave={(v) => onEditItem(item._index, { name: v })}
              />
            </td>
            <ItemDetailCells item={item} order={order} onEditItem={(patch) => onEditItem(item._index, patch)} />
            <td className="py-2 pr-3 text-right text-sm text-gray-700">
              <InlineEditCell
                value={String(item.amount)}
                display={`${item.amount.toLocaleString()}원`}
                align="right"
                inputType="number"
                onSave={(v) => onEditItem(item._index, { amount: Number(v) })}
              />
            </td>
            {hasNote && (
              <td className="py-2 pr-3 text-sm text-gray-600">
                <InlineEditCell
                  value={item.note ?? ""}
                  display={item.note ?? ""}
                  onSave={(v) => onEditItem(item._index, { note: v })}
                />
              </td>
            )}
          </tr>
        ))}
    </>
  );
}

// 실제 원본 양식은 항목 표 맨 아래에 공급가액 소계・부가세・총합계가 늘 붙어 있다(PRD 4.2 —
// 테스티파이는 "부가세 10% 행 + 총합계", 썬데이워커는 항목별 세액 후 합계 등). 발급되는
// PDF/xlsx와 같은 값이 나오도록 pdf_service._build_filled_xlsx와 동일한 계산식을 그대로 쓴다.
// ponytail: JS Math.round는 절반을 항상 올림, Python round()는 은행가 반올림(.5를 짝수로) —
// 나눗셈 결과가 정확히 .5로 떨어지는 극히 드문 금액에서 이 미리보기가 실제 발급본과 1원 차이날
// 수 있음. 실제 발급 금액은 항상 서버(pdf_service)가 최종 계산하므로 이 화면은 참고용.
function computeVatBreakdown(totalAmount: number, vatIncluded: boolean) {
  const supplyAmount = vatIncluded ? Math.round(totalAmount / 1.1) : totalAmount;
  const vatAmount = vatIncluded ? totalAmount - supplyAmount : Math.round(supplyAmount * 0.1);
  const grandTotal = vatIncluded ? totalAmount : supplyAmount + vatAmount;
  return { supplyAmount, vatAmount, grandTotal };
}

function LineItemTable({
  items,
  columnLabels,
  detailColumnOrder,
  totalAmount,
  vatIncluded,
  showCategorySplit = false,
  highlightKeys,
  onSaveLineItems,
}: {
  items: LineItem[];
  columnLabels: Record<string, string>;
  detailColumnOrder: string[];
  totalAmount: number;
  vatIncluded: boolean;
  showCategorySplit?: boolean;
  highlightKeys?: Set<string>;
  onSaveLineItems: (items: LineItem[]) => Promise<void>;
}) {
  const groups = groupLineItems(items);
  const order = detailColumnOrder.length > 0 ? detailColumnOrder : DEFAULT_DETAIL_ORDER;
  const labelFor = (key: string) => columnLabels[key] ?? DEFAULT_COLUMN_LABELS[key] ?? key;
  const hasNote = Boolean(columnLabels.note);
  const labelColSpan = (showCategorySplit ? 2 : 0) + 1 + order.length;
  const { supplyAmount, vatAmount, grandTotal } = computeVatBreakdown(totalAmount, vatIncluded);

  async function handleEditItem(index: number, patch: LineItemPatch) {
    const merged: LineItem = { ...items[index], ...patch };
    // 실제 발급 PDF의 공급가액 칸은 원본 수식(단가×작업일×투입인력)으로 재계산되므로, 화면에서
    // 어느 값을 고치든 세 값의 곱과 공급가액이 항상 일치하도록 나머지를 다시 계산해서 보낸다
    // (2026-08-09 — 단가/작업일/투입인력 직접편집 추가, pdf_service._compute_item_pricing과 짝).
    if ("amount" in patch) {
      const divisor = (merged.work_days ?? 1) * (merged.quantity ?? 1);
      merged.unit_price = divisor ? merged.amount / divisor : merged.amount;
    } else if ("unit_price" in patch || "work_days" in patch || "quantity" in patch) {
      merged.amount = Math.round((merged.unit_price ?? 0) * (merged.work_days ?? 1) * (merged.quantity ?? 1));
    }
    const next = items.map((item, i) => (i === index ? merged : item));
    await onSaveLineItems(next);
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
      <table className="w-full min-w-[560px] border-collapse text-base">
        <thead>
          <tr className="border-b border-gray-200 bg-gray-100">
            {showCategorySplit && (
              <>
                <th className="px-3 py-2 text-left text-sm font-semibold text-gray-600">
                  {columnLabels.category_large ?? "구분(대)"}
                </th>
                <th className="px-3 py-2 text-left text-sm font-semibold text-gray-600">
                  {columnLabels.category_mid ?? "구분(중)"}
                </th>
              </>
            )}
            <th className="px-3 py-2 text-left text-sm font-semibold text-gray-600">
              {labelFor("item_name")}
            </th>
            {order.map((key) => (
              <th
                key={key}
                className={
                  "px-3 py-2 text-sm font-semibold text-gray-600 " +
                  (TEXT_DETAIL_KEYS.has(key) ? "text-center" : "text-right")
                }
              >
                {labelFor(key)}
              </th>
            ))}
            <th className="px-3 py-2 text-right text-sm font-semibold text-gray-600">
              {columnLabels.supply_amount ?? columnLabels.amount ?? DEFAULT_COLUMN_LABELS.supply_amount}
            </th>
            {hasNote && (
              <th className="px-3 py-2 text-left text-sm font-semibold text-gray-600">
                {columnLabels.note}
              </th>
            )}
          </tr>
        </thead>
        <tbody>
          {groups.map((g, gi) => (
            <CategoryRows
              key={gi}
              group={g}
              order={order}
              hasNote={hasNote}
              showCategorySplit={showCategorySplit}
              highlightKeys={highlightKeys}
              onEditItem={handleEditItem}
            />
          ))}
        </tbody>
        <tfoot className="border-t-2 border-gray-300 bg-gray-50">
          <tr className="border-b border-gray-200">
            <td className="px-3 py-2 text-right text-sm text-gray-500" colSpan={labelColSpan}>
              공급가액 소계
            </td>
            <td className="px-3 py-2 text-right text-sm text-gray-700">
              {supplyAmount.toLocaleString()}원
            </td>
            {hasNote && <td className="px-3 py-2" />}
          </tr>
          <tr className="border-b border-gray-200">
            <td className="px-3 py-2 text-right text-sm text-gray-500" colSpan={labelColSpan}>
              부가세 (10%)
            </td>
            <td className="px-3 py-2 text-right text-sm text-gray-700">
              {vatAmount.toLocaleString()}원
            </td>
            {hasNote && <td className="px-3 py-2" />}
          </tr>
          <tr>
            <td className="px-3 py-2.5 text-right text-sm font-bold text-gray-900" colSpan={labelColSpan}>
              총합계
            </td>
            <td className="px-3 py-2.5 text-right text-base font-bold text-indigo-700">
              {grandTotal.toLocaleString()}원
            </td>
            {hasNote && <td className="px-3 py-2.5" />}
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

function ComparisonSummaryTable({ quotes, primaryTotal }: { quotes: EntityQuote[]; primaryTotal?: number }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white">
      <table className="w-full min-w-[480px] text-sm">
        <thead className="border-b border-gray-200 bg-gray-50 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
          <tr>
            <th className="px-4 py-2.5">법인</th>
            <th className="px-4 py-2.5">구분</th>
            <th className="px-4 py-2.5 text-right">총액</th>
            <th className="px-4 py-2.5 text-right">본견적 대비</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {quotes.map((q) => {
            const diffPercent =
              !q.is_primary && primaryTotal ? ((q.total_amount - primaryTotal) / primaryTotal) * 100 : null;
            return (
              <tr key={q.id}>
                <td className="px-4 py-2.5 font-medium text-gray-900">{q.entity_name}</td>
                <td className="px-4 py-2.5">
                  <span
                    className={
                      q.is_primary
                        ? "rounded-full bg-indigo-100 px-2 py-0.5 text-xs font-semibold text-indigo-700"
                        : "rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600"
                    }
                  >
                    {q.is_primary ? "본견적" : "비교견적"}
                  </span>
                </td>
                <td className="px-4 py-2.5 text-right font-semibold text-gray-900">
                  {q.total_amount.toLocaleString()}원
                </td>
                <td
                  className={
                    "px-4 py-2.5 text-right text-sm font-semibold " +
                    (diffPercent === null
                      ? "text-gray-300"
                      : diffPercent > 0
                      ? "text-rose-600"
                      : diffPercent < 0
                      ? "text-blue-600"
                      : "text-gray-400")
                  }
                >
                  {diffPercent === null ? "-" : `${diffPercent > 0 ? "+" : ""}${diffPercent.toFixed(1)}%`}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function QuoteCard({
  quote,
  vatIncluded,
  onOpenChat,
  onSaveServiceName,
  onSaveLineItems,
}: {
  quote: EntityQuote;
  vatIncluded: boolean;
  onOpenChat: () => void;
  onSaveServiceName: (value: string) => Promise<void>;
  onSaveLineItems: (items: LineItem[]) => Promise<void>;
}) {
  return (
    // 내용(왼쪽, 편집)과 뷰어(오른쪽, 실제 양식)를 나란히 둔다 — 이전엔 편집 표 밑에 800px
    // iframe이 이어져서 미리보기를 보려면 한참 스크롤해야 했고, 수정할 때마다 표와 미리보기를
    // 번갈아 스크롤해야 했다. 뷰어는 sticky라 편집 중에도 계속 눈에 보인다.
    <div className="grid grid-cols-1 gap-6 xl:grid-cols-[3fr_2fr] xl:items-start">
      <div className="rounded-2xl border-2 border-indigo-600 bg-white p-6 shadow-md">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span
                className={
                  quote.is_primary
                    ? "rounded-full bg-indigo-600 px-3 py-1 text-sm font-semibold text-white"
                    : "rounded-full bg-gray-200 px-3 py-1 text-sm font-medium text-gray-700"
                }
              >
                {quote.is_primary ? "본견적" : "비교견적"}
              </span>
              {quote.is_catalog_borrowed && (
                <span
                  className="rounded-full bg-amber-100 px-3 py-1 text-sm font-medium text-amber-700"
                  title={`${quote.entity_name}의 실제 카탈로그가 없어 ${quote.catalog_source_entity_name}의 항목 구성을 차용했습니다.`}
                >
                  {quote.catalog_source_entity_name} 차용
                </span>
              )}
            </div>
            <p className="mt-2 text-2xl font-bold text-gray-900">{quote.entity_name}</p>
            {quote.entity_name === TESTIFY_NAME && (
              <ServiceNameField quote={quote} onSave={onSaveServiceName} />
            )}
          </div>
          <div className="text-right">
            <p className="whitespace-nowrap text-3xl font-bold text-indigo-700">
              {quote.total_amount.toLocaleString()}
              <span className="ml-0.5 text-base font-medium text-gray-400">원</span>
            </p>
          </div>
        </div>

        {quote.line_items.length > 0 ? (
          <div className="mt-4">
            <LineItemTable
              items={quote.line_items}
              columnLabels={quote.column_labels}
              detailColumnOrder={quote.detail_column_order}
              totalAmount={quote.total_amount}
              vatIncluded={vatIncluded}
              showCategorySplit={quote.show_category_split}
              onSaveLineItems={onSaveLineItems}
            />
          </div>
        ) : (
          <p className="mt-4 text-sm text-gray-400">아직 항목이 생성되지 않았습니다.</p>
        )}

        {quote.line_items.length > 0 && (
          <div className="mt-5 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={onOpenChat}
              className="rounded-full bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-500"
            >
              채팅으로 수정
            </button>
            <a
              href={getEntityQuotePdfUrl(quote.id)}
              className="rounded-full border border-indigo-300 px-4 py-2 text-sm font-semibold text-indigo-700 hover:border-indigo-400"
            >
              PDF 다운로드
            </a>
            <a
              href={getEntityQuoteXlsxUrl(quote.id)}
              className="rounded-full border border-indigo-300 px-4 py-2 text-sm font-semibold text-indigo-700 hover:border-indigo-400"
            >
              엑셀 다운로드
            </a>
          </div>
        )}
      </div>

      {quote.line_items.length > 0 && (
        <div className="xl:sticky xl:top-6">
          <QuotePreviewPane quote={quote} />
        </div>
      )}
    </div>
  );
}

function QuotePreviewPane({ quote }: { quote: EntityQuote }) {
  const previewKey = hashKey({ items: quote.line_items, total: quote.total_amount, service: quote.service_name });
  const [loadedKey, setLoadedKey] = useState<string | null>(null);
  const loading = loadedKey !== previewKey;

  return (
    <div className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
      <div className="mb-2 flex items-center justify-between">
        <p className="text-xs font-semibold text-gray-400">실제 양식 미리보기</p>
        {loading && <p className="text-xs text-indigo-500">최신 수정 내용 반영 중…</p>}
      </div>
      <div className="relative aspect-[1/1.4142] max-h-[calc(100vh-8rem)] w-full overflow-hidden rounded-lg border border-gray-200">
        {loading && (
          <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-2 bg-gray-50">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-indigo-200 border-t-indigo-600" />
            <p className="text-xs text-gray-400">실제 양식을 불러오는 중…</p>
          </div>
        )}
        <iframe
          key={previewKey}
          src={`${getEntityQuotePdfUrl(quote.id, { inline: true })}#view=FitH`}
          title={`${quote.entity_name} 견적서 미리보기`}
          className="h-full w-full"
          onLoad={() => setLoadedKey(previewKey)}
        />
      </div>
    </div>
  );
}

function EditChatModal({
  quote,
  messages,
  vatIncluded,
  highlightKeys,
  onSend,
  onClose,
  onSaveLineItems,
}: {
  quote: EntityQuote;
  messages: ChatMessage[];
  vatIncluded: boolean;
  highlightKeys?: Set<string>;
  onSend: (text: string) => Promise<void>;
  onClose: () => void;
  onSaveLineItems: (items: LineItem[]) => Promise<void>;
}) {
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, sending]);

  async function handleSend() {
    if (!input.trim() || sending) return;
    setSending(true);
    setErrorMsg(null);
    const text = input;
    setInput("");
    try {
      await onSend(text);
    } catch (e) {
      setErrorMsg(e instanceof ApiError ? e.message : "수정에 실패했습니다.");
    } finally {
      setSending(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
      onClick={onClose}
    >
      <div
        className="flex h-[82vh] w-full max-w-5xl overflow-hidden rounded-2xl bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Left: 채팅 */}
        <div className="flex w-2/5 flex-col border-r border-gray-200">
          <div className="border-b border-gray-100 px-5 py-4">
            <p className="text-sm font-semibold text-gray-900">채팅으로 수정</p>
            <p className="mt-0.5 text-xs text-gray-500">
              {quote.entity_name} · {quote.is_primary ? "본견적" : "비교견적"}
            </p>
          </div>
          <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-5 py-4">
            {messages.length === 0 && (
              <p className="text-sm text-gray-400">
                예: “2번 항목 200만원 낮추고 총액 유지해줘” 처럼 자연어로 요청해보세요.
              </p>
            )}
            {messages.map((m, i) => (
              <div key={i} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
                <div
                  className={
                    "max-w-[85%] rounded-2xl px-3 py-2 text-sm " +
                    (m.role === "user" ? "bg-indigo-600 text-white" : "bg-gray-100 text-gray-800")
                  }
                >
                  <p className="whitespace-pre-line">{m.text}</p>
                  {m.scope && m.scope !== "quote_only" && (
                    <p className="mt-1 text-xs font-medium text-amber-600">
                      ⚠ {SCOPE_LABEL[m.scope] ?? m.scope}
                    </p>
                  )}
                </div>
              </div>
            ))}
            {sending && (
              <div className="flex justify-start">
                <div className="flex items-center gap-1 rounded-2xl bg-gray-100 px-3 py-2.5">
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-gray-400 [animation-delay:-0.3s]" />
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-gray-400 [animation-delay:-0.15s]" />
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-gray-400" />
                </div>
              </div>
            )}
          </div>
          {errorMsg && <p className="px-5 pb-1 text-xs text-red-600">{errorMsg}</p>}
          <div className="flex gap-2 border-t border-gray-100 px-4 py-3">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSend()}
              placeholder="예: 2번 항목 200만원 낮추고 총액 유지해줘"
              className="flex-1 rounded-full border border-gray-300 px-4 py-2 text-sm focus:border-indigo-500 focus:outline-none"
            />
            <button
              type="button"
              disabled={sending || !input.trim()}
              onClick={handleSend}
              className="rounded-full bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-700 disabled:cursor-not-allowed disabled:bg-gray-300"
            >
              {sending ? "…" : "전송"}
            </button>
          </div>
        </div>

        {/* Right: 실시간 견적 미리보기 */}
        <div className="flex w-3/5 flex-col">
          <div className="flex items-center justify-between border-b border-gray-100 px-6 py-4">
            <div>
              <p className="text-base font-semibold text-gray-900">{quote.entity_name}</p>
              <p className="text-xs text-gray-500">{quote.is_primary ? "본견적" : "비교견적"}</p>
            </div>
            <div className="text-right">
              <p className="text-lg font-bold text-gray-900">
                {quote.total_amount.toLocaleString()}원
              </p>
              {quote.is_catalog_borrowed && (
                <p className="text-xs font-medium text-amber-600">
                  {quote.catalog_source_entity_name} 카탈로그 차용
                </p>
              )}
            </div>
          </div>
          <div className="flex-1 overflow-y-auto px-6 py-4">
            <LineItemTable
              items={quote.line_items}
              columnLabels={quote.column_labels}
              detailColumnOrder={quote.detail_column_order}
              totalAmount={quote.total_amount}
              vatIncluded={vatIncluded}
              showCategorySplit={quote.show_category_split}
              highlightKeys={highlightKeys}
              onSaveLineItems={onSaveLineItems}
            />
          </div>
          <button
            type="button"
            onClick={onClose}
            className="border-t border-gray-100 px-6 py-3 text-sm font-medium text-gray-600 hover:bg-gray-50"
          >
            닫기
          </button>
        </div>
      </div>
    </div>
  );
}

type EntitySelection = {
  entityId: string;
  role: "primary" | "comparison";
  // 과업종류(마케팅/시장검증)별 포함 여부 + 체크된 module_name들.
  tasks: Record<FixedTaskType, { included: boolean; moduleNames: string[] }>;
};

function emptyTasks(): EntitySelection["tasks"] {
  return { 마케팅: { included: false, moduleNames: [] }, 시장검증: { included: false, moduleNames: [] } };
}

// 기준 기업이 고른 variant 옵션의 라벨(예: "온라인 광고 / SEO 마케팅 / ...")을 찾는다 — 다른
// 기업에 같은 선택을 옮길 때 module_name이 아니라 라벨로 매칭해야, 법인마다 실제 module_name이
// 달라도(예: 미러링 카탈로그) 같은 개념의 옵션을 찾을 수 있다.
function selectedVariantLabels(taskType: FixedTaskType, moduleNames: string[], options: CatalogModuleOptions | undefined): string[] {
  const labels: string[] = [];
  for (const group of options?.groups ?? []) {
    if (group.kind !== "variant") continue;
    const match = group.options.find((o) => o.module_names.every((m) => moduleNames.includes(m)));
    if (match) labels.push(match.label);
  }
  return labels;
}

// 기준 기업의 variant 라벨을 대상 기업의 카탈로그에서 같은 라벨로 찾아 적용하고, 없으면(카탈로그
// 구성이 달라 매칭이 안 되면) 그 기업 자신의 기본값으로 대체한다.
function moduleNamesMatchingLabels(referenceLabels: string[], options: CatalogModuleOptions | undefined): string[] {
  const names: string[] = [];
  let labelIndex = 0;
  for (const group of options?.groups ?? []) {
    if (group.kind !== "variant") continue;
    const wanted = referenceLabels[labelIndex++];
    const match = wanted ? group.options.find((o) => o.label === wanted) : undefined;
    const chosen = match ?? group.options.find((o) => o.is_default) ?? group.options[0];
    if (chosen) names.push(...chosen.module_names);
  }
  return names;
}

export default function EstimateWizard({ initialEstimateSetId }: { initialEstimateSetId?: string } = {}) {
  const [entities, setEntities] = useState<EntityOption[]>([]);
  const [entitiesLoading, setEntitiesLoading] = useState(true);
  // 과업종류별로 취급하지 않는 법인(예: 썬데이워커/ABBG × 시장검증)을 숨기기 위한 정보.
  const [excludedByTask, setExcludedByTask] = useState<Record<FixedTaskType, Set<string>>>({
    마케팅: new Set(),
    시장검증: new Set(),
  });

  const [entitySelections, setEntitySelections] = useState<EntitySelection[]>([]);
  // (entityId, taskType) -> 카탈로그 모듈 옵션 캐시. 선택된 기업마다 두 과업종류 옵션을 미리 받아둔다.
  const [moduleOptionsCache, setModuleOptionsCache] = useState<Record<string, CatalogModuleOptions>>({});

  const [projectName, setProjectName] = useState("");
  const [recipientName, setRecipientName] = useState("");
  const [recipientContact, setRecipientContact] = useState("");
  const [recipientPhone, setRecipientPhone] = useState("");
  const [recipientEmail, setRecipientEmail] = useState("");
  const [totalAmount, setTotalAmount] = useState("");
  const [vatIncluded, setVatIncluded] = useState(true);
  const [serviceName, setServiceName] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<EstimateSet | null>(null);
  const [generating, setGenerating] = useState(false);

  const [activeQuoteId, setActiveQuoteId] = useState<string | null>(null);
  const [viewedQuoteId, setViewedQuoteId] = useState<string | null>(null);
  const [chatHistory, setChatHistory] = useState<Record<string, ChatMessage[]>>({});
  // 채팅 수정 직후 오른쪽 미리보기에서 어느 항목이 바뀌었는지 표시하기 위한 키 집합
  // ("카테고리::항목명"). 사용자가 "수정되는지도 몰라요"라고 지적한 부분(2026-08-10) 대응.
  const [lastChangedKeys, setLastChangedKeys] = useState<Record<string, Set<string>>>({});

  const [moduleOptions, setModuleOptions] = useState<EntityModuleOptions[]>([]);
  const [moduleSelections, setModuleSelections] = useState<Record<string, string[]>>({});

  // 견적서 목록에서 기존 세트를 클릭해 들어온 경우, 새로 만드는 대신 그 결과 화면을 바로 불러온다.
  const [initialLoading, setInitialLoading] = useState(!!initialEstimateSetId);
  useEffect(() => {
    if (!initialEstimateSetId) return;
    fetchEstimateSet(initialEstimateSetId)
      .then(setResult)
      .catch((e) => setError(e instanceof ApiError ? e.message : "견적서를 불러오지 못했습니다."))
      .finally(() => setInitialLoading(false));
  }, [initialEstimateSetId]);

  const primaryEntityId = entitySelections.find((s) => s.role === "primary")?.entityId ?? "";
  const primaryIsTestify = entities.find((e) => e.id === primaryEntityId)?.name === TESTIFY_NAME;
  // 과업 선택은 이 "기준 기업" 하나만 고르면 나머지 기업에 자동으로 같은 과업이 적용된다
  // (2026-08-09 사용자 요청 — 기업마다 따로 고르지 않는다). 본견적이 있으면 본견적이 기준,
  // 없으면(비교견적끼리만 선택된 경우) 가장 먼저 선택한 기업이 기준이 된다.
  const referenceEntityId = primaryEntityId || entitySelections[0]?.entityId || "";
  const resultId = result?.id;
  const resultHasItems = result?.entity_quotes.some((q) => q.line_items.length > 0) ?? false;

  // 법인 목록은 과업종류 필터링 없이 한 번만 불러온다(2026-08 개편 — 기업을 먼저 고르므로).
  // 기존 /api/entities?task_type= 엔드포인트를 그대로 재사용해 두 과업종류 각각 호출한 뒤
  // 합집합을 전체 후보로, 빠진 쪽을 과업종류별 제외 목록으로 삼는다.
  useEffect(() => {
    Promise.all(FIXED_TASK_TYPES.map((t) => fetchEntities(t)))
      .then(([marketingEntities, marketVerificationEntities]) => {
        const byId = new Map<string, EntityOption>();
        for (const e of [...marketingEntities, ...marketVerificationEntities]) byId.set(e.id, e);
        const all = Array.from(byId.values()).sort((a, b) => a.name.localeCompare(b.name));
        setEntities(all);
        setExcludedByTask({
          마케팅: new Set(all.map((e) => e.id).filter((id) => !marketingEntities.some((e) => e.id === id))),
          시장검증: new Set(all.map((e) => e.id).filter((id) => !marketVerificationEntities.some((e) => e.id === id))),
        });
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "법인 목록을 불러오지 못했습니다."))
      .finally(() => setEntitiesLoading(false));
  }, []);

  // 선택된 기업이 새로 생기면, 그 기업의 마케팅/시장검증 모듈 옵션을 미리 받아 캐시해둔다.
  useEffect(() => {
    const missing = entitySelections
      .map((s) => s.entityId)
      .filter((id) => FIXED_TASK_TYPES.some((t) => !(`${id}:${t}` in moduleOptionsCache)));
    if (missing.length === 0) return;
    Promise.all(
      missing.flatMap((entityId) =>
        FIXED_TASK_TYPES.map((taskType) =>
          fetchCatalogModuleOptions(entityId, taskType).then((options) => [`${entityId}:${taskType}`, options] as const)
        )
      )
    )
      .then((entries) => {
        setModuleOptionsCache((prev) => {
          const next = { ...prev };
          for (const [key, options] of entries) next[key] = options;
          return next;
        });
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "모듈 옵션을 불러오지 못했습니다."));
  }, [entitySelections, moduleOptionsCache]);

  // 기준 기업(본견적, 없으면 첫 선택 기업)의 과업 선택을 나머지 기업에 그대로 적용한 결과를
  // "계산"한다 — state에 동기화해 저장하지 않고 필요할 때(제출 시점 등)마다 유도한다. 그 기업이
  // 취급하지 않는 과업종류(excludedByTask)는 강제로 제외하고, variant 옵션은 라벨이 일치하는
  // 것을 찾아 적용하되 없으면 그 기업 자신의 기본값을 쓴다.
  function effectiveTasks(s: EntitySelection): EntitySelection["tasks"] {
    if (s.entityId === referenceEntityId) return s.tasks;
    const reference = entitySelections.find((r) => r.entityId === referenceEntityId);
    if (!reference) return s.tasks;
    const nextTasks = emptyTasks();
    for (const taskType of FIXED_TASK_TYPES) {
      const refTask = reference.tasks[taskType];
      if (!refTask.included || excludedByTask[taskType].has(s.entityId)) continue;
      const refOptions = moduleOptionsCache[`${referenceEntityId}:${taskType}`];
      const targetOptions = moduleOptionsCache[`${s.entityId}:${taskType}`];
      const referenceLabels = selectedVariantLabels(taskType, refTask.moduleNames, refOptions);
      const moduleNames = moduleNamesMatchingLabels(referenceLabels, targetOptions);
      nextTasks[taskType] = { included: true, moduleNames };
    }
    return nextTasks;
  }

  useEffect(() => {
    if (!ENABLE_MODULE_SELECTION_UI) return;
    if (!resultId || resultHasItems) return;
    fetchModuleOptions(resultId)
      .then((options) => {
        setModuleOptions(options);
        const defaults: Record<string, string[]> = {};
        for (const opt of options) {
          const picked: string[] = [];
          for (const group of opt.groups) {
            if (group.kind === "variant") {
              const def = group.options.find((o) => o.is_default);
              if (def) picked.push(...def.module_names);
            }
          }
          defaults[opt.entity_quote_id] = picked;
        }
        setModuleSelections(defaults);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "모듈 옵션을 불러오지 못했습니다."));
  }, [resultId, resultHasItems]);

  function setVariantSelection(
    quoteId: string,
    group: EntityModuleOptions["groups"][number],
    option: ModuleOption
  ) {
    setModuleSelections((prev) => {
      const current = prev[quoteId] ?? [];
      const groupModuleNames = new Set(group.options.flatMap((o) => o.module_names));
      const withoutGroup = current.filter((m) => !groupModuleNames.has(m));
      return { ...prev, [quoteId]: [...withoutGroup, ...option.module_names] };
    });
  }

  function toggleAdditiveSelection(quoteId: string, option: ModuleOption, checked: boolean) {
    setModuleSelections((prev) => {
      const current = prev[quoteId] ?? [];
      const moduleNames = new Set(option.module_names);
      const next = checked
        ? [...current, ...option.module_names]
        : current.filter((m) => !moduleNames.has(m));
      return { ...prev, [quoteId]: next };
    });
  }

  function toggleEntity(entityId: string) {
    setEntitySelections((prev) => {
      if (prev.some((s) => s.entityId === entityId)) return prev.filter((s) => s.entityId !== entityId);
      return [...prev, { entityId, role: "comparison" as const, tasks: emptyTasks() }];
    });
  }

  function setRole(entityId: string, role: "primary" | "comparison") {
    setEntitySelections((prev) => {
      if (role === "comparison") {
        const comparisonCount = prev.filter((s) => s.role === "comparison" && s.entityId !== entityId).length;
        if (comparisonCount >= MAX_COMPARISON) return prev;
      }
      return prev.map((s) => {
        if (s.entityId === entityId) return { ...s, role };
        if (role === "primary" && s.role === "primary") return { ...s, role: "comparison" as const };
        return s;
      });
    });
  }

  function toggleTaskIncluded(entityId: string, taskType: FixedTaskType, included: boolean) {
    // 과업을 포함시켜도 세부 항목은 자동 선택하지 않는다 — 사용자가 직접 하나를 골라야
    // 그 과업이 "선택됨"으로 간주된다(taskSatisfied 참고).
    setEntitySelections((prev) =>
      prev.map((s) => {
        if (s.entityId !== entityId) return s;
        return { ...s, tasks: { ...s.tasks, [taskType]: { included, moduleNames: s.tasks[taskType].moduleNames } } };
      })
    );
  }

  function setVariantModule(entityId: string, taskType: FixedTaskType, group: ModuleGroup, option: ModuleOption) {
    setEntitySelections((prev) =>
      prev.map((s) => {
        if (s.entityId !== entityId) return s;
        const current = s.tasks[taskType].moduleNames;
        const groupNames = new Set(group.options.flatMap((o) => o.module_names));
        const without = current.filter((m) => !groupNames.has(m));
        return {
          ...s,
          tasks: { ...s.tasks, [taskType]: { included: true, moduleNames: [...without, ...option.module_names] } },
        };
      })
    );
  }

  function toggleAdditiveModule(entityId: string, taskType: FixedTaskType, option: ModuleOption, checked: boolean) {
    setEntitySelections((prev) =>
      prev.map((s) => {
        if (s.entityId !== entityId) return s;
        const current = s.tasks[taskType].moduleNames;
        const names = new Set(option.module_names);
        const next = checked ? [...current, ...option.module_names] : current.filter((m) => !names.has(m));
        return { ...s, tasks: { ...s.tasks, [taskType]: { included: s.tasks[taskType].included, moduleNames: next } } };
      })
    );
  }

  // "포함" 토글만으로는 부족하다 — 모듈이 있는 과업은 세부 항목을 하나 이상 골라야
  // 그 과업이 실제로 선택된 것으로 친다(포함만 켜고 아무 항목도 안 고른 상태 방지).
  function taskSatisfied(entityId: string, taskType: FixedTaskType, task: { included: boolean; moduleNames: string[] }) {
    if (!task.included) return false;
    const hasModules = moduleOptionsCache[`${entityId}:${taskType}`]?.has_modules ?? false;
    return !hasModules || task.moduleNames.length > 0;
  }

  const allEntitiesHaveTask = entitySelections.every((s) =>
    FIXED_TASK_TYPES.some((t) => taskSatisfied(s.entityId, t, effectiveTasks(s)[t]))
  );

  const canSubmit =
    entitySelections.length > 0 &&
    entitySelections.filter((s) => s.role === "comparison").length <= MAX_COMPARISON &&
    allEntitiesHaveTask &&
    projectName.trim().length > 0 &&
    recipientName.trim().length > 0 &&
    Number(totalAmount) > 0 &&
    (!primaryIsTestify || serviceName.trim().length > 0) &&
    !submitting;

  async function handleSubmit() {
    setSubmitting(true);
    setError(null);
    try {
      const created = await createEstimateSet({
        project_name: projectName,
        recipient_name: recipientName,
        recipient_contact: recipientContact || undefined,
        recipient_phone: recipientPhone || undefined,
        recipient_email: recipientEmail || undefined,
        total_amount: Number(totalAmount),
        vat_included: vatIncluded,
        entities: entitySelections.map((s) => ({
          entity_id: s.entityId,
          is_primary: s.role === "primary",
          task_types: FIXED_TASK_TYPES.filter((t) => effectiveTasks(s)[t].included),
        })),
        service_name: primaryIsTestify ? serviceName : undefined,
      });
      setResult(created);

      // 생성된 entity_quote(기업별 row, 교차 선택한 과업종류를 모두 포함)마다, 그 기업이 각
      // 과업종류에서 고른 모듈을 모두 모아 매칭한다(모듈명이 과업종류 간에 겹치지 않아 합쳐도 안전).
      const bySelection = new Map(entitySelections.map((s) => [s.entityId, effectiveTasks(s)]));
      const selections: Record<string, string[]> = {};
      for (const quote of created.entity_quotes) {
        const tasks = bySelection.get(quote.entity_id);
        selections[quote.id] = quote.task_types.flatMap(
          (t) => tasks?.[t as FixedTaskType]?.moduleNames ?? []
        );
      }
      setModuleSelections(selections);
      const generated = await generateEstimateSet(created.id, selections);
      setResult(generated);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "견적 세트 생성에 실패했습니다.");
    } finally {
      setSubmitting(false);
    }
  }

  function handleReset() {
    setResult(null);
    setEntitySelections([]);
    setProjectName("");
    setRecipientName("");
    setTotalAmount("");
    setVatIncluded(true);
    setServiceName("");
    setError(null);
    setActiveQuoteId(null);
    setViewedQuoteId(null);
    setChatHistory({});
    setModuleOptions([]);
    setModuleSelections({});
  }

  async function handleGenerate() {
    if (!result) return;
    setGenerating(true);
    setError(null);
    try {
      const updated = await generateEstimateSet(result.id, moduleSelections);
      setResult(updated);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "항목・금액 자동 생성에 실패했습니다.");
    } finally {
      setGenerating(false);
    }
  }

  function handleQuoteEdited(updated: EntityQuote) {
    setResult((prev) =>
      prev
        ? {
            ...prev,
            entity_quotes: prev.entity_quotes.map((q) => (q.id === updated.id ? updated : q)),
          }
        : prev
    );
  }

  async function handleSaveServiceName(quoteId: string, value: string) {
    const updated = await updateServiceName(quoteId, value);
    handleQuoteEdited(updated);
  }

  async function handleSaveLineItems(quoteId: string, items: LineItem[]) {
    const updated = await updateLineItems(quoteId, items);
    handleQuoteEdited(updated);
  }

  async function handleSendEdit(quoteId: string, text: string) {
    setChatHistory((prev) => ({
      ...prev,
      [quoteId]: [...(prev[quoteId] ?? []), { role: "user", text }],
    }));

    const editResult = await editEntityQuote(quoteId, text);
    handleQuoteEdited(editResult.entity_quote);

    const summary =
      editResult.changed_items.length > 0
        ? editResult.changed_items.map((i) => `• ${i.name} → ${i.amount.toLocaleString()}원`).join("\n")
        : "요청하신 내용을 반영했습니다.";

    setChatHistory((prev) => ({
      ...prev,
      [quoteId]: [...(prev[quoteId] ?? []), { role: "assistant", text: summary, scope: editResult.scope }],
    }));
    setLastChangedKeys((prev) => ({
      ...prev,
      [quoteId]: new Set(editResult.changed_items.map((i) => `${i.category}::${i.name}`)),
    }));
  }

  if (initialLoading) {
    return <p className="p-8 text-center text-base text-gray-400">불러오는 중…</p>;
  }

  if (result) {
    const hasItems = result.entity_quotes.some((q) => q.line_items.length > 0);
    const primaryQuote = result.entity_quotes.find((q) => q.is_primary) ?? null;
    const comparisonQuotes = result.entity_quotes.filter((q) => !q.is_primary);
    const activeQuote = result.entity_quotes.find((q) => q.id === activeQuoteId) ?? null;
    const viewedQuote =
      result.entity_quotes.find((q) => q.id === viewedQuoteId) ?? primaryQuote ?? comparisonQuotes[0] ?? null;
    const modulesToChoose = moduleOptions.filter((o) => o.has_modules);
    const isAutoGenerating = !ENABLE_MODULE_SELECTION_UI && submitting;

    return (
      <div className="space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
          <div>
            <p className="text-sm font-medium text-emerald-600">견적 세트 생성 완료</p>
            <h2 className="mt-1 text-2xl font-bold text-gray-900">{result.project_name}</h2>
          </div>
          <div className="flex flex-wrap gap-8">
            <div>
              <p className="text-xs text-gray-500">과업종류</p>
              <p className="mt-1 text-base font-semibold text-gray-900">{result.task_type}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500">총액</p>
              <p className="mt-1 text-base font-semibold text-gray-900">
                {result.total_amount.toLocaleString()}원
                <span className="ml-1 text-xs font-normal text-gray-400">
                  ({result.vat_included ? "VAT 포함" : "VAT 별도"})
                </span>
              </p>
            </div>
          </div>
          <button
            onClick={handleReset}
            title="지금 만든 견적은 그대로 두고, 처음 화면으로 돌아가 다른 견적을 새로 만듭니다."
            className="rounded-full border border-gray-300 px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50"
          >
            + 다른 견적 새로 만들기
          </button>
        </div>

        {error && (
          <div className="rounded-md bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
        )}

        {!hasItems ? (
          <div className="flex flex-col items-center gap-3 rounded-2xl border-2 border-indigo-100 bg-white p-12 text-center shadow-sm">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-indigo-100 text-indigo-600">
              {isAutoGenerating ? (
                <div className="h-6 w-6 animate-spin rounded-full border-2 border-indigo-200 border-t-indigo-600" />
              ) : (
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 24 24"
                  fill="currentColor"
                  className="h-6 w-6"
                >
                  <path d="M9.5 2.5a1 1 0 0 1 1.9 0l.9 2.7a4 4 0 0 0 2.5 2.5l2.7.9a1 1 0 0 1 0 1.9l-2.7.9a4 4 0 0 0-2.5 2.5l-.9 2.7a1 1 0 0 1-1.9 0l-.9-2.7a4 4 0 0 0-2.5-2.5l-2.7-.9a1 1 0 0 1 0-1.9l2.7-.9a4 4 0 0 0 2.5-2.5l.9-2.7Z" />
                  <path d="M18.5 13.8a.8.8 0 0 1 1.5 0l.3.9a2 2 0 0 0 1.2 1.2l.9.3a.8.8 0 0 1 0 1.5l-.9.3a2 2 0 0 0-1.2 1.2l-.3.9a.8.8 0 0 1-1.5 0l-.3-.9a2 2 0 0 0-1.2-1.2l-.9-.3a.8.8 0 0 1 0-1.5l.9-.3a2 2 0 0 0 1.2-1.2l.3-.9Z" />
                </svg>
              )}
            </div>
            <p className="text-base font-semibold text-gray-900">
              {isAutoGenerating
                ? "항목・금액을 생성하고 있습니다…"
                : ENABLE_MODULE_SELECTION_UI
                ? "다음 단계: 항목・금액 자동 생성"
                : "항목・금액 자동 생성에 실패했습니다"}
            </p>
            <p className="max-w-md text-sm text-gray-500">
              {isAutoGenerating
                ? "잠시만 기다려주세요."
                : ENABLE_MODULE_SELECTION_UI
                ? "아래 버튼을 누르면 입력하신 총액을 기준으로 법인별 항목과 금액이 자동으로 생성・배분됩니다."
                : "아래 버튼을 다시 누르면 자동으로 생성・배분을 재시도합니다."}
            </p>

            {ENABLE_MODULE_SELECTION_UI && modulesToChoose.length > 0 && (
              <div className="mt-2 w-full max-w-xl space-y-5 rounded-xl border border-gray-200 bg-gray-50/60 p-5 text-left">
                <div>
                  <p className="text-sm font-semibold text-gray-700">항목 구성 선택</p>
                  <p className="mt-0.5 text-xs text-gray-500">
                    이 견적서에 어떤 항목들을 담을지 고르세요. &quot;N개 항목 보기&quot;를 누르면 실제로
                    포함되는 항목명을 확인할 수 있습니다.
                  </p>
                </div>
                {modulesToChoose.map((opt) => {
                  const isPrimaryQuote = opt.entity_quote_id === primaryQuote?.id;
                  return (
                  <div
                    key={opt.entity_quote_id}
                    className="space-y-3 rounded-lg border border-gray-200 bg-white p-3"
                  >
                    <div className="flex items-center gap-2">
                      <span
                        className={
                          isPrimaryQuote
                            ? "rounded-full bg-indigo-600 px-2 py-0.5 text-[11px] font-semibold text-white"
                            : "rounded-full bg-gray-200 px-2 py-0.5 text-[11px] font-medium text-gray-700"
                        }
                      >
                        {isPrimaryQuote ? "본견적" : "비교견적"}
                      </span>
                      <p className="text-sm font-semibold text-gray-900">{opt.entity_name}</p>
                    </div>
                    {opt.groups.map((group, gi) => (
                      <div key={gi} className="space-y-2 pl-1">
                        {group.kind === "additive" && (
                          <p className="text-[11px] text-gray-400">
                            필요하면 아래 항목 구성을 추가로 포함하세요.
                          </p>
                        )}
                        {group.options.map((o) => {
                          const selected = moduleSelections[opt.entity_quote_id] ?? [];
                          const isChecked = o.module_names.every((m) => selected.includes(m));
                          return (
                            <ModuleOptionRow
                              key={o.option_key}
                              option={o}
                              label={group.kind === "additive" ? `+ ${o.label} 추가` : o.label}
                              inputType={group.kind === "variant" ? "radio" : "checkbox"}
                              name={group.kind === "variant" ? `variant-${opt.entity_quote_id}-${gi}` : undefined}
                              checked={isChecked}
                              onChange={() =>
                                group.kind === "variant"
                                  ? setVariantSelection(opt.entity_quote_id, group, o)
                                  : toggleAdditiveSelection(opt.entity_quote_id, o, !isChecked)
                              }
                            />
                          );
                        })}
                      </div>
                    ))}
                  </div>
                  );
                })}
              </div>
            )}

            {!isAutoGenerating && (
            <button
              type="button"
              disabled={generating}
              onClick={handleGenerate}
              className="mt-1 rounded-full bg-indigo-600 px-6 py-3 text-sm font-semibold text-white hover:bg-indigo-500 disabled:cursor-not-allowed disabled:bg-gray-300"
            >
              {generating ? "생성 중…" : "항목・금액 자동 생성 및 배분"}
            </button>
            )}
          </div>
        ) : (
          <div className="space-y-5">
            {result.entity_quotes.length > 1 && (
              <ComparisonSummaryTable quotes={result.entity_quotes} primaryTotal={primaryQuote?.total_amount} />
            )}

            {result.entity_quotes.length > 1 && (
              <div className="flex flex-wrap gap-2">
                {result.entity_quotes.map((q) => {
                  const selected = (viewedQuote?.id ?? primaryQuote?.id) === q.id;
                  return (
                    <button
                      key={q.id}
                      type="button"
                      onClick={() => setViewedQuoteId(q.id)}
                      className={
                        "rounded-full border px-4 py-2 text-sm font-medium " +
                        (selected
                          ? "border-indigo-600 bg-indigo-600 text-white"
                          : "border-gray-300 text-gray-700 hover:border-gray-400")
                      }
                    >
                      {q.entity_name}
                      <span className="ml-1.5 text-xs opacity-70">{q.is_primary ? "본견적" : "비교견적"}</span>
                      {q.total_amount > 0 && (
                        <span className="ml-1.5 text-xs opacity-70">· {q.total_amount.toLocaleString()}원</span>
                      )}
                    </button>
                  );
                })}
              </div>
            )}

            {viewedQuote && (
              <QuoteCard
                quote={viewedQuote}
                vatIncluded={result.vat_included}
                onOpenChat={() => setActiveQuoteId(viewedQuote.id)}
                onSaveServiceName={(value) => handleSaveServiceName(viewedQuote.id, value)}
                onSaveLineItems={(items) => handleSaveLineItems(viewedQuote.id, items)}
              />
            )}
          </div>
        )}

        {activeQuote && (
          <EditChatModal
            quote={activeQuote}
            messages={chatHistory[activeQuote.id] ?? []}
            vatIncluded={result.vat_included}
            highlightKeys={lastChangedKeys[activeQuote.id]}
            onSend={(text) => handleSendEdit(activeQuote.id, text)}
            onClose={() => setActiveQuoteId(null)}
            onSaveLineItems={(items) => handleSaveLineItems(activeQuote.id, items)}
          />
        )}
      </div>
    );
  }

  const referenceSelection = entitySelections.find((s) => s.entityId === referenceEntityId);
  const otherSelections = entitySelections.filter((s) => s.entityId !== referenceEntityId);
  // 기준 기업이 실제로 켠 과업종류가 있고, 그 전부를 어떤 기업이 취급하지 않을 때만 경고한다 —
  // 아직 아무 과업도 안 켰을 때 every()가 공허하게 참이 되어 전부 "제외"로 오판하던 버그가
  // 있었다(2026-08-09, 스크린샷으로 재현 확인).
  const referenceIncludedTaskTypes = referenceSelection
    ? FIXED_TASK_TYPES.filter((t) => referenceSelection.tasks[t].included)
    : [];
  const strandedSelections =
    otherSelections.length > 0 && referenceIncludedTaskTypes.length > 0
      ? otherSelections.filter((s) => referenceIncludedTaskTypes.every((t) => excludedByTask[t].has(s.entityId)))
      : [];
  const entityLabel = (id: string) => entities.find((e) => e.id === id)?.name ?? id;

  return (
    <div className="space-y-10 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
      <div>
        <h2 className="text-2xl font-bold text-gray-900">견적서 생성</h2>
        <p className="mt-2 text-base text-gray-500">
          기업을 선택하고 본견적/비교견적 역할을 정하면, 과업은 한 번만 골라도 모든 기업에 동일하게 적용됩니다.
        </p>
      </div>

      {error && (
        <div className="rounded-md bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      )}

      {/* Step 1: 기업 선택 */}
      <fieldset>
        <StepHeader n={1} title="기업 선택" hint="다중 선택, 최소 1곳" />
        {entitiesLoading ? (
          <p className="mt-3 text-base text-gray-400">불러오는 중…</p>
        ) : (
          <div className="mt-3 flex flex-wrap gap-2">
            {entities.map((e) => {
              const selected = entitySelections.some((s) => s.entityId === e.id);
              return (
                <button
                  key={e.id}
                  type="button"
                  onClick={() => toggleEntity(e.id)}
                  className={
                    "inline-flex items-center gap-1.5 rounded-full border px-4 py-2 text-base font-medium transition-colors " +
                    (selected
                      ? "border-indigo-600 bg-indigo-600 text-white"
                      : "border-gray-300 text-gray-700 hover:border-gray-400 hover:bg-gray-50")
                  }
                >
                  {selected && (
                    <svg viewBox="0 0 12 12" fill="none" className="h-3 w-3">
                      <path d="M2 6l2.5 2.5L10 3" stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  )}
                  {e.name}
                </button>
              );
            })}
          </div>
        )}
      </fieldset>

      {/* Step 2: 본견적/비교견적 지정 */}
      {entitySelections.length > 0 && (
        <fieldset>
          <StepHeader n={2} title="본견적/비교견적 지정" hint={`본견적 최대 1곳, 비교견적 최대 ${MAX_COMPARISON}곳`} />
          <div className="mt-3 divide-y divide-gray-100 overflow-hidden rounded-xl border border-gray-200">
            {entitySelections.map((s) => (
              <div key={s.entityId} className="flex flex-wrap items-center justify-between gap-3 bg-white px-4 py-3">
                <span className="text-base font-semibold text-gray-900">{entityLabel(s.entityId)}</span>
                <div className="inline-flex rounded-full border border-gray-200 bg-gray-50 p-0.5">
                  {(["primary", "comparison"] as const).map((role) => (
                    <button
                      key={role}
                      type="button"
                      onClick={() => setRole(s.entityId, role)}
                      className={
                        "rounded-full px-3.5 py-1.5 text-sm font-medium transition-colors " +
                        (s.role === role ? "bg-indigo-600 text-white shadow-sm" : "text-gray-600 hover:text-gray-900")
                      }
                    >
                      {role === "primary" ? "본견적" : "비교견적 +10%"}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </fieldset>
      )}

      {/* Step 3: 과업 선택 — 기준 기업(본견적, 없으면 첫 선택 기업) 하나만 고르면 나머지 기업에
          자동으로 동일하게 적용된다(2026-08-09 사용자 요청 — 기업마다 따로 고르지 않는다). */}
      {entitySelections.length > 0 && referenceSelection && (
        <fieldset>
          <StepHeader
            n={3}
            title="과업 선택"
            hint="마케팅·시장검증 중 최소 한 곳에서 세부 항목을 하나 이상 골라야 합니다 (둘 다 고를 필요는 없습니다)"
          />
          <div className="mt-3 space-y-3">
            <div className="rounded-xl border border-gray-200 p-4">
              <p className="text-sm font-semibold text-gray-900">
                {entityLabel(referenceEntityId)}
                <span className="ml-1.5 font-normal text-gray-400">
                  ({referenceSelection.role === "primary" ? "본견적" : "비교견적"} 기준)
                </span>
              </p>
              <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
                {FIXED_TASK_TYPES.filter((t) => !excludedByTask[t].has(referenceEntityId)).map((taskType) => (
                  <TaskModulePicker
                    key={taskType}
                    entityId={referenceEntityId}
                    taskType={taskType}
                    included={referenceSelection.tasks[taskType].included}
                    moduleNames={referenceSelection.tasks[taskType].moduleNames}
                    options={moduleOptionsCache[`${referenceEntityId}:${taskType}`]}
                    onToggleIncluded={(included) => toggleTaskIncluded(referenceEntityId, taskType, included)}
                    onSetVariant={(group, option) => setVariantModule(referenceEntityId, taskType, group, option)}
                    onToggleAdditive={(option, checked) =>
                      toggleAdditiveModule(referenceEntityId, taskType, option, checked)
                    }
                  />
                ))}
              </div>
            </div>
            {otherSelections.length > 0 && (
              <p className="px-1 text-sm text-gray-400">
                {otherSelections.map((s) => entityLabel(s.entityId)).join(", ")}에도 동일하게 적용됩니다.
              </p>
            )}
            {strandedSelections.length > 0 && (
              <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-700">
                {strandedSelections.map((s) => entityLabel(s.entityId)).join(", ")}은(는) 선택한 과업을 취급하지 않아
                제외됩니다 — 발급하려면 기업 선택을 다시 확인해주세요.
              </p>
            )}
          </div>
        </fieldset>
      )}

      {/* Step 4: 사업명 + 총액 */}
      {entitySelections.length > 0 && (
        <fieldset className="space-y-4">
          <StepHeader n={4} title="사업 정보" />
          <div>
            <label className="block text-sm text-gray-500">사업명</label>
            <input
              type="text"
              value={projectName}
              onChange={(e) => setProjectName(e.target.value)}
              placeholder="예: 미구 시장검증"
              className="mt-1.5 w-full rounded-md border border-gray-300 px-4 py-3 text-base focus:border-indigo-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-500">
              수신자(고객사명) <span className="text-amber-600">(견적서에 &quot;OOO 귀하&quot;로 표시됩니다)</span>
            </label>
            <input
              type="text"
              value={recipientName}
              onChange={(e) => setRecipientName(e.target.value)}
              placeholder="예: ㈜미구"
              className="mt-1.5 w-full rounded-md border border-gray-300 px-4 py-3 text-base focus:border-indigo-500 focus:outline-none"
            />
          </div>
          {entitySelections.some((s) =>
            ["ABBG", "알파브라더스"].includes(entities.find((e) => e.id === s.entityId)?.name ?? "")
          ) && (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <div>
                <label className="block text-sm text-gray-500">
                  담당자 <span className="text-gray-400">(ABBG·알파브라더스 양식 전용)</span>
                </label>
                <input
                  type="text"
                  value={recipientContact}
                  onChange={(e) => setRecipientContact(e.target.value)}
                  placeholder="예: 김담당"
                  className="mt-1.5 w-full rounded-md border border-gray-300 px-4 py-3 text-base focus:border-indigo-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-500">
                  연락처 <span className="text-gray-400">(ABBG·알파브라더스 양식 전용)</span>
                </label>
                <input
                  type="text"
                  value={recipientPhone}
                  onChange={(e) => setRecipientPhone(e.target.value)}
                  placeholder="예: 010-1234-5678"
                  className="mt-1.5 w-full rounded-md border border-gray-300 px-4 py-3 text-base focus:border-indigo-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-500">
                  이메일 <span className="text-gray-400">(ABBG·알파브라더스 양식 전용)</span>
                </label>
                <input
                  type="text"
                  value={recipientEmail}
                  onChange={(e) => setRecipientEmail(e.target.value)}
                  placeholder="예: example@company.com"
                  className="mt-1.5 w-full rounded-md border border-gray-300 px-4 py-3 text-base focus:border-indigo-500 focus:outline-none"
                />
              </div>
            </div>
          )}
          <div className="flex items-end gap-4">
            <div className="flex-1">
              <label className="block text-sm text-gray-500">총액 (원)</label>
              <input
                type="text"
                inputMode="numeric"
                value={totalAmount ? Number(totalAmount).toLocaleString("ko-KR") : ""}
                onChange={(e) => setTotalAmount(e.target.value.replace(/[^0-9]/g, ""))}
                placeholder="200,000,000"
                className="mt-1.5 w-full rounded-md border border-gray-300 px-4 py-3 text-base focus:border-indigo-500 focus:outline-none"
              />
            </div>
            <label className="flex items-center gap-2 pb-3 text-base text-gray-700">
              <input
                type="checkbox"
                checked={vatIncluded}
                onChange={(e) => setVatIncluded(e.target.checked)}
                className="h-4 w-4 rounded border-gray-300"
              />
              VAT 포함
            </label>
          </div>
          {primaryIsTestify && (
            <div>
              <label className="block text-sm text-gray-500">
                용역명 <span className="text-amber-600">(테스티파이 발급 시 필수)</span>
              </label>
              <input
                type="text"
                value={serviceName}
                onChange={(e) => setServiceName(e.target.value)}
                placeholder="예: 정량, 정성 데이터 기반 시장 검증 용역"
                className="mt-1.5 w-full rounded-md border border-gray-300 px-4 py-3 text-base focus:border-indigo-500 focus:outline-none"
              />
            </div>
          )}
        </fieldset>
      )}

      <button
        type="button"
        disabled={!canSubmit}
        onClick={handleSubmit}
        className="w-full rounded-full bg-indigo-600 px-4 py-3 text-base font-semibold text-white hover:bg-indigo-500 disabled:cursor-not-allowed disabled:bg-gray-300"
      >
        {submitting ? "생성 중…" : "견적 세트 생성"}
      </button>
    </div>
  );
}
