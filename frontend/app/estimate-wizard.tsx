"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useGeneratedEstimateLayout } from "./app-shell";
import {
  ApiError,
  createEstimateSet,
  editEntityQuote,
  fetchCatalogModuleOptions,
  fetchEntities,
  fetchEstimateSet,
  fetchModuleOptions,
  fetchQuoteVersions,
  generateEstimateSet,
  regenerateComparisons,
  updateMarkupRatio,
  getEntityQuotePdfUrl,
  getEntityQuoteXlsxUrl,
  updateLineItems,
  updateQuoteDate,
  updateRecipientInfo,
  updateServiceName,
  type ChatAttachment,
  type ComparisonMode,
  type CatalogModuleOptions,
  type EntityModuleOptions,
  type EntityOption,
  type EntityQuote,
  type EstimateSet,
  type LineItem,
  type ModuleGroup,
  type ModuleOption,
  type RecipientInfoInput,
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
// 용역명뿐 아니라 수신자/담당자/연락처/이메일도 같은 패턴이라(2026-08-12) 공용 컴포넌트로 뺐다 —
// placeholder만으로는 칸이 비면 무슨 값인지 알 수 없다는 사용자 피드백으로 "라벨 :" 을 항상 보여준다.
// required 필드 강조색 — 기본은 기존 남색(용역명/수신자), ABBG·알파브라더스 담당자/연락처/
// 이메일은 사용자 요청으로 보라색을 쓴다(2026-08-13).
const REQUIRED_COLOR_CLASSES: Record<"indigo" | "purple", { badge: string; border: string }> = {
  indigo: { badge: "text-indigo-600", border: "border-amber-300" },
  purple: { badge: "text-purple-600", border: "border-purple-300" },
};

function LabeledInlineField({
  label,
  value,
  placeholder,
  type = "text",
  autoComplete,
  required = false,
  requiredColor = "indigo",
  onSave,
}: {
  label: string;
  value: string;
  placeholder: string;
  type?: "text" | "tel" | "email";
  autoComplete?: string;
  required?: boolean;
  requiredColor?: "indigo" | "purple";
  onSave: (value: string) => Promise<void>;
}) {
  const [draft, setDraft] = useState(value);
  const [saving, setSaving] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  async function handleSave() {
    const trimmed = draft.trim();
    if (trimmed === value || saving) return;
    if (required && !trimmed) return;
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
    <label className="block min-w-0" onClick={(e) => e.stopPropagation()}>
      <span className="mb-1.5 flex items-center gap-1 text-xs font-semibold text-slate-600">
        {label}
        {required && <span className={REQUIRED_COLOR_CLASSES[requiredColor].badge}>필수</span>}
      </span>
      <div className="relative">
      <input
        type={type}
        autoComplete={autoComplete}
        value={draft}
        disabled={saving}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={handleSave}
        onKeyDown={(e) => e.key === "Enter" && handleSave()}
        placeholder={placeholder}
        className={
          "h-9 w-full rounded-lg border bg-white px-3 pr-12 text-sm text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-indigo-500 focus:ring-3 focus:ring-indigo-100 " +
          (required && !draft.trim() ? REQUIRED_COLOR_CLASSES[requiredColor].border : "border-slate-200 hover:border-slate-300")
        }
      />
      {saving && <span className="absolute right-2.5 top-2.5 text-xs text-slate-400">저장 중…</span>}
      {!saving && value && draft.trim() === value && (
        <span className="absolute right-2.5 top-2 flex h-5 w-5 items-center justify-center rounded-full bg-emerald-50 text-xs text-emerald-600" aria-label="저장됨">✓</span>
      )}
      </div>
      {errorMsg && <span className="mt-1 block text-xs text-red-600">{errorMsg}</span>}
    </label>
  );
}

function ServiceNameField({
  quote,
  onSave,
}: {
  quote: EntityQuote;
  onSave: (value: string) => Promise<void>;
}) {
  return (
    <LabeledInlineField
      label="용역명"
      value={quote.service_name ?? ""}
      placeholder="예: 정량·정성 데이터 기반 시장검증 용역"
      onSave={onSave}
    />
  );
}

// 담당자/연락처/이메일 칸은 ABBG·알파브라더스 양식에만 있다(010_seed_quote_templates.sql
// header_fields의 client_contact/client_phone/client_email). 수신자(고객사명)는 모든 법인
// 양식에 대응 칸이 있어 공통으로 보여준다.
// 견적서 상단에 담당자/연락처/이메일 칸이 있는 양식들. 테스티파이는 039 마이그레이션으로
// 알파브라더스형 신양식으로 갈아타면서 이 칸들이 생겼다(2026-08-19).
const RECIPIENT_CONTACT_ENTITIES = ["ABBG", "알파브라더스", "테스티파이"];

function RecipientInfoFields({
  quote,
  onSave,
}: {
  quote: EntityQuote;
  onSave: (input: RecipientInfoInput) => Promise<void>;
}) {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      <LabeledInlineField
        label="수신자"
        value={quote.recipient_name ?? ""}
        placeholder="예: 주식회사 미구"
        onSave={(value) => onSave({ recipient_name: value })}
      />
      {RECIPIENT_CONTACT_ENTITIES.includes(quote.entity_name) && (
        <>
          <LabeledInlineField
            label="담당자"
            value={quote.recipient_contact ?? ""}
            placeholder="예: 김미구"
            required
            requiredColor="purple"
            onSave={(value) => onSave({ recipient_contact: value })}
          />
          <LabeledInlineField
            label="연락처"
            value={quote.recipient_phone ?? ""}
            placeholder="예: 010-1234-5678"
            type="tel"
            autoComplete="tel"
            required
            requiredColor="purple"
            onSave={(value) => onSave({ recipient_phone: value })}
          />
          <LabeledInlineField
            label="이메일"
            value={quote.recipient_email ?? ""}
            placeholder="예: migu@company.com"
            type="email"
            autoComplete="email"
            required
            requiredColor="purple"
            onSave={(value) => onSave({ recipient_email: value })}
          />
        </>
      )}
    </div>
  );
}

function QuoteDateField({
  quote,
  onSave,
}: {
  quote: EntityQuote;
  onSave: (value: string) => Promise<void>;
}) {
  const [saving, setSaving] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  async function handleChange(next: string) {
    if (!next || next === quote.quote_date || saving) return;
    setSaving(true);
    setErrorMsg(null);
    try {
      await onSave(next);
    } catch (e) {
      setErrorMsg(e instanceof ApiError ? e.message : "저장에 실패했습니다.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <label className="block min-w-0" onClick={(e) => e.stopPropagation()}>
      <span className="mb-1.5 flex items-center gap-1 text-xs font-semibold text-slate-600">
        작성일 <span className="text-indigo-600">필수</span>
      </span>
      <div className="relative">
      <input
        type="date"
        defaultValue={quote.quote_date ?? ""}
        disabled={saving}
        onChange={(e) => handleChange(e.target.value)}
        className="h-9 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none transition hover:border-slate-300 focus:border-indigo-500 focus:ring-3 focus:ring-indigo-100"
      />
      {saving && <span className="absolute right-10 top-3 text-xs text-slate-400">저장 중…</span>}
      </div>
      {errorMsg && <span className="mt-1 block text-xs text-red-600">{errorMsg}</span>}
    </label>
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
        <ToggleSwitch checked={included} onLabel={taskType} />
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
    | "category"
    | "mid_category"
    | "name"
    | "amount"
    | "unit_price"
    | "work_days"
    | "quantity"
    | "note"
    | "description"
    | "input_mm"
    | "tax_amount"
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
// 금액 입력칸에 원 단위 천단위 콤마를 실시간으로 붙여준다(2026-08-13 사용자 요청) — 숫자만
// 남기고 다시 콤마를 끼워 넣는 방식이라 커서가 끝으로 튀는 것 말고는 부작용이 없다.
function formatWithCommas(raw: string): string {
  const digits = raw.replace(/[^\d-]/g, "");
  if (digits === "" || digits === "-") return digits;
  const negative = digits.startsWith("-");
  const intPart = (negative ? digits.slice(1) : digits).replace(/^0+(?=\d)/, "");
  return (negative ? "-" : "") + intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

function InlineEditCell({
  value,
  display,
  align = "left",
  inputType = "text",
  multiline = false,
  onSave,
}: {
  value: string;
  display: string;
  align?: "left" | "right";
  inputType?: "text" | "number";
  /** 상품구성처럼 개조식 여러 줄을 쓰는 칸. textarea로 열려 Enter가 줄바꿈이 된다. */
  multiline?: boolean;
  onSave: (nextValue: string) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(inputType === "number" ? formatWithCommas(value) : value);
  const [saving, setSaving] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  // Enter로 저장이 끝난 직후 짧게 배경색을 강조했다 되돌려, "수정한 내용이 바로 반영됐다"는
  // 모션을 준다(2026-08-13 사용자 요청).
  const [justSaved, setJustSaved] = useState(false);
  const rawDraft = inputType === "number" ? draft.replace(/,/g, "") : draft;
  // PDF 반영(저장 API + 세트 재조회)은 시간이 걸려도, Enter를 누르면 그 기다림과 무관하게 즉시
  // 칸을 빠져나오고 입력한 값을 먼저 보여준다(2026-08-13 사용자 요청 — 이전엔 저장이 끝나야
  // 칸에서 빠져나왔음). commit()이 두 번(Enter → blur) 겹쳐 불리는 걸 막는 가드.
  const committedRef = useRef(false);
  const [pendingLabel, setPendingLabel] = useState<string | null>(null);

  function startEditing() {
    committedRef.current = false;
    setErrorMsg(null);
    setDraft(inputType === "number" ? formatWithCommas(value) : value);
    setEditing(true);
  }

  async function commit() {
    if (committedRef.current) return;
    committedRef.current = true;
    if (rawDraft === value) {
      setEditing(false);
      return;
    }
    if (inputType === "number" && (rawDraft.trim() === "" || Number.isNaN(Number(rawDraft)))) {
      setErrorMsg("숫자를 입력하세요.");
      committedRef.current = false;
      return;
    }
    setErrorMsg(null);
    setSaving(true);
    setPendingLabel(draft);
    setEditing(false); // 저장 완료를 기다리지 않고 바로 칸을 빠져나온다 — 저장은 아래에서 이어서 진행.
    try {
      await onSave(rawDraft);
      setJustSaved(true);
      setTimeout(() => setJustSaved(false), 600);
    } catch (e) {
      setErrorMsg(e instanceof ApiError ? e.message : "저장에 실패했습니다.");
      committedRef.current = false;
      setEditing(true); // 실패하면 다시 편집 상태로 돌아가 고칠 수 있게 한다.
    } finally {
      setSaving(false);
      setPendingLabel(null);
    }
  }

  if (editing) {
    return (
      <div onClick={(e) => e.stopPropagation()}>
        {multiline ? (
          // 상품구성은 "1. ~ 2. ~ 3. ~" 개조식 여러 줄이 기본이라 한 줄짜리 input으로는 아예
          // 쓸 수가 없었다(2026-08-21 사용자 지적). Enter는 줄바꿈이고, 저장은 ⌘/Ctrl+Enter나
          // 칸 밖 클릭으로 한다.
          <>
            <textarea
              autoFocus
              rows={Math.min(12, Math.max(3, draft.split("\n").length + 1))}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onBlur={commit}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                  e.preventDefault();
                  commit();
                }
                if (e.key === "Escape") {
                  committedRef.current = true;
                  setDraft(value);
                  e.currentTarget.blur();
                  setEditing(false);
                }
              }}
              className="w-full resize-y rounded border border-indigo-400 px-1.5 py-1 text-[13px] leading-snug focus:outline-none"
            />
            <p className="mt-0.5 text-[11px] text-gray-400">Enter 줄바꿈 · ⌘/Ctrl+Enter 저장 · Esc 취소</p>
          </>
        ) : (
        <input
          type="text"
          inputMode={inputType === "number" ? "numeric" : undefined}
          autoFocus
          value={draft}
          onChange={(e) =>
            setDraft(inputType === "number" ? formatWithCommas(e.target.value) : e.target.value)
          }
          onFocus={(e) => e.target.select()}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              commit();
            }
            if (e.key === "Escape") {
              committedRef.current = true; // Escape는 저장하지 않고 그냥 나간다.
              setDraft(inputType === "number" ? formatWithCommas(value) : value);
              e.currentTarget.blur();
              setEditing(false);
            }
          }}
          className={
            "w-full rounded border border-indigo-400 px-1.5 py-0.5 text-sm focus:outline-none " +
            (align === "right" ? "text-right" : "text-left")
          }
        />
        )}
        {errorMsg && <p className="mt-0.5 text-xs text-red-600">{errorMsg}</p>}
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        startEditing();
      }}
      title="클릭해서 수정"
      disabled={saving}
      className={
        "w-full rounded px-1 py-0.5 transition-colors duration-500 hover:bg-indigo-50 " +
        (inputType === "number" ? "whitespace-nowrap " : "whitespace-pre-line break-words ") +
        (align === "right" ? "text-right" : "text-left") +
        (justSaved ? " bg-amber-100" : "") +
        (saving ? " text-gray-400" : "")
      }
    >
      {/* 값이 비면 버튼에 내용이 없어 높이가 4px로 찌그러져 클릭할 수가 없었다 — 새로 추가한
          행의 상품구성 칸이 아예 안 눌리던 원인(2026-08-21 사용자 지적). */}
      {saving ? pendingLabel : display || <span className="text-gray-300">입력</span>}
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
            className={
              "py-2 pr-3 text-[13px] leading-snug text-gray-600 " +
              (isText ? "text-left align-top" : "whitespace-nowrap text-right")
            }
          >
            {/* 상품구성은 개조식 10줄이 넘어가는 항목이 있어(주간 액션플랜 등) 한 행이 화면
                절반을 잡아먹었다(2026-08-21 사용자 지적). 높이를 묶고 넘치면 그 칸만 스크롤해
                다른 항목과 나란히 비교할 수 있게 한다. 클릭하면 편집은 그대로 된다. */}
            <div className={isText ? "max-h-32 overflow-y-auto pr-1 focus-within:max-h-none focus-within:overflow-visible" : ""}>
            <InlineEditCell
              value={renderDetailEditValue(item, key)}
              display={renderDetailValue(item, key)}
              align={isText ? "left" : "right"}
              inputType={isText ? "text" : "number"}
              multiline={isText}
              onSave={(v) => onEditItem({ [key]: isText ? v : Number(v) } as LineItemPatch)}
            />
            </div>
          </td>
        );
      })}
    </>
  );
}

