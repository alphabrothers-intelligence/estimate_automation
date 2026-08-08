"use client";

import { useEffect, useRef, useState } from "react";
import {
  ApiError,
  createEstimateSet,
  editEntityQuote,
  fetchCatalogModuleOptions,
  fetchEntities,
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
// 선택한다. 두 과업종류만 이 마법사에서 다룬다 — "광고대행"/"고객검증"은 이번 개편 범위 밖.
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

function ServiceNameField({
  quote,
  onSave,
}: {
  quote: EntityQuote;
  onSave: (value: string) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(quote.service_name ?? "");
  const [saving, setSaving] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  async function handleSave() {
    if (!value.trim() || saving) return;
    setSaving(true);
    setErrorMsg(null);
    try {
      await onSave(value.trim());
      setEditing(false);
    } catch (e) {
      setErrorMsg(e instanceof ApiError ? e.message : "저장에 실패했습니다.");
    } finally {
      setSaving(false);
    }
  }

  if (editing) {
    return (
      <div className="mt-2 flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
        <input
          type="text"
          autoFocus
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSave()}
          placeholder="예: 정량, 정성 데이터 기반 시장 검증 용역"
          className="flex-1 rounded-md border border-gray-300 px-2 py-1 text-sm focus:border-indigo-500 focus:outline-none"
        />
        <button
          type="button"
          disabled={saving || !value.trim()}
          onClick={handleSave}
          className="shrink-0 rounded-md bg-gray-900 px-2 py-1 text-sm font-medium text-white hover:bg-gray-700 disabled:cursor-not-allowed disabled:bg-gray-300"
        >
          {saving ? "…" : "저장"}
        </button>
        {errorMsg && <p className="text-sm text-red-600">{errorMsg}</p>}
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        setEditing(true);
      }}
      className="mt-2 block text-left text-sm"
    >
      {quote.service_name ? (
        <span className="text-gray-500">
          용역명: <span className="text-gray-700">{quote.service_name}</span>
        </span>
      ) : (
        <span className="rounded-full bg-amber-100 px-2 py-0.5 font-medium text-amber-700">
          용역명 입력 필요 (발급 전 작성)
        </span>
      )}
    </button>
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
    <div>
      <div className="flex items-center gap-2 text-sm text-gray-700">
        <input
          type={inputType}
          name={name}
          checked={checked}
          onChange={onChange}
          className={
            inputType === "radio"
              ? "h-4 w-4 border-gray-300 text-indigo-600 focus:ring-indigo-500"
              : "h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
          }
        />
        <span>{label}</span>
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="text-xs text-indigo-600 hover:underline"
        >
          {expanded ? "항목 접기" : `${option.item_count}개 항목 보기`}
        </button>
      </div>
      {expanded && (
        <p className="ml-6 mt-1 text-xs leading-relaxed text-gray-500">
          {option.item_names.join(" · ")}
        </p>
      )}
    </div>
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
    <div className="rounded-lg border border-gray-200 p-3">
      <label className="flex items-center gap-2 text-sm font-medium text-gray-800">
        <input
          type="checkbox"
          checked={included}
          onChange={(e) => onToggleIncluded(e.target.checked)}
          className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
        />
        {taskType} 포함
      </label>
      {included && hasModules && (
        <div className="mt-2 space-y-1.5 pl-6">
          {(options?.groups ?? []).map((group, gi) => (
            <div key={gi} className="space-y-1">
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
type LineItemPatch = Partial<Pick<LineItem, "category" | "name" | "amount">>;

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
// 인라인 편집 패턴). PDF/xlsx 발급은 실제로는 항목명・카테고리・금액만 반영하므로(단가/작업일/
// 수량은 발급 시 카탈로그에서 다시 계산됨) 편집 대상도 이 두 값으로만 한정한다.
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
        "w-full rounded px-1 py-0.5 hover:bg-indigo-50 " + (align === "right" ? "text-right" : "text-left")
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

function renderDetailValue(item: LineItem, key: string): string {
  if (key === "unit_price") return item.unit_price != null ? `${item.unit_price.toLocaleString()}원` : "—";
  if (key === "work_days") return item.work_days != null ? `${item.work_days}일` : "—";
  if (key === "quantity") return item.quantity != null ? String(item.quantity) : "—";
  return "—";
}

function ItemDetailCells({ item, order }: { item: LineItem; order: string[] }) {
  return (
    <>
      {order.map((key) => (
        <td key={key} className="py-2 pr-3 text-right text-sm text-gray-600">
          {renderDetailValue(item, key)}
        </td>
      ))}
    </>
  );
}

function CategoryRows({
  group,
  order,
  hasNote,
  onEditItem,
}: {
  group: LineItemGroup;
  order: string[];
  hasNote: boolean;
  onEditItem: (index: number, patch: LineItemPatch) => Promise<void>;
}) {
  const [expanded, setExpanded] = useState(true);
  const isFlat = group.items.length === 1 && group.items[0].name === group.category;

  if (isFlat) {
    const item = group.items[0];
    return (
      <tr className="border-b border-gray-200 bg-white last:border-b-0">
        <td className="px-3 py-2.5 text-gray-800">
          <InlineEditCell
            value={group.category}
            display={group.category}
            onSave={(v) => onEditItem(item._index, { category: v, name: v })}
          />
        </td>
        <ItemDetailCells item={item} order={order} />
        <td className="px-3 py-2.5 text-right font-semibold text-gray-900">
          <InlineEditCell
            value={String(item.amount)}
            display={`${group.amount.toLocaleString()}원`}
            align="right"
            inputType="number"
            onSave={(v) => onEditItem(item._index, { amount: Number(v) })}
          />
        </td>
        {hasNote && <td className="px-3 py-2.5 text-sm text-gray-400">{item.note ?? ""}</td>}
      </tr>
    );
  }

  return (
    <>
      <tr className="border-b border-gray-200 bg-white last:border-b-0">
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
          <tr key={item._index} className="border-b border-gray-200 bg-gray-50 last:border-b-0">
            <td className="py-2 pl-9 pr-3 text-sm text-gray-700">
              <InlineEditCell
                value={item.name}
                display={item.name}
                onSave={(v) => onEditItem(item._index, { name: v })}
              />
            </td>
            <ItemDetailCells item={item} order={order} />
            <td className="py-2 pr-3 text-right text-sm text-gray-700">
              <InlineEditCell
                value={String(item.amount)}
                display={`${item.amount.toLocaleString()}원`}
                align="right"
                inputType="number"
                onSave={(v) => onEditItem(item._index, { amount: Number(v) })}
              />
            </td>
            {hasNote && <td className="py-2 pr-3 text-sm text-gray-400">{item.note ?? ""}</td>}
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
  onSaveLineItems,
}: {
  items: LineItem[];
  columnLabels: Record<string, string>;
  detailColumnOrder: string[];
  totalAmount: number;
  vatIncluded: boolean;
  onSaveLineItems: (items: LineItem[]) => Promise<void>;
}) {
  const groups = groupLineItems(items);
  const order = detailColumnOrder.length > 0 ? detailColumnOrder : DEFAULT_DETAIL_ORDER;
  const labelFor = (key: string) => columnLabels[key] ?? DEFAULT_COLUMN_LABELS[key] ?? key;
  const hasNote = Boolean(columnLabels.note);
  const labelColSpan = 1 + order.length;
  const { supplyAmount, vatAmount, grandTotal } = computeVatBreakdown(totalAmount, vatIncluded);

  async function handleEditItem(index: number, patch: LineItemPatch) {
    const next = items.map((item, i) => (i === index ? { ...item, ...patch } : item));
    await onSaveLineItems(next);
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
      <table className="w-full min-w-[560px] border-collapse text-base">
        <thead>
          <tr className="border-b border-gray-200 bg-gray-100">
            <th className="px-3 py-2 text-left text-sm font-semibold text-gray-600">
              {labelFor("item_name")}
            </th>
            {order.map((key) => (
              <th key={key} className="px-3 py-2 text-right text-sm font-semibold text-gray-600">
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
            <CategoryRows key={gi} group={g} order={order} hasNote={hasNote} onEditItem={handleEditItem} />
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

      {quote.line_items.length > 0 && (
        <div className="mt-4">
          <p className="mb-1.5 text-xs font-semibold text-gray-400">실제 양식 미리보기</p>
          <iframe
            key={hashKey({ items: quote.line_items, total: quote.total_amount, service: quote.service_name })}
            src={getEntityQuotePdfUrl(quote.id, { inline: true })}
            title={`${quote.entity_name} 견적서 미리보기`}
            className="h-[800px] w-full rounded-lg border border-gray-200"
          />
        </div>
      )}
    </div>
  );
}

function EditChatModal({
  quote,
  messages,
  vatIncluded,
  onSend,
  onClose,
  onSaveLineItems,
}: {
  quote: EntityQuote;
  messages: ChatMessage[];
  vatIncluded: boolean;
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
  }, [messages]);

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
                  {m.text}
                  {m.scope && m.scope !== "quote_only" && (
                    <p className="mt-1 text-xs font-medium text-amber-600">
                      ⚠ {SCOPE_LABEL[m.scope] ?? m.scope}
                    </p>
                  )}
                </div>
              </div>
            ))}
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

export default function EstimateWizard() {
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

  const [moduleOptions, setModuleOptions] = useState<EntityModuleOptions[]>([]);
  const [moduleSelections, setModuleSelections] = useState<Record<string, string[]>>({});

  const primaryEntityId = entitySelections.find((s) => s.role === "primary")?.entityId ?? "";
  const primaryIsTestify = entities.find((e) => e.id === primaryEntityId)?.name === TESTIFY_NAME;
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
    setEntitySelections((prev) =>
      prev.map((s) => {
        if (s.entityId !== entityId) return s;
        let moduleNames = s.tasks[taskType].moduleNames;
        if (included && moduleNames.length === 0) {
          // 처음 포함시킬 때 variant(라디오) 그룹의 기본값을 자동으로 골라준다 — 라디오는 항상
          // 하나가 선택돼 있어야 하므로 이렇게 하면 "시장검증 최소 1개" 조건이 자연히 만족된다.
          const options = moduleOptionsCache[`${entityId}:${taskType}`];
          for (const group of options?.groups ?? []) {
            if (group.kind === "variant") {
              const def = group.options.find((o) => o.is_default) ?? group.options[0];
              if (def) moduleNames = [...moduleNames, ...def.module_names];
            }
          }
        }
        return { ...s, tasks: { ...s.tasks, [taskType]: { included, moduleNames } } };
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

  const allEntitiesHaveTask = entitySelections.every((s) => FIXED_TASK_TYPES.some((t) => s.tasks[t].included));

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
        total_amount: Number(totalAmount),
        vat_included: vatIncluded,
        entities: entitySelections.map((s) => ({
          entity_id: s.entityId,
          is_primary: s.role === "primary",
          task_types: FIXED_TASK_TYPES.filter((t) => s.tasks[t].included),
        })),
        service_name: primaryIsTestify ? serviceName : undefined,
      });
      setResult(created);

      // 생성된 entity_quote(기업×과업종류별 row)마다, 그 기업이 그 과업종류에서 고른 모듈을 매칭한다.
      const bySelection = new Map(entitySelections.map((s) => [s.entityId, s]));
      const selections: Record<string, string[]> = {};
      for (const quote of created.entity_quotes) {
        const selection = bySelection.get(quote.entity_id);
        selections[quote.id] = selection?.tasks[quote.task_type as FixedTaskType]?.moduleNames ?? [];
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
        ? editResult.changed_items.map((i) => `${i.name} → ${i.amount.toLocaleString()}원`).join(", ")
        : "요청하신 내용을 반영했습니다.";

    setChatHistory((prev) => ({
      ...prev,
      [quoteId]: [...(prev[quoteId] ?? []), { role: "assistant", text: summary, scope: editResult.scope }],
    }));
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
            onSend={(text) => handleSendEdit(activeQuote.id, text)}
            onClose={() => setActiveQuoteId(null)}
            onSaveLineItems={(items) => handleSaveLineItems(activeQuote.id, items)}
          />
        )}
      </div>
    );
  }

  return (
    <div className="space-y-8 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
      <div>
        <h2 className="text-2xl font-bold text-gray-900">견적서 생성</h2>
        <p className="mt-2 text-base text-gray-500">
          기업을 먼저 선택하면, 본견적/비교견적 역할과 과업(마케팅·시장검증)을 기업별로 자유롭게 조합할 수 있습니다.
        </p>
      </div>

      {error && (
        <div className="rounded-md bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      )}

      {/* Step 1: 기업 선택 */}
      <fieldset>
        <legend className="text-base font-semibold text-gray-900">
          1. 기업 선택 <span className="font-normal text-gray-400">(다중 선택, 최소 1곳)</span>
        </legend>
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
                    "rounded-full border px-4 py-2 text-base " +
                    (selected
                      ? "border-indigo-600 bg-indigo-600 text-white"
                      : "border-gray-300 text-gray-700 hover:border-gray-400")
                  }
                >
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
          <legend className="text-base font-semibold text-gray-900">
            2. 본견적/비교견적 지정 <span className="font-normal text-gray-400">(본견적 최대 1곳, 비교견적 최대 {MAX_COMPARISON}곳)</span>
          </legend>
          <div className="mt-3 space-y-2">
            {entitySelections.map((s) => {
              const entityName = entities.find((e) => e.id === s.entityId)?.name ?? s.entityId;
              return (
                <div
                  key={s.entityId}
                  className="flex flex-wrap items-center gap-4 rounded-lg border border-gray-200 px-4 py-2.5"
                >
                  <span className="min-w-24 text-base font-medium text-gray-900">{entityName}</span>
                  <label className="flex items-center gap-1.5 text-sm text-gray-700">
                    <input
                      type="radio"
                      name={`role-${s.entityId}`}
                      checked={s.role === "primary"}
                      onChange={() => setRole(s.entityId, "primary")}
                      className="h-4 w-4 text-indigo-600 focus:ring-indigo-500"
                    />
                    본견적
                  </label>
                  <label className="flex items-center gap-1.5 text-sm text-gray-700">
                    <input
                      type="radio"
                      name={`role-${s.entityId}`}
                      checked={s.role === "comparison"}
                      onChange={() => setRole(s.entityId, "comparison")}
                      className="h-4 w-4 text-indigo-600 focus:ring-indigo-500"
                    />
                    비교견적 <span className="text-gray-400">(+10%)</span>
                  </label>
                </div>
              );
            })}
          </div>
        </fieldset>
      )}

      {/* Step 3: 과업 선택 (기업별 마케팅/시장검증 교차 선택) */}
      {entitySelections.length > 0 && (
        <fieldset>
          <legend className="text-base font-semibold text-gray-900">
            3. 과업 선택 <span className="font-normal text-gray-400">(기업마다 마케팅·시장검증 교차 선택 가능)</span>
          </legend>
          <div className="mt-3 space-y-4">
            {entitySelections.map((s) => {
              const entityName = entities.find((e) => e.id === s.entityId)?.name ?? s.entityId;
              const availableTaskTypes = FIXED_TASK_TYPES.filter((t) => !excludedByTask[t].has(s.entityId));
              return (
                <div key={s.entityId} className="rounded-xl border border-gray-200 p-4">
                  <p className="text-sm font-semibold text-gray-900">{entityName}</p>
                  <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-2">
                    {availableTaskTypes.map((taskType) => (
                      <TaskModulePicker
                        key={taskType}
                        entityId={s.entityId}
                        taskType={taskType}
                        included={s.tasks[taskType].included}
                        moduleNames={s.tasks[taskType].moduleNames}
                        options={moduleOptionsCache[`${s.entityId}:${taskType}`]}
                        onToggleIncluded={(included) => toggleTaskIncluded(s.entityId, taskType, included)}
                        onSetVariant={(group, option) => setVariantModule(s.entityId, taskType, group, option)}
                        onToggleAdditive={(option, checked) =>
                          toggleAdditiveModule(s.entityId, taskType, option, checked)
                        }
                      />
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </fieldset>
      )}

      {/* Step 4: 사업명 + 총액 */}
      {entitySelections.length > 0 && (
        <fieldset className="space-y-4">
          <legend className="text-base font-semibold text-gray-900">4. 사업 정보</legend>
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