// 행 추가·삭제 버튼. 열을 새로 만들지 않고 상품명 칸 아래에 붙인다 — 표가 table-fixed라
// 열을 추가하면 폭 합 100%가 깨져 "원"이 잘린다(2026-08-21). 행에 마우스를 올렸을 때만 보인다.
// 새 행은 같은 구분(대)으로 바로 아래에 들어간다. 없던 구분(대)을 만드는 건 채팅으로 한다.
function RowActions({ onAdd, onRemove }: { onAdd: () => void; onRemove: () => void }) {
  return (
    <span className="mt-1 flex gap-1.5 opacity-0 transition group-hover:opacity-100">
      <button
        type="button"
        onClick={onAdd}
        title="이 아래에 같은 구분으로 항목 추가"
        aria-label="이 아래에 항목 추가"
        className="rounded border border-slate-200 bg-white px-1.5 py-px text-[11px] font-bold leading-4 text-slate-500 hover:border-indigo-300 hover:text-indigo-600"
      >
        +
      </button>
      <button
        type="button"
        onClick={onRemove}
        title="이 항목 삭제"
        aria-label="이 항목 삭제"
        className="rounded border border-slate-200 bg-white px-1.5 py-px text-[11px] font-bold leading-4 text-slate-500 hover:border-rose-300 hover:text-rose-600"
      >
        ✕
      </button>
    </span>
  );
}

function CategoryRows({
  group,
  order,
  hasNote,
  showCategorySplit,
  highlightKeys,
  onEditItem,
  onPatchMany,
  onAddAfter,
  onRemoveItem,
}: {
  group: LineItemGroup;
  order: string[];
  hasNote: boolean;
  showCategorySplit: boolean;
  highlightKeys?: Set<string>;
  onEditItem: (index: number, patch: LineItemPatch) => Promise<void>;
  onPatchMany: (indexes: number[], patch: LineItemPatch) => Promise<void>;
  onAddAfter: (index: number) => void;
  onRemoveItem: (index: number) => void;
}) {
  const [expanded, setExpanded] = useState(true);
  const isFlat = group.items.length === 1 && group.items[0].name === group.category;
  // 채팅 수정으로 방금 바뀐 항목에 왼쪽 강조선 + 옅은 배경을 준다 — "어디가 수정되고 있는지
  // 모르겠다"는 피드백(2026-08-10) 대응. 다음 수정이나 항목 재생성 전까지 유지된다.
  const isChanged = (item: { category: string; name: string }) =>
    highlightKeys?.has(`${item.category}::${item.name}`) ?? false;
  // 구분(대)에는 모듈명(group.category), 구분(중)에는 항목의 mid_category를 보여준다 —
  // 발급되는 PDF(pdf_service._collect_item_block_updates)와 같은 값이어야 한다. 구분(중)이
  // 없는 카탈로그는 구분(대)와 같은 값으로 채워진다(2026-08-19).
  // 표가 table-fixed라 열 폭이 고정이다 — 여기에 whitespace-nowrap을 주면 긴 구분명이
  // 줄바꿈 없이 옆 칸 위로 그대로 흘러넘쳐 상품명과 겹쳐 보였다(2026-08-20 사용자 지적).
  // 넘칠 때는 줄을 바꿔 담는다.
  const splitCells = (item?: IndexedLineItem) =>
    showCategorySplit && (
      <>
        <td className="break-words px-3 py-2.5 text-sm text-gray-600">
          <InlineEditCell
            value={group.category}
            display={group.category}
            onSave={(v) => onPatchMany(group.items.map((it) => it._index), { category: v })}
          />
        </td>
        <td className="break-words px-3 py-2.5 text-sm text-gray-600">
          <InlineEditCell
            value={item?.mid_category ?? group.category}
            display={item?.mid_category ?? group.category}
            onSave={(v) =>
              onPatchMany(item ? [item._index] : group.items.map((it) => it._index), { mid_category: v })
            }
          />
        </td>
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
        {splitCells(item)}
        <td className="px-3 py-2.5 text-gray-800">
          <InlineEditCell
            value={group.category}
            display={group.category}
            onSave={(v) => onEditItem(item._index, { category: v, name: v })}
          />
        </td>
        <ItemDetailCells item={item} order={order} onEditItem={(patch) => onEditItem(item._index, patch)} />
        <td className="whitespace-nowrap px-3 py-2.5 text-right font-semibold text-gray-900">
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

  // 실제 발급 양식은 같은 구분(대)를 셀 하나로 병합해 보여준다 — 미리보기가 행마다 같은 값을
  // 반복하면 발급본과 달라 보이고, 접기 토글이 가운데 상품명 칸에 있어 어느 묶음을 접는지도
  // 헷갈렸다(2026-08-21 사용자 지적). 토글을 맨 왼쪽 구분(대) 칸으로 옮기고 그 칸을 묶음
  // 전체에 rowSpan으로 병합한다. 구분(중)도 연속으로 같은 값이면 같은 방식으로 묶는다.
  const groupIndexes = group.items.map((it) => it._index);
  const bodyRowCount = expanded ? group.items.length : 0;
  const midRunLength = (i: number) => {
    const value = group.items[i].mid_category ?? group.category;
    if (i > 0 && (group.items[i - 1].mid_category ?? group.category) === value) return 0; // 위 칸에 병합됨
    let n = 1;
    while (i + n < group.items.length && (group.items[i + n].mid_category ?? group.category) === value) n += 1;
    return n;
  };

  // 구분(대)/구분(중) 칸이 있는 양식은 병합 셀이 곧 묶음 라벨이라 소계 행이 필요 없다.
  // 펼친 상태에서는 항목 행만 그리고, 구분(대) 셀을 첫 항목 행에서 통째로 병합한다.
  if (showCategorySplit && expanded) {
    return (
      <>
        {group.items.map((item, i) => (
          <tr
            key={item._index}
            className={
              "group border-b border-gray-200 last:border-b-0 " +
              (isChanged(item) ? "border-l-4 border-l-amber-400 bg-amber-50" : "bg-white")
            }
          >
            {i === 0 && (
              <td
                rowSpan={group.items.length}
                className="border-r border-gray-200 bg-slate-50/70 px-2.5 py-2 align-top text-[13px] font-semibold leading-snug text-slate-700"
              >
                {/* 접기 토글과 이름 편집을 갈라놨다 — 칸 전체가 토글이면 구분명을 고칠 수가 없다. */}
                <div className="flex min-w-0 items-start gap-1">
                  <button
                    type="button"
                    onClick={() => setExpanded(false)}
                    title="이 묶음 접기"
                    aria-label="이 묶음 접기"
                    className="shrink-0"
                  >
                    <svg viewBox="0 0 20 20" fill="currentColor" className="mt-1 h-3 w-3 rotate-90 text-gray-400">
                      <path fillRule="evenodd" d="M6 4l8 6-8 6V4z" clipRule="evenodd" />
                    </svg>
                  </button>
                  <InlineEditCell
                    value={group.category}
                    display={group.category}
                    onSave={(v) => onPatchMany(groupIndexes, { category: v })}
                  />
                </div>
              </td>
            )}
            {midRunLength(i) > 0 && (
              <td
                rowSpan={midRunLength(i)}
                className="border-r border-gray-200 bg-slate-50/40 px-2.5 py-2 align-top text-[13px] leading-snug text-slate-600 break-words"
              >
                {/* 같은 값이 이어지는 구간을 한 칸으로 병합해 보여주므로, 고치면 그 구간 전체에
                    적용한다 — 한 행만 바뀌면 병합이 쪼개져 발급본과 달라진다. */}
                <InlineEditCell
                  value={item.mid_category ?? group.category}
                  display={item.mid_category ?? group.category}
                  onSave={(v) =>
                    onPatchMany(
                      group.items.slice(i, i + midRunLength(i)).map((it) => it._index),
                      { mid_category: v }
                    )
                  }
                />
              </td>
            )}
            <td className="px-2.5 py-2 align-top text-[13px] text-gray-800">
              <InlineEditCell
                value={item.name}
                display={item.name}
                onSave={(v) => onEditItem(item._index, { name: v })}
              />
              <RowActions
                onAdd={() => onAddAfter(item._index)}
                onRemove={() => onRemoveItem(item._index)}
              />
            </td>
            <ItemDetailCells item={item} order={order} onEditItem={(patch) => onEditItem(item._index, patch)} />
            <td className="whitespace-nowrap py-2 pr-3 text-right align-top text-[13px] text-gray-700">
              <InlineEditCell
                value={String(item.amount)}
                display={`${item.amount.toLocaleString()}원`}
                align="right"
                inputType="number"
                onSave={(v) => onEditItem(item._index, { amount: Number(v) })}
              />
            </td>
            {hasNote && (
              <td className="py-2 pr-3 align-top text-[13px] text-gray-600">
                <InlineEditCell
                  value={item.note ?? ""}
                  display={item.note ?? ""}
                  onSave={(v) => onEditItem(item._index, { note: v })}
                />
              </td>
            )}
          </tr>
        ))}
        {/* 묶음이 끝나는 자리에 그 구분(대)의 공급가액 합계를 한 줄로 보여준다 — 항목이 길어
            지면 이 묶음이 얼마인지 한눈에 안 보였다(2026-08-21 사용자 요청). */}
        <tr className="border-b-2 border-gray-300 bg-slate-50/60">
          <td className="px-2.5 py-1.5" colSpan={3 + order.length} />
          <td className="whitespace-nowrap py-1.5 pr-3 text-right text-[13px] font-bold text-slate-700">
            {group.amount.toLocaleString()}원
          </td>
          {hasNote && <td className="py-1.5" />}
        </tr>
      </>
    );
  }

  return (
    <>
      <tr className="border-b border-gray-200 bg-white last:border-b-0">
        {showCategorySplit && (
          <td
            rowSpan={1 + bodyRowCount}
            className="border-r border-gray-200 bg-slate-50/70 px-2.5 py-2 align-top text-[13px] font-semibold leading-snug text-slate-700"
          >
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              className="flex min-w-0 items-start gap-1.5 break-words text-left"
            >
              <svg
                viewBox="0 0 20 20"
                fill="currentColor"
                className={"mt-1 h-3.5 w-3.5 shrink-0 text-gray-500 transition-transform " + (expanded ? "rotate-90" : "")}
              >
                <path fillRule="evenodd" d="M6 4l8 6-8 6V4z" clipRule="evenodd" />
              </svg>
              {group.category}
            </button>
          </td>
        )}
        {showCategorySplit && <td className="border-r border-gray-200 bg-slate-50/70 px-2.5 py-2" />}
        <td className="px-3 py-2.5 font-bold text-gray-900">
          {showCategorySplit ? (
            <span className="text-sm text-gray-400">소계</span>
          ) : (
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              className="flex min-w-0 items-center gap-1.5 break-words text-left"
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
          )}
        </td>
        <td className="py-2 pr-3 text-right text-sm text-gray-400" colSpan={order.length} />
        <td className="whitespace-nowrap px-3 py-2.5 text-right font-bold text-gray-900">
          {group.amount.toLocaleString()}원
        </td>
        {hasNote && <td className="px-3 py-2.5" />}
      </tr>
      {expanded &&
        group.items.map((item, i) => (
          <tr
            key={item._index}
            className={
              "group border-b border-gray-200 last:border-b-0 " +
              (isChanged(item) ? "border-l-4 border-l-amber-400 bg-amber-50" : "bg-gray-50")
            }
          >
            {showCategorySplit && midRunLength(i) > 0 && (
              <td
                rowSpan={midRunLength(i)}
                className="border-r border-gray-200 bg-slate-50/40 px-2.5 py-2 align-top text-[13px] leading-snug text-slate-600 break-words"
              >
                {item.mid_category ?? group.category}
              </td>
            )}
            <td className="px-2.5 py-2 align-top text-[13px] text-gray-800">
              <InlineEditCell
                value={item.name}
                display={item.name}
                onSave={(v) => onEditItem(item._index, { name: v })}
              />
              <RowActions
                onAdd={() => onAddAfter(item._index)}
                onRemove={() => onRemoveItem(item._index)}
              />
            </td>
            <ItemDetailCells item={item} order={order} onEditItem={(patch) => onEditItem(item._index, patch)} />
            <td className="whitespace-nowrap py-2 pr-3 text-right text-sm text-gray-700">
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
function computeVatBreakdown(totalAmount: number) {
  // entity_quotes.total_amount는 **언제나 부가세 포함 총액**이다 — 백엔드
  // quote_pricing.grand_total이 vat_included와 무관하게 공급가액×1.1을 저장한다.
  // (vat_included는 "사용자가 입력한 총액을 공급가액으로 볼지 총액으로 볼지"를 정할 뿐이라
  // 생성 시점에만 쓰인다.)
  //
  // 예전엔 여기서 vat_included=false일 때 totalAmount를 공급가액으로 보고 부가세를 한 번 더
  // 더했다. 그래서 항목 합이 1,000,000원인 견적서가 공급가액 1,100,000 / 부가세 110,000 /
  // 총합계 1,210,000으로 표시됐다(2026-08-21 사용자 지적 — 부가세 이중 계산).
  const supplyAmount = Math.round(totalAmount / 1.1);
  return { supplyAmount, vatAmount: totalAmount - supplyAmount, grandTotal: totalAmount };
}

// 수정 반영하기 전 미리보기(pending) 항목들만으로 총합계를 화면에 보여줄 때 쓴다 —
// estimate_service.update_line_items의 grand_total 계산과 동일한 식이어야 커밋 후 값과
// 일치한다(2026-08-14).
function computeGrandTotal(items: LineItem[]): number {
  // 백엔드 quote_pricing.grand_total과 같은 식. vat_included와 무관하게 공급가액×1.1이다.
  const supply = items.reduce((sum, item) => sum + item.amount, 0);
  return supply + Math.round(supply * 0.1);
}

// 직접편집이든 채팅 수정이든 커밋("수정 반영하기") 전까지는 화면에서만 미리보이는 상태.
type PendingEdit = { items: LineItem[]; editRequestText: string };


// 백엔드 allocation_service.reconcile_amounts의 JS 쌍둥이 — 소계/총합계를 직접 고쳤을 때
// 항목들을 비례 배분한 뒤 1만원 단위로 떨어뜨리고, 남는 차액은 가장 큰 항목이 흡수한다.
// 두 구현이 같은 규칙을 따라야 "수정 반영하기" 전후로 금액이 흔들리지 않는다.
function LineItemTable({
  items,
  columnLabels,
  detailColumnOrder,
  totalAmount,
  amountUsesWorkDays,
  amountUsesQuantity,
  showCategorySplit = false,
  highlightKeys,
  onSaveLineItems,
}: {
  items: LineItem[];
  columnLabels: Record<string, string>;
  detailColumnOrder: string[];
  totalAmount: number;
  // 금액 계산식은 백엔드가 내려준다(EntityQuoteOut.amount_uses_*). 화면이 "단가×수량"으로
  // 하드코딩하면 규칙이 바뀔 때 화면과 발급본이 갈린다 — 실제로 그 사고가 났었다(2026-08-21).
  amountUsesWorkDays: boolean;
  amountUsesQuantity: boolean;
  showCategorySplit?: boolean;
  highlightKeys?: Set<string>;
  onSaveLineItems: (items: LineItem[]) => void;
}) {
  const groups = groupLineItems(items);
  const order = detailColumnOrder.length > 0 ? detailColumnOrder : DEFAULT_DETAIL_ORDER;
  const labelFor = (key: string) => columnLabels[key] ?? DEFAULT_COLUMN_LABELS[key] ?? key;
  const hasNote = Boolean(columnLabels.note);
  const labelColSpan = (showCategorySplit ? 2 : 0) + 1 + order.length;
  const { supplyAmount, vatAmount, grandTotal } = computeVatBreakdown(totalAmount);
  const hasTextDetail = order.some((key) => TEXT_DETAIL_KEYS.has(key));

  // 열 폭 합은 반드시 100%여야 한다 — table-fixed라 넘치면 마지막 열("공급가액")의 "원"이
  // 잘리고 가로 스크롤이 생긴다(2026-08-21 사용자 지적, 합이 109%였음).
  // 구분(대)10 + 구분(중)10 + 상품명11 + 상품구성28 + 작업일6 + 수량6 + 단가14 + 공급가액15 = 100
  function detailColumnWidth(key: string): string {
    if (TEXT_DETAIL_KEYS.has(key)) return showCategorySplit ? "28%" : "25%";
    if (!hasTextDetail) {
      if (key === "unit_price") return "20%";
      if (key === "work_days" || key === "quantity") return "10%";
      return "10%";
    }
    if (key === "work_days") return showCategorySplit ? "6%" : "8%";
    if (key === "quantity") return showCategorySplit ? "6%" : "7%";
    if (key === "unit_price") return showCategorySplit ? "14%" : "18%";
    return "9%";
  }

  // 새 행은 앞 항목의 구분(대)을 물려받아 바로 아래에 들어간다. 금액 0원으로 시작해
  // 사용자가 단가를 채우면 그때 계산된다 — 임의의 금액을 넣어두면 그게 또 "마음대로 바뀐 값"이다.
  function handleAddAfter(index: number) {
    const base = items[index];
    const row: LineItem = {
      ...base,
      name: "새 항목",
      description: "",
      work_days: 1,
      quantity: 1,
      unit_price: 0,
      amount: 0,
      note: undefined,
    };
    onSaveLineItems([...items.slice(0, index + 1), row, ...items.slice(index + 1)]);
  }

  // 병합된 구분(대)/구분(중) 칸을 고치면 그 칸이 덮는 행 전부에 같은 값을 넣는다.
  async function handlePatchMany(indexes: number[], patch: LineItemPatch) {
    const target = new Set(indexes);
    onSaveLineItems(items.map((item, i) => (target.has(i) ? { ...item, ...patch } : item)));
  }

  function handleRemoveItem(index: number) {
    onSaveLineItems(items.filter((_, i) => i !== index));
  }

  async function handleEditItem(index: number, patch: LineItemPatch) {
    const merged: LineItem = { ...items[index], ...patch };
    // 단가에 곱해지는 값 — 백엔드 quote_pricing.FormSpec.divisor와 같은 식이어야 한다.
    const divisorOf = (item: LineItem) =>
      (amountUsesWorkDays ? item.work_days ?? 1 : 1) * (amountUsesQuantity ? item.quantity ?? 1 : 1);
    if ("amount" in patch) {
      const d = divisorOf(merged);
      merged.unit_price = d ? merged.amount / d : merged.amount;
    } else if ("unit_price" in patch || "work_days" in patch || "quantity" in patch) {
      merged.amount = Math.round((merged.unit_price ?? 0) * divisorOf(merged));
    }

    const next = items.map((item, i) => (i === index ? merged : item));

    // 재배분 없음 — 고친 항목만 바뀌고 총합계는 그만큼 따라 움직인다.
    // 예전엔 "총합계 유지" 모드가 나머지 항목을 비례 축소·확대했는데, 사용자가 손대지도 않은
    // 금액이 매번 흔들리는 주된 원인이었다(2026-08-21 재설계 — 사용자가 친 값은 절대 재계산하지
    // 않는다). 총액을 맞춰야 하면 사용자가 직접 고치거나 다시 생성한다.
    onSaveLineItems(next);
  }

  return (
    <div>
      <div
        className={
          "overflow-x-auto rounded-lg border border-gray-200 bg-white " +
          (!showCategorySplit && !hasTextDetail ? "w-full max-w-[980px]" : "w-full")
        }
      >
      <table className="w-full min-w-0 table-fixed border-collapse text-[13px]">
        <colgroup>
          {showCategorySplit && (
            <>
              <col style={{ width: "10%" }} />
              <col style={{ width: "10%" }} />
            </>
          )}
          <col style={{ width: showCategorySplit ? "11%" : hasTextDetail ? "15%" : "32%" }} />
          {order.map((key) => <col key={key} style={{ width: detailColumnWidth(key) }} />)}
          <col style={{ width: hasTextDetail ? (showCategorySplit ? "15%" : "27%") : "28%" }} />
          {hasNote && <col style={{ width: "16%" }} />}
        </colgroup>
        <thead>
          <tr className="border-b border-gray-200 bg-gray-100">
            {showCategorySplit && (
              <>
                <th className="break-words px-2.5 py-2 text-left text-xs font-semibold text-gray-600">
                  {columnLabels.category_large ?? "구분(대)"}
                </th>
                <th className="break-words px-2.5 py-2 text-left text-xs font-semibold text-gray-600">
                  {columnLabels.category_mid ?? "구분(중)"}
                </th>
              </>
            )}
            <th className="px-2.5 py-2 text-left text-xs font-semibold text-gray-600">
              {labelFor("item_name")}
            </th>
            {order.map((key) => (
              <th
                key={key}
                className={
                  "px-2.5 py-2 text-xs font-semibold text-gray-600 " +
                  (TEXT_DETAIL_KEYS.has(key) ? "text-left" : "whitespace-nowrap text-right")
                }
              >
                {labelFor(key)}
              </th>
            ))}
            <th className="whitespace-nowrap px-2.5 py-2 text-right text-xs font-semibold text-gray-600">
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
              onPatchMany={handlePatchMany}
              onAddAfter={handleAddAfter}
              onRemoveItem={handleRemoveItem}
            />
          ))}
        </tbody>
        <tfoot className="border-t-2 border-gray-300 bg-gray-50">
          <tr className="border-b border-gray-200">
            <td className="px-3 py-2 text-right text-sm text-gray-500" colSpan={labelColSpan}>
              공급가액 소계
            </td>
            <td className="whitespace-nowrap px-3 py-2 text-right text-sm text-gray-700">
                {supplyAmount.toLocaleString()}원
            </td>
            {hasNote && <td className="px-3 py-2" />}
          </tr>
          <tr className="border-b border-gray-200">
            <td className="px-3 py-2 text-right text-sm text-gray-500" colSpan={labelColSpan}>
              부가세 (10%)
            </td>
            <td className="whitespace-nowrap px-3 py-2 text-right text-sm text-gray-700">
              {vatAmount.toLocaleString()}원
            </td>
            {hasNote && <td className="px-3 py-2" />}
          </tr>
          <tr>
            <td className="px-3 py-2.5 text-right text-sm font-bold text-gray-900" colSpan={labelColSpan}>
              총합계
            </td>
            <td className="whitespace-nowrap px-3 py-2.5 text-right text-base font-bold text-indigo-700">
              {grandTotal.toLocaleString()}원
            </td>
            {hasNote && <td className="px-3 py-2.5" />}
          </tr>
        </tfoot>
      </table>
      </div>
    </div>
  );
}

function QuoteCard({
  quote,
  pending,
  hasComparisons,
  onSaveServiceName,
  onSaveQuoteDate,
  onSaveRecipientInfo,
  onStageLineItems,
  onCommitPending,
  onDiscardPending,
  onRevertToOriginal,
  onRevertToPrevious,
}: {
  quote: EntityQuote;
  pending: PendingEdit | null;
  hasComparisons: boolean;
  onSaveServiceName: (value: string) => Promise<void>;
  onSaveQuoteDate: (value: string) => Promise<void>;
  onSaveRecipientInfo: (input: RecipientInfoInput) => Promise<void>;
  onStageLineItems: (items: LineItem[]) => void;
  onCommitPending: (mode: ComparisonMode) => Promise<void>;
  onDiscardPending: () => void;
  onRevertToOriginal: () => Promise<void>;
  onRevertToPrevious: () => Promise<void>;
}) {
  // 본견적을 고쳤을 때 비교견적을 어떻게 할지는 "무엇을 고쳤는지"를 보면 정해진다.
  // 저장 시점에 사용자에게 세 갈래를 고르게 했더니 매번 판단해야 해서 헷갈린다는
  // 피드백을 받았다(2026-08-21). 고른 결과를 버튼 옆에 문장으로 알려주고, 틀렸다 싶으면
  // 비교견적 패널의 "다시 생성"으로 언제든 덮어쓸 수 있다.
  //   문구(품명·구분·상품구성)를 고쳤다  → regenerate (비교견적 문장도 다시 씀, AI 10~20초)
  //   금액 총액이 달라졌다              → sync      (인상률대로 금액만 따라감, 즉시)
  //   둘 다 아니다(수량↔단가 맞바꾸기 등) → keep      (비교견적은 그대로 두면 맞다)
  const comparisonMode: ComparisonMode = useMemo(() => {
    if (!pending || !quote.is_primary || !hasComparisons) return "keep";
    const saved = quote.line_items;
    const next = pending.items;
    const textChanged =
      next.length !== saved.length ||
      next.some((item, i) => {
        const before = saved[i];
        return (
          !before ||
          item.name !== before.name ||
          item.category !== before.category ||
          (item.description ?? "") !== (before.description ?? "")
        );
      });
    if (textChanged) return "regenerate";
    const sum = (list: LineItem[]) => list.reduce((acc, item) => acc + item.amount, 0);
    return sum(next) === sum(saved) ? "keep" : "sync";
  }, [pending, quote.is_primary, quote.line_items, hasComparisons]);

  const comparisonNote = {
    keep: null,
    sync: "비교견적서 금액도 인상률에 맞춰 함께 반영됩니다.",
    regenerate: "상품 구성이 바뀌어, 비교견적서 문구도 함께 다시 씁니다 (10~20초).",
  }[comparisonMode];

  const contactRequired = RECIPIENT_CONTACT_ENTITIES.includes(quote.entity_name);
  // 수신자·용역명은 선택 입력이라 여기 없다(2026-08-20) — 비워도 발급되고, 나중에 "정보 수정"에서
  // 채우면 그때 PDF에 반영된다.
  const missingRequiredFields = [
    !quote.quote_date && "작성일",
    contactRequired && !quote.recipient_contact && "담당자",
    contactRequired && !quote.recipient_phone && "연락처",
    contactRequired && !quote.recipient_email && "이메일",
  ].filter(Boolean);
  const hasMissingRequired = missingRequiredFields.length > 0;
  const [infoExpanded, setInfoExpanded] = useState(false);
  const [busyAction, setBusyAction] = useState<"commit" | "original" | "previous" | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const displayQuote = pending
    ? { ...quote, line_items: pending.items, total_amount: computeGrandTotal(pending.items) }
    : quote;

  async function runAction(kind: "commit" | "original" | "previous", fn: () => Promise<void>) {
    setBusyAction(kind);
    setActionError(null);
    try {
      await fn();
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : "처리에 실패했습니다.");
    } finally {
      setBusyAction(null);
    }
  }

  return (
    // 내용(왼쪽, 편집)과 뷰어(오른쪽, 실제 양식)를 나란히 둔다 — 이전엔 편집 표 밑에 800px
    // iframe이 이어져서 미리보기를 보려면 한참 스크롤해야 했고, 수정할 때마다 표와 미리보기를
    // 번갈아 스크롤해야 했다. 뷰어는 sticky라 편집 중에도 계속 눈에 보인다.
    <div className="mx-auto grid w-full max-w-[1500px] grid-cols-1 gap-5 min-[1600px]:grid-cols-[minmax(680px,1fr)_440px] min-[1600px]:items-start min-[1900px]:grid-cols-[minmax(720px,1010px)_470px]">
      <div className="overflow-hidden rounded-2xl border border-black/10 bg-white shadow-[0_1px_2px_rgba(0,0,0,0.04)]">
        <div className="border-b border-slate-100 px-6 py-4">
          <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span
                className={
                  quote.is_primary
                    ? "rounded-md bg-slate-900 px-2.5 py-1 text-xs font-semibold text-white"
                    : "rounded-md bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-600"
                }
              >
                {quote.is_primary ? "본견적서" : "비교견적서"}
              </span>
            </div>
            <p className="mt-2 text-xl font-bold tracking-tight text-slate-950">{quote.entity_name}</p>
            <p className="mt-1 text-xs text-slate-500">수정 내용은 저장 후 실제 견적서에 반영됩니다.</p>
          </div>
          <div className="ml-auto text-right">
            <p className="text-xs font-medium text-slate-400">견적 금액{pending && " (미반영 변경 포함)"}</p>
            <p className="mt-1 whitespace-nowrap text-2xl font-bold tracking-tight text-slate-950">
              {displayQuote.total_amount.toLocaleString()}
              <span className="ml-0.5 text-base font-medium text-slate-400">원</span>
            </p>
            {quote.line_items.length > 0 && (
              <div className="mt-2 flex items-center justify-end gap-1.5" aria-label="파일 다운로드">
                {/* target="_blank"이 없으면 이 링크가 현재 탭의 "이동"으로 시작돼서, 미반영 수정이
                    남아 있을 때 beforeunload 핸들러가 걸려 크롬의 "사이트에서 나가시겠습니까?"
                    경고가 뜬다(2026-08-19 사용자 지적) — 실제로는 파일만 내려받고 페이지는 그대로
                    있는데도 뜨는 오해성 경고다. 새 탭으로 시작하면 현재 문서는 이탈 대상이 아니라
                    경고가 뜨지 않고, 첨부파일 응답이라 그 탭은 곧바로 닫힌다. */}
                <a
                  href={getEntityQuotePdfUrl(quote.id)}
                  target="_blank"
                  rel="noopener"
                  title="PDF 다운로드"
                  aria-label="PDF 다운로드"
                  className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 text-xs font-semibold text-slate-600 transition hover:border-slate-300 hover:bg-slate-50 hover:text-slate-950"
                >
                  <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d="M12 3v12m0 0 4-4m-4 4-4-4M5 20h14" />
                  </svg>
                  <span>PDF</span>
                </a>
                <a
                  href={getEntityQuoteXlsxUrl(quote.id)}
                  target="_blank"
                  rel="noopener"
                  title="엑셀 다운로드"
                  aria-label="엑셀 다운로드"
                  className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 text-xs font-semibold text-slate-600 transition hover:border-slate-300 hover:bg-slate-50 hover:text-slate-950"
                >
                  <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d="M12 3v12m0 0 4-4m-4 4-4-4M5 20h14" />
                  </svg>
                  <span>엑셀</span>
                </a>
              </div>
            )}
          </div>
          </div>
        </div>

        <div
          className={
            "border-b px-5 py-3.5 transition-colors " +
            (hasMissingRequired ? "border-amber-200 bg-amber-50/80" : "border-slate-100 bg-slate-50/70")
          }
        >
          <div className={"flex items-center justify-between gap-3 " + (infoExpanded ? "mb-3" : "")}>
            <div>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <h3 className="flex items-center gap-1.5 text-sm font-bold text-slate-900">
                  {hasMissingRequired && (
                    <svg className="h-4 w-4 text-amber-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                      <path d="M12 9v4m0 4h.01" />
                      <path d="M10.3 3.9 2.5 17.5A2 2 0 0 0 4.2 20h15.6a2 2 0 0 0 1.7-2.5L13.7 3.9a2 2 0 0 0-3.4 0Z" />
                    </svg>
                  )}
                  견적서 발급 정보
                </h3>
                {hasMissingRequired && (
                  <span className="rounded-md bg-amber-100 px-2 py-0.5 text-[11px] font-bold text-amber-800">
                    필수 입력 정보 미입력 · {missingRequiredFields.length}개
                  </span>
                )}
                {!infoExpanded && (
                  <p className="text-xs text-slate-500">
                    {quote.quote_date ?? "날짜 미입력"} · {quote.recipient_name || "수신자 미입력"}
                  </p>
                )}
              </div>
              {infoExpanded && (
                <p className={"mt-0.5 text-xs " + (hasMissingRequired ? "font-medium text-amber-700" : "text-slate-500")}>
                  {hasMissingRequired ? "견적서 발급 전 반드시 입력해 주세요." : "입력 후 자동 저장됩니다."}
                </p>
              )}
            </div>
            <button
              type="button"
              onClick={() => setInfoExpanded((value) => !value)}
              className={
                "shrink-0 rounded-lg border px-3 py-1.5 text-xs font-semibold transition " +
                (hasMissingRequired
                  ? "border-amber-600 bg-amber-600 text-white shadow-sm hover:bg-amber-700"
                  : "border-slate-200 bg-white text-slate-600 hover:border-indigo-200 hover:text-indigo-700")
              }
              aria-expanded={infoExpanded}
            >
              {infoExpanded ? "접기" : "정보 수정"}
            </button>
          </div>
          {infoExpanded && (
            <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
              <QuoteDateField quote={quote} onSave={onSaveQuoteDate} />
              {quote.entity_name === TESTIFY_NAME && (
                <ServiceNameField quote={quote} onSave={onSaveServiceName} />
              )}
              <div className={quote.entity_name === TESTIFY_NAME ? "lg:col-span-2" : "lg:col-span-1"}>
                <RecipientInfoFields quote={quote} onSave={onSaveRecipientInfo} />
              </div>
            </div>
          )}
        </div>

        {quote.line_items.length > 0 ? (
          <div className="px-6 py-5">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
              <div>
                <h3 className="text-sm font-bold text-slate-900">견적 항목</h3>
                <p className="mt-0.5 text-xs text-slate-400">항목을 눌러 직접 수정할 수 있습니다.</p>
              </div>
            </div>
            <div className="mb-3 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-100 bg-slate-50/70 px-3.5 py-2">
              <p className="text-xs text-slate-500">
                {pending ? (
                  <span className="inline-flex flex-wrap items-center gap-x-2 gap-y-0.5">
                    <span className="font-semibold text-amber-700">저장되지 않은 변경사항</span>
                    {comparisonNote && <span className="text-slate-500">{comparisonNote}</span>}
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1.5"><span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />저장됨</span>
                )}
              </p>
              <div className="flex items-center gap-2">
                {pending && (
                  <>
                    <button
                      type="button"
                      disabled={busyAction !== null}
                      title="미리보기 변경사항을 버리고 마지막으로 저장된 상태로 돌아갑니다."
                      onClick={onDiscardPending}
                      className="rounded-lg border border-black/10 bg-white px-3 py-1.5 text-xs font-semibold text-slate-600 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      변경 취소
                    </button>
                    <button
                      type="button"
                      disabled={busyAction !== null}
                      title={comparisonNote ?? "미리보기 변경사항을 실제 견적서에 저장합니다."}
                      onClick={() => runAction("commit", () => onCommitPending(comparisonMode))}
                      className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {busyAction === "commit"
                        ? comparisonMode === "regenerate"
                          ? "비교견적서 다시 쓰는 중…"
                          : "반영하는 중…"
                        : "수정 반영하기"}
                    </button>
                  </>
                )}
                <div className="flex items-center overflow-hidden rounded-lg border border-slate-200 bg-white" aria-label="버전 불러오기">
                  <span className="px-2 text-[11px] font-semibold text-slate-400">버전</span>
                  <button
                    type="button"
                    disabled={busyAction !== null}
                    onClick={() => runAction("previous", onRevertToPrevious)}
                    title="이전 저장 버전 불러오기"
                    aria-label="이전 저장 버전 불러오기"
                    className="grid h-8 w-8 place-items-center border-l border-slate-200 text-slate-600 transition hover:bg-slate-50 hover:text-slate-950 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {busyAction === "previous" ? (
                      <span className="text-xs">…</span>
                    ) : (
                      <svg className="h-[18px] w-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                        <path d="M9 14 4 9l5-5" />
                        <path d="M4 9h10a6 6 0 0 1 0 12h-1" />
                      </svg>
                    )}
                  </button>
                  <button
                    type="button"
                    disabled={busyAction !== null}
                    onClick={() => runAction("original", onRevertToOriginal)}
                    title="최초 생성 원본 불러오기"
                    aria-label="최초 생성 원본 불러오기"
                    className="h-8 border-l border-slate-200 px-2.5 text-xs font-semibold text-slate-600 transition hover:bg-slate-50 hover:text-slate-950 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {busyAction === "original" ? "…" : "원본"}
                  </button>
                </div>
              </div>
            </div>
            {actionError && <p className="mb-3 text-xs text-red-600">{actionError}</p>}
            <LineItemTable
              items={displayQuote.line_items}
              columnLabels={quote.column_labels}
              detailColumnOrder={quote.detail_column_order}
              totalAmount={displayQuote.total_amount}
              amountUsesWorkDays={quote.amount_uses_work_days}
              amountUsesQuantity={quote.amount_uses_quantity}
              showCategorySplit={false}
              onSaveLineItems={onStageLineItems}
            />
          </div>
        ) : (
          <p className="px-6 py-8 text-sm text-gray-400">아직 항목이 생성되지 않았습니다.</p>
        )}

      </div>

      {quote.line_items.length > 0 && (
        <div className="hidden min-[1600px]:sticky min-[1600px]:top-6 min-[1600px]:block">
          <QuotePreviewPane quote={quote} />
        </div>
      )}
    </div>
  );
}

function QuotePreviewPane({ quote }: { quote: EntityQuote }) {
  const previewKey = hashKey({
    items: quote.line_items,
    total: quote.total_amount,
    service: quote.service_name,
    date: quote.quote_date,
  });
  const [loadedKey, setLoadedKey] = useState<string | null>(null);
  // 발급이 막힌 경우(비교견적이 본견적보다 싸면 409) iframe이 서버가 준 JSON을 날것으로
  // 보여줬다(2026-08-21 사용자 지적). 먼저 상태를 확인해 사람이 읽을 문장으로 바꾼다.
  //
  // 어느 previewKey에 대한 결과인지 함께 담아둔다 — effect 본문에서 setState로 초기화하면
  // 렌더가 연쇄되어 react-hooks/set-state-in-effect 린트에 걸린다. 키가 바뀌면 저장된 값이
  // 자동으로 무효가 되므로 초기화 자체가 필요 없다.
  const [blockedFor, setBlockedFor] = useState<{ key: string; message: string } | null>(null);
  const blocked = blockedFor?.key === previewKey ? blockedFor.message : null;
  const loading = loadedKey !== previewKey && !blocked;

  useEffect(() => {
    let alive = true;
    fetch(getEntityQuotePdfUrl(quote.id, { inline: true, version: previewKey }))
      .then(async (res) => {
        if (!alive || res.ok) return;
        const body = await res.json().catch(() => null);
        setBlockedFor({ key: previewKey, message: body?.detail ?? "미리보기를 불러오지 못했습니다." });
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [quote.id, previewKey]);

  return (
    <div className="rounded-2xl border border-black/10 bg-white p-3 shadow-[0_1px_2px_rgba(0,0,0,0.04)]">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-bold text-slate-900">{quote.is_primary ? "본견적서" : "비교견적서"} 미리보기</p>
          <p className="mt-0.5 text-xs text-slate-400">실제 발급되는 양식입니다.</p>
        </div>
        {loading && <p className="text-xs text-indigo-500">최신 수정 내용 반영 중…</p>}
      </div>
      <div className="relative aspect-[1/1.4142] max-h-[calc(100vh-8rem)] w-full overflow-hidden rounded-lg border border-gray-200">
        {loading && (
          <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-2 bg-gray-50">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-indigo-200 border-t-indigo-600" />
            <p className="text-xs text-gray-400">실제 양식을 불러오는 중…</p>
          </div>
        )}
        {blocked ? (
          <div className="flex h-full flex-col items-center justify-center gap-3 bg-amber-50 px-6 text-center">
            <span className="grid h-9 w-9 place-items-center rounded-full bg-amber-100 text-amber-700">
              <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <path d="M12 9v4m0 4h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" />
              </svg>
            </span>
            <p className="text-sm font-semibold text-amber-900">아직 발급할 수 없습니다</p>
            <p className="max-w-xs text-xs leading-relaxed text-amber-800">{blocked}</p>
          </div>
        ) : (
        <iframe
          key={previewKey}
          src={`${getEntityQuotePdfUrl(quote.id, { inline: true, version: previewKey })}#toolbar=0&navpanes=0&view=FitH`}
          title={`${quote.entity_name} 견적서 미리보기`}
          className="h-full w-full"
          onLoad={() => {
            setLoadedKey(previewKey);
          }}
        />
        )}
      </div>
    </div>
  );
}

function PersistentEditChat({
  quote,
  messages,
  onSend,
}: {
  quote: EntityQuote;
  messages: ChatMessage[];
  onSend: (text: string, attachment?: ChatAttachment) => Promise<void>;
}) {
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  // 실무자가 쓰던 방식 그대로 — 견적서 파일을 붙여넣고 대화한다. PDF는 Claude가 직접 읽고,
  // xlsx는 서버가 표 텍스트로 펴서 넣는다(2026-08-21).
  const [attachment, setAttachment] = useState<ChatAttachment | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, sending]);

  async function handleSend() {
    if (!input.trim() || sending) return;
    setSending(true);
    setErrorMsg(null);
    const text = input;
    const file = attachment;
    setAttachment(null);
    setInput("");
    try {
      await onSend(text, file ?? undefined);
    } catch (e) {
      setErrorMsg(e instanceof ApiError ? e.message : "수정에 실패했습니다.");
    } finally {
      setSending(false);
    }
  }

  return (
    <aside className="estimate-chat-dock sticky top-20 flex h-[calc(100vh-6rem)] flex-col overflow-hidden rounded-2xl border border-black/10 bg-white shadow-[0_1px_2px_rgba(0,0,0,0.04)] min-[1900px]:top-6 min-[1900px]:h-[calc(100vh-3rem)]">
          <div className="border-b border-slate-100 px-5 py-4">
            <div className="flex items-center gap-2">
              <span className="grid h-8 w-8 place-items-center rounded-lg bg-slate-100 text-slate-700">
                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4Z" />
                </svg>
              </span>
              <div>
                <p className="text-sm font-bold text-slate-900">채팅으로 견적 수정</p>
                <p className="mt-0.5 text-xs text-slate-500">
                  {quote.entity_name} · {quote.is_primary ? "본견적서" : "비교견적서"}
                </p>
              </div>
            </div>
          </div>
          <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
            {messages.length === 0 && (
              <div className="rounded-xl bg-slate-50 p-3.5">
                <p className="text-sm font-semibold text-slate-700">무엇을 바꿀까요?</p>
                <button type="button" onClick={() => setInput("2번 항목 금액을 낮추고 총액은 유지해줘")} className="mt-2.5 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-left text-xs text-slate-600 transition hover:border-indigo-200 hover:text-indigo-700">
                  “2번 항목 금액을 낮추고 총액은 유지해줘”
                </button>
              </div>
            )}
            {messages.map((m, i) => (
              <div key={i} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
                <div
                  className={
                    "max-w-[85%] rounded-2xl px-3 py-2 text-sm " +
                    (m.role === "user" ? "bg-indigo-600 text-white" : "bg-slate-100 text-slate-800")
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
          <div className="border-t border-slate-100 p-4">
            <div className="rounded-xl border border-slate-200 bg-white p-2 transition focus-within:border-indigo-400 focus-within:ring-4 focus-within:ring-indigo-50">
          {attachment && (
            <div className="mx-3 mb-2 flex items-center justify-between gap-2 rounded-lg bg-slate-100 px-2.5 py-1.5 text-xs text-slate-600">
              <span className="truncate">{attachment.filename}</span>
              <button type="button" onClick={() => setAttachment(null)} className="shrink-0 text-slate-400 hover:text-slate-700">
                제거
              </button>
            </div>
          )}
          <label className="mx-3 mb-2 inline-flex w-fit cursor-pointer items-center gap-1.5 rounded-lg border border-black/10 px-2.5 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50">
            <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="m21.4 11.1-9.2 9.2a5 5 0 0 1-7-7l9.2-9.2a3.3 3.3 0 1 1 4.7 4.7l-9.2 9.2a1.7 1.7 0 1 1-2.3-2.3l8.5-8.5" />
            </svg>
            견적서 첨부 (PDF · xlsx)
            <input
              type="file"
              accept=".pdf,.xlsx,.xlsm"
              className="hidden"
              onChange={async (e) => {
                const f = e.target.files?.[0];
                e.target.value = "";
                if (!f) return;
                const buf = await f.arrayBuffer();
                let bin = "";
                new Uint8Array(buf).forEach((b) => (bin += String.fromCharCode(b)));
                setAttachment({ filename: f.name, data: btoa(bin) });
              }}
            />
          </label>
            <textarea
              rows={2}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              placeholder={attachment ? `${attachment.filename} 첨부됨 — 무엇을 할지 적어주세요` : "수정할 내용을 입력하세요"}
              className="w-full resize-none px-2 py-1 text-sm text-slate-900 outline-none placeholder:text-slate-400"
            />
            <div className="flex items-center justify-between gap-2 px-1 pb-0.5">
              <span className="text-[11px] text-slate-400">Enter 전송 · Shift+Enter 줄바꿈</span>
            <button
              type="button"
              disabled={sending || !input.trim()}
              onClick={handleSend}
              aria-label="수정 요청 보내기"
              className="grid h-9 w-9 place-items-center rounded-xl bg-indigo-600 text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:bg-slate-200"
            >
              {sending ? "…" : <span aria-hidden="true">↑</span>}
            </button>
            </div>
            </div>
          </div>
    </aside>
  );
}

const DEFAULT_MARKUP_PERCENT = 10;

type EntitySelection = {
  entityId: string;
  role: "primary" | "comparison";
  // 과업종류(마케팅/시장검증)별 포함 여부 + 체크된 module_name들.
  tasks: Record<FixedTaskType, { included: boolean; moduleNames: string[] }>;
  // 비교견적 마크업(%) — role이 comparison일 때만 쓰인다(2026-08-14 사용자 요청 — 고정 +10%
  // 대신 기업마다 다르게 조절 가능해야 함).
  markupPercent: number;
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

// additive(체크박스) 선택도 대상 기업에 그대로 반영한다 — 라벨(상품명)이 같은 항목을 대상
// 기업 카탈로그에서 찾아 그대로 쓰고, 없으면(그 기업엔 해당 상품이 없음) 그 항목만 건너뛴다.
// 예전엔 additive 그룹 자체를 건너뛰어서(kind !== "variant" 체크) 기준 기업이 체크박스 상품을
// 골라도 나머지 기업엔 하나도 전파되지 않았다 — 시장검증은 전부 additive라 이 과업을 고른
// 비교견적 기업이 전부 "선택한 항목 없음" 상태로 남아 발급이 막히는 원인이었다(2026-08-12).
function additiveModuleNamesMatchingLabels(
  refModuleNames: string[],
  refOptions: CatalogModuleOptions | undefined,
  targetOptions: CatalogModuleOptions | undefined
): string[] {
  const refAdditiveOptions = (refOptions?.groups ?? []).filter((g) => g.kind === "additive").flatMap((g) => g.options);
  const targetAdditiveOptions = (targetOptions?.groups ?? []).filter((g) => g.kind === "additive").flatMap((g) => g.options);
  const names: string[] = [];
  for (const option of refAdditiveOptions) {
    const checked = option.module_names.every((m) => refModuleNames.includes(m));
    if (!checked) continue;
    const match = targetAdditiveOptions.find((o) => o.label === option.label);
    if (match) names.push(...match.module_names);
  }
  return names;
}

export default function EstimateWizard({ initialEstimateSetId }: { initialEstimateSetId?: string } = {}) {
  const setGeneratedEstimateLayout = useGeneratedEstimateLayout();
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

  const [viewedQuoteId, setViewedQuoteId] = useState<string | null>(null);
  const [chatHistory, setChatHistory] = useState<Record<string, ChatMessage[]>>({});
  // 직접편집·채팅 수정 모두 여기 쌓였다가 "수정 반영하기"를 눌러야 실제 저장된다(2026-08-14).
  const [pendingByQuote, setPendingByQuote] = useState<Record<string, PendingEdit>>({});
  const pendingByQuoteRef = useRef(pendingByQuote);
  pendingByQuoteRef.current = pendingByQuote;
  // 비교견적을 다시 써야 하는 상태 — 본견적 항목이 추가·삭제돼 1:1 대응이 깨졌을 때
  // 백엔드가 알려준다. 금액만 바뀐 경우는 서버가 이미 자동 반영했으므로 여기 안 담긴다.
  const [needsRegeneration, setNeedsRegeneration] = useState<string[]>([]);
  const [regenerating, setRegenerating] = useState(false);
  // 인상률 입력칸의 임시값(비교견적 id -> "15"). 저장은 다시 생성 시점에 한 번에 한다.
  const [markupDraft, setMarkupDraft] = useState<Record<string, string>>({});

  const [moduleOptions, setModuleOptions] = useState<EntityModuleOptions[]>([]);
  const [moduleSelections, setModuleSelections] = useState<Record<string, string[]>>({});

  // "수정 반영하기"를 안 눌러도 저장이 되게 하는 안전망. 견적서 탭을 바꾸거나(SPA 내 이탈)
  // 이 화면 자체를 벗어나면(라우트 이동) 그 시점까지의 pending을 자동으로 커밋한다. 브라우저
  // 탭을 완전히 닫는 경우엔 비동기 저장 요청이 끝난다는 보장이 없어 대신 이탈을 막는 확인창을 띄운다.
  useEffect(() => {
    return () => {
      if (viewedQuoteId && pendingByQuoteRef.current[viewedQuoteId]) {
        handleCommitPending(viewedQuoteId);
      }
    };
     
  }, [viewedQuoteId]);

  useEffect(() => {
    return () => {
      Object.keys(pendingByQuoteRef.current).forEach((quoteId) => handleCommitPending(quoteId));
    };
     
  }, []);

  useEffect(() => {
    function handleBeforeUnload(e: BeforeUnloadEvent) {
      if (Object.keys(pendingByQuoteRef.current).length === 0) return;
      e.preventDefault();
      e.returnValue = "";
    }
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, []);

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

  useEffect(() => {
    setGeneratedEstimateLayout(Boolean(result));
    return () => setGeneratedEstimateLayout(false);
  }, [result, setGeneratedEstimateLayout]);

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
      const variantNames = moduleNamesMatchingLabels(referenceLabels, targetOptions);
      const additiveNames = additiveModuleNamesMatchingLabels(refTask.moduleNames, refOptions, targetOptions);
      nextTasks[taskType] = { included: true, moduleNames: [...variantNames, ...additiveNames] };
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
    // 비교견적서는 개수 제한 없음(2026-08-12 사용자 결정) — 본견적 1곳만 setRole에서 별도로 막는다.
    setEntitySelections((prev) => {
      if (prev.some((s) => s.entityId === entityId)) return prev.filter((s) => s.entityId !== entityId);
      return [...prev, { entityId, role: "comparison" as const, tasks: emptyTasks(), markupPercent: DEFAULT_MARKUP_PERCENT }];
    });
  }

  function setRole(entityId: string, role: "primary" | "comparison") {
    setEntitySelections((prev) => {
      return prev.map((s) => {
        if (s.entityId === entityId) return { ...s, role };
        if (role === "primary" && s.role === "primary") return { ...s, role: "comparison" as const };
        return s;
      });
    });
  }

  function setMarkupPercent(entityId: string, percent: number) {
    setEntitySelections((prev) => prev.map((s) => (s.entityId === entityId ? { ...s, markupPercent: percent } : s)));
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
    allEntitiesHaveTask &&
    projectName.trim().length > 0 &&
    Number(totalAmount) > 0 &&
    !submitting;

  async function handleSubmit() {
    setSubmitting(true);
    setError(null);
    try {
      const created = await createEstimateSet({
        project_name: projectName,
        recipient_name: recipientName || undefined,
        recipient_contact: recipientContact || undefined,
        recipient_phone: recipientPhone || undefined,
        recipient_email: recipientEmail || undefined,
        total_amount: Number(totalAmount),
        vat_included: vatIncluded,
        entities: entitySelections.map((s) => ({
          entity_id: s.entityId,
          is_primary: s.role === "primary",
          task_types: FIXED_TASK_TYPES.filter((t) => effectiveTasks(s)[t].included),
          markup_ratio: s.role === "comparison" ? s.markupPercent / 100 : undefined,
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
    setViewedQuoteId(null);
    setChatHistory({});
    setPendingByQuote({});
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

  async function handleSaveQuoteDate(quoteId: string, value: string) {
    const updated = await updateQuoteDate(quoteId, value);
    handleQuoteEdited(updated);
  }

  async function handleSaveRecipientInfo(quoteId: string, input: RecipientInfoInput) {
    const updated = await updateRecipientInfo(quoteId, input);
    handleQuoteEdited(updated);
  }

  // 직접편집(표 셀 수정)이 호출한다 — 아직 저장하지 않고 화면 미리보기(pending)만 갱신한다.
  function handleStageLineItems(quoteId: string, items: LineItem[]) {
    setPendingByQuote((prev) => ({ ...prev, [quoteId]: { items, editRequestText: "직접편집" } }));
  }

  // "수정 반영하기" — pending을 실제로 저장한다. 직접편집이든 채팅 수정이든 같은 경로로 커밋된다.
  async function handleCommitPending(quoteId: string, mode: ComparisonMode = "sync") {
    const pending = pendingByQuoteRef.current[quoteId];
    if (!pending) return;
    const { entity_quote, synced_comparison_quotes, comparisons_need_regeneration } =
      await updateLineItems(quoteId, pending.items, pending.editRequestText, mode);
    setNeedsRegeneration(comparisons_need_regeneration);
    setPendingByQuote((prev) => {
      const next = { ...prev };
      delete next[quoteId];
      return next;
    });
    // 본견적 금액을 바꾸면 비교견적 금액도 서버가 즉시 맞춰 응답에 실어 보낸다(AI 호출 없음,
    // 2026-08-21) — 세트 전체를 다시 조회하지 않고 그 값으로 바로 병합한다. setResult는 함수형
    // 업데이트라 항상 최신 상태 기준으로 병합되므로, 화면 이탈 시 자동 flush(useEffect
    // cleanup)에서 호출돼도 안전하다.
    const updatedById = new Map([entity_quote, ...synced_comparison_quotes].map((q) => [q.id, q]));
    setResult((prev) =>
      prev
        ? { ...prev, entity_quotes: prev.entity_quotes.map((q) => updatedById.get(q.id) ?? q) }
        : prev
    );
  }

  // "비교견적 생성/다시 생성" — 확정된 본견적을 기준으로 AI가 항목을 다시 쓴다(10~20초).
  // 인상률을 고쳐뒀으면 먼저 저장한 뒤 그 비율로 생성한다.
  async function handleRegenerateComparisons() {
    if (!result) return;
    setRegenerating(true);
    setError(null);
    try {
      const edits = Object.entries(markupDraft);
      for (const [quoteId, raw] of edits) {
        const percent = Number(raw);
        if (Number.isFinite(percent) && percent > 0) {
          await updateMarkupRatio(quoteId, 1 + percent / 100);
        }
      }
      setMarkupDraft({});
      setResult(await regenerateComparisons(result.id));
      setNeedsRegeneration([]);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "비교견적 생성에 실패했습니다.");
    } finally {
      setRegenerating(false);
    }
  }

  // "되돌아가기" — pending을 버리고 마지막으로 저장된 상태로 화면을 되돌린다.
  function handleDiscardPending(quoteId: string) {
    setPendingByQuote((prev) => {
      const next = { ...prev };
      delete next[quoteId];
      return next;
    });
  }

  // "원본으로 되돌리기"/"뒤로 가기" — 과거 버전의 항목들을 pending에 올려 미리 보여준다. 여기서도
  // 바로 저장하지 않고 "수정 반영하기"를 눌러야 커밋된다(되돌리기도 직접편집과 같은 경로 공유).
  async function handleRevertToVersion(quoteId: string, which: "original" | "previous") {
    const versions = await fetchQuoteVersions(quoteId);
    if (versions.length === 0) return;
    const target = which === "original" ? versions[0] : versions[Math.max(0, versions.length - 2)];
    setPendingByQuote((prev) => ({
      ...prev,
      [quoteId]: {
        items: target.line_items as LineItem[],
        editRequestText: which === "original" ? "원본으로 되돌리기" : "이전 버전으로 되돌리기",
      },
    }));
  }

  async function handleSendEdit(quoteId: string, text: string, attachment?: ChatAttachment) {
    setChatHistory((prev) => ({
      ...prev,
      [quoteId]: [...(prev[quoteId] ?? []), { role: "user", text }],
    }));

    // 채팅 수정도 미리보기 전용(edit_service)이라 여기서 바로 저장되지 않는다 — 직접편집과 같은
    // pending 상태에 얹어서, 화면에서 확인 후 "수정 반영하기"를 눌러야 실제로 커밋된다.
    const editResult = await editEntityQuote(quoteId, text, attachment);
    setPendingByQuote((prev) => ({
      ...prev,
      [quoteId]: { items: editResult.entity_quote.line_items as LineItem[], editRequestText: text },
    }));

    // 모델이 사람에게 하는 답을 그대로 띄운다 — 예전엔 "요청하신 내용을 반영했습니다."
    // 고정 문구라 대화가 아니라 폼 제출 같았다(2026-08-21 채팅 리뉴얼).
    const changedLines = editResult.changed_items
      .map((i) => `• ${i.name} → ${i.amount.toLocaleString()}원`)
      .join("\n");
    const summary = [editResult.reply, changedLines].filter(Boolean).join("\n\n");

    setChatHistory((prev) => ({
      ...prev,
      [quoteId]: [...(prev[quoteId] ?? []), { role: "assistant", text: summary, scope: editResult.scope }],
    }));
  }

  if (initialLoading) {
    return <p className="p-8 text-center text-base text-gray-400">불러오는 중…</p>;
  }

  if (result) {
    const hasItems = result.entity_quotes.some((q) => q.line_items.length > 0);
    const primaryQuote = result.entity_quotes.find((q) => q.is_primary) ?? null;
    const comparisonQuotes = result.entity_quotes.filter((q) => !q.is_primary);
    const viewedQuote =
      result.entity_quotes.find((q) => q.id === viewedQuoteId) ?? primaryQuote ?? comparisonQuotes[0] ?? null;
    const modulesToChoose = moduleOptions.filter((o) => o.has_modules);
    const isAutoGenerating = !ENABLE_MODULE_SELECTION_UI && submitting;
    const displayQuotes = [...result.entity_quotes].sort(
      (a, b) => Number(b.is_primary) - Number(a.is_primary)
    );

    return (
      <div
        className={
          viewedQuote && hasItems
            ? "mx-auto grid w-full max-w-[1860px] grid-cols-1 gap-5 xl:grid-cols-[340px_minmax(0,1fr)] xl:items-start"
            : ""
        }
      >
        {viewedQuote && hasItems && (
          <PersistentEditChat
            key={viewedQuote.id}
            quote={viewedQuote}
            messages={chatHistory[viewedQuote.id] ?? []}
            onSend={(text, attachment) => handleSendEdit(viewedQuote.id, text, attachment)}
          />
        )}
        <div className="mx-auto w-full max-w-[1500px] min-w-0 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-black/10 bg-white px-5 py-4 shadow-[0_1px_2px_rgba(0,0,0,0.04)]">
          <div className="min-w-0">
            <p className="text-[11px] font-semibold text-emerald-700">견적 세트 생성 완료</p>
            <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
              <h2 className="truncate text-xl font-bold tracking-tight text-slate-950">{result.project_name}</h2>
              <span className="text-xs text-slate-500">{result.task_type} · {result.total_amount.toLocaleString()}원 · VAT {result.vat_included ? "포함" : "별도"}</span>
            </div>
          </div>
          <button
            onClick={handleReset}
            title="지금 만든 견적은 그대로 두고, 처음 화면으로 돌아가 다른 견적을 새로 만듭니다."
            className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-black/10 bg-slate-50 text-lg text-slate-600 transition hover:bg-slate-100"
            aria-label="다른 견적 새로 만들기"
          >
            <span aria-hidden="true">＋</span>
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
          <div className="space-y-4">
            {result.entity_quotes.length > 1 && (
              <div className="flex items-center gap-2 overflow-x-auto border-b border-slate-200 pb-3 [scrollbar-width:none]">
                <span className="shrink-0 text-xs font-semibold text-slate-400">견적서 {displayQuotes.length}개</span>
                {displayQuotes.map((q) => {
                  const selected = (viewedQuote?.id ?? primaryQuote?.id) === q.id;
                  // 아직 생성 안 된 비교견적(총액 0)은 -100%로 표시되어 오해를 샀다
                  // (2026-08-21 사용자 지적) — 항목이 생긴 뒤에만 증감률을 보여준다.
                  const diffPercent =
                    !q.is_primary && q.line_items.length > 0 && primaryQuote && primaryQuote.total_amount > 0
                      ? ((q.total_amount - primaryQuote.total_amount) / primaryQuote.total_amount) * 100
                      : null;
                  return (
                    <button
                      key={q.id}
                      type="button"
                      onClick={() => setViewedQuoteId(q.id)}
                      aria-pressed={selected}
                      className={
                        "inline-flex shrink-0 items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm font-medium transition " +
                        (selected
                          ? "border-slate-900 bg-slate-900 text-white"
                          : "border-black/10 bg-white text-slate-700 hover:bg-slate-50")
                      }
                    >
                      {selected && (
                        <svg className="h-3.5 w-3.5 shrink-0" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                          <path d="m3 8 3 3 7-7" />
                        </svg>
                      )}
                      <span>{q.entity_name}</span>
                      <span
                        className={
                          "rounded-full px-2 py-0.5 text-[10px] font-bold " +
                          (q.is_primary
                            ? selected
                              ? "bg-blue-500/25 text-blue-100"
                              : "bg-blue-50 text-blue-700"
                            : selected
                              ? "bg-white/10 text-white"
                              : "bg-slate-100 text-slate-500")
                        }
                      >
                        {q.is_primary ? "본견적" : "비교견적"}
                      </span>
                      {q.total_amount > 0 && (
                        <span className={"text-xs " + (selected ? "text-slate-300" : "text-slate-400")}>
                          · {q.total_amount.toLocaleString()}원
                        </span>
                      )}
                      {diffPercent !== null && (
                        <span
                          className={
                            "text-[11px] font-semibold " +
                            (selected
                              ? diffPercent > 0
                                ? "text-rose-200"
                                : diffPercent < 0
                                  ? "text-sky-200"
                                  : "text-slate-300"
                              : diffPercent > 0
                                ? "text-rose-600"
                                : diffPercent < 0
                                  ? "text-sky-600"
                                  : "text-slate-400")
                          }
                        >
                          {diffPercent > 0 ? "+" : ""}{diffPercent.toFixed(1)}%
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>
            )}

            {primaryQuote && primaryQuote.line_items.length > 0 && comparisonQuotes.length > 0 && (() => {
              // 순차 흐름(2026-08-21): 본견적을 검토·수정한 뒤 여기서 비교견적을 만든다.
              // 아직 안 만들었거나, 본견적 항목이 바뀌어 다시 써야 하는 상태면 눈에 띄게 띄운다.
              const notYet = comparisonQuotes.every((q) => q.line_items.length === 0);
              const stale = needsRegeneration.length > 0;
              const highlight = notYet || stale;
              return (
                <div
                  className={
                    "rounded-2xl border p-4 " +
                    (highlight ? "border-amber-300 bg-amber-50" : "border-black/10 bg-white")
                  }
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="text-sm font-bold text-slate-900">
                        {notYet
                          ? "2단계 — 비교견적서 생성"
                          : stale
                            ? "본견적 항목이 바뀌었습니다"
                            : "비교견적서"}
                      </p>
                      <p className="mt-0.5 text-xs text-slate-500">
                        {notYet
                          ? "본견적서를 검토·수정한 뒤 생성하세요. 확정된 본견적을 기준으로 같은 과업을 다른 표현·다른 금액으로 다시 씁니다."
                          : stale
                            ? "항목이 추가·삭제되어 비교견적과 1:1로 대응하지 않습니다. 다시 생성해야 발급할 수 있습니다."
                            : "금액만 바뀐 경우는 자동으로 반영됩니다. 항목 문장까지 다시 쓰려면 아래에서 생성하세요."}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={handleRegenerateComparisons}
                      disabled={regenerating}
                      className={
                        "shrink-0 rounded-lg px-4 py-2 text-sm font-semibold text-white transition disabled:opacity-50 " +
                        (highlight ? "bg-amber-600 hover:bg-amber-700" : "bg-slate-900 hover:bg-slate-800")
                      }
                    >
                      {regenerating ? "생성 중… (10~20초)" : notYet ? "비교견적서 생성" : "비교견적서 다시 생성"}
                    </button>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2 border-t border-black/5 pt-3">
                    {comparisonQuotes.map((q) => {
                      const current = Math.round(((q.markup_ratio ?? 1.1) - 1) * 100);
                      return (
                        <label
                          key={q.id}
                          className="inline-flex items-center gap-1.5 rounded-lg border border-black/10 bg-white px-2.5 py-1.5 text-xs"
                        >
                          <span className="font-medium text-slate-700">{q.entity_name}</span>
                          <span className="text-slate-400">+</span>
                          <input
                            type="number"
                            min={1}
                            max={200}
                            value={markupDraft[q.id] ?? String(current)}
                            onChange={(e) =>
                              setMarkupDraft((prev) => ({ ...prev, [q.id]: e.target.value }))
                            }
                            className="w-14 rounded border border-black/10 px-1.5 py-0.5 text-right tabular-nums outline-none focus:border-slate-900"
                          />
                          <span className="text-slate-400">%</span>
                          {needsRegeneration.includes(q.id) && (
                            <span className="rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-bold text-amber-700">
                              재생성 필요
                            </span>
                          )}
                        </label>
                      );
                    })}
                  </div>
                </div>
              );
            })()}

            {viewedQuote && (
              <QuoteCard
                key={viewedQuote.id}
                quote={viewedQuote}
                pending={pendingByQuote[viewedQuote.id] ?? null}
                hasComparisons={comparisonQuotes.length > 0}
                onSaveServiceName={(value) => handleSaveServiceName(viewedQuote.id, value)}
                onSaveQuoteDate={(value) => handleSaveQuoteDate(viewedQuote.id, value)}
                onSaveRecipientInfo={(input) => handleSaveRecipientInfo(viewedQuote.id, input)}
                onStageLineItems={(items) => handleStageLineItems(viewedQuote.id, items)}
                onCommitPending={(mode) => handleCommitPending(viewedQuote.id, mode)}
                onDiscardPending={() => handleDiscardPending(viewedQuote.id)}
                onRevertToOriginal={() => handleRevertToVersion(viewedQuote.id, "original")}
                onRevertToPrevious={() => handleRevertToVersion(viewedQuote.id, "previous")}
              />
            )}
          </div>
        )}

        </div>
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
        <StepHeader n={1} title="기업 선택" hint="다중 선택 (본견적 1곳 + 비교견적 무제한)" />
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
          <StepHeader n={2} title="본견적/비교견적 지정" hint="본견적 최대 1곳, 비교견적 무제한" />
          <div className="mt-3 divide-y divide-gray-100 overflow-hidden rounded-xl border border-gray-200">
            {entitySelections.map((s) => (
              <div key={s.entityId} className="flex flex-wrap items-center justify-between gap-3 bg-white px-4 py-3">
                <span className="text-base font-semibold text-gray-900">{entityLabel(s.entityId)}</span>
                <div className="flex items-center gap-2">
                  {s.role === "comparison" && (
                    <label className="flex items-center gap-1 text-sm text-gray-500">
                      <span>마크업</span>
                      <input
                        type="number"
                        step="1"
                        value={s.markupPercent}
                        onChange={(e) => {
                          const raw = e.target.value.replace(/^0+(?=\d)/, "");
                          e.target.value = raw;
                          setMarkupPercent(s.entityId, raw === "" ? 0 : Number(raw));
                        }}
                        onClick={(e) => e.stopPropagation()}
                        className="w-14 rounded-md border border-gray-200 px-1.5 py-1 text-right text-sm"
                      />
                      <span>%</span>
                    </label>
                  )}
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
                        {role === "primary" ? "본견적" : "비교견적"}
                      </button>
                    ))}
                  </div>
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
            {!allEntitiesHaveTask && (
              <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-700">
                마케팅 또는 시장검증 중 한 곳에서 세부 항목을 하나 이상 골라야 견적서를 만들 수 있습니다.
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
            <label className="block text-sm text-gray-500">
              사업명 <span className="text-red-500">*</span>
            </label>
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
              수신자(고객사명){" "}
              <span className="text-gray-400">(선택 — 견적서에 &quot;OOO 귀하&quot;로 표시, 발급 전까지 화면에서 입력 가능)</span>
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
              <label className="block text-sm text-gray-500">
                총액 (원) <span className="text-red-500">*</span>
              </label>
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
          {/* 용역명은 예전 테스티파이 양식(B12)에만 있던 칸이다 — 신양식에는 그 칸이 없어
              더 이상 필수가 아니지만, 입력해 두면 이력에 남으므로 선택 입력으로 남긴다. */}
          {primaryIsTestify && (
            <div>
              <label className="block text-sm text-gray-500">
                용역명 <span className="text-slate-400">(선택)</span>
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
