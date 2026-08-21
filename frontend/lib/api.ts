const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8001";

export type EntityOption = {
  id: string;
  name: string;
};

export type LineItem = {
  category: string;
  name: string;
  amount: number;
  unit_price?: number;
  work_days?: number;
  quantity?: number;
  note?: string;
  // 과업종류를 교차 선택한 견적서에서 이 항목이 어느 과업종류 소속인지 — 직접편집 저장 시
  // 그대로 되돌려 보내야 발급 시 단가 계산이 올바른 법인 카탈로그를 참조한다.
  task_type?: string;
  // 알파브라더스처럼 상품구성을 별도 칸(상품구성/상세내용)에 세로로 나열하는 양식용.
  description?: string;
  // 구분(중) — 구분(대)(category)와 상품명(name) 사이의 중간 분류. 이 칸이 있는 양식
  // (테스티파이 신양식·알파브라더스)에서만 표시된다(2026-08-19).
  mid_category?: string;
  // 썬데이워커 전용 — 투입 MM(작업일×수량÷20 근사치, PRD 7.4)과 항목별 세액(공급가액×10%).
  input_mm?: number;
  tax_amount?: number;
  // 채팅에서 사용자가 금액·단가를 콕 집어 지정한 항목. 저장 시 그대로 되돌려 보내야 다음
  // 수정 때 그 금액이 10만원 단위로 다시 밀리지 않는다(2026-08-20).
};

export type EntityQuote = {
  id: string;
  entity_id: string;
  entity_name: string;
  is_primary: boolean;
  task_type: string;
  task_types: string[];
  total_amount: number;
  line_items: LineItem[];
  is_catalog_borrowed: boolean;
  catalog_source_entity_name: string | null;
  service_name: string | null;
  quote_date: string | null;
  recipient_name: string | null;
  recipient_contact: string | null;
  recipient_phone: string | null;
  recipient_email: string | null;
  // 법인마다 실제 원본 양식의 컬럼 명칭·순서가 다르다(예: 작업일/소요일, 수량/작업수량) —
  // 백엔드가 각 법인의 실제 템플릿에서 그대로 계산해 내려준다(2026-07-10).
  column_labels: Record<string, string>;
  detail_column_order: string[];
  // 알파브라더스처럼 항목 블록마다 구분(대)/구분(중)이 있는 양식인지 (item.task_type로 채움)
  show_category_split: boolean;
  /** 이 양식의 공급가액 수식이 작업일/수량을 곱하는가. 화면 편집이 발급본과 같은 식을 쓴다. */
  amount_uses_work_days: boolean;
  amount_uses_quantity: boolean;
  // 금액 후처리가 무엇을 움직였는지 한 문장. "안 건드린 항목이 왜 바뀌었나"를 사용자가
  // 화면에서 바로 추적할 수 있어야 한다(2026-08-21).
  adjustment_note: string | null;
  // 비교견적의 인상률(1.10 = +10%). 화면에서 %를 고쳐 다시 생성할 때 쓴다.
  markup_ratio: number | null;
};

export type ModuleItemGroup = {
  module_name: string;
  item_names: string[];
};

export type ModuleOption = {
  option_key: string;
  label: string;
  module_names: string[];
  item_count: number;
  is_default: boolean;
  item_groups: ModuleItemGroup[];
};

export type ModuleGroup = {
  kind: "variant" | "additive";
  options: ModuleOption[];
  label?: string | null;
};

export type EntityModuleOptions = {
  entity_quote_id: string;
  entity_name: string;
  has_modules: boolean;
  groups: ModuleGroup[];
};

export type EstimateSet = {
  id: string;
  project_name: string;
  total_amount: number;
  vat_included: boolean;
  task_type: string;
  primary_entity_id: string | null;
  entity_quotes: EntityQuote[];
};

export type EstimateSetSummary = {
  id: string;
  project_name: string;
  total_amount: number;
  vat_included: boolean;
  task_type: string;
  created_at: string;
  quote_count: number;
  entity_names: string[];
};

export function getEntityQuotePdfUrl(
  entityQuoteId: string,
  options?: { inline?: boolean; version?: string }
): string {
  // version은 견적 내용 해시다. 내용이 그대로면 URL도 그대로라 브라우저 캐시에 걸려 서버를
  // 다시 때리지 않는다 — LibreOffice 변환이 1건에 3초 넘게 걸리고 전역 락이라, 탭을 옮길
  // 때마다 재요청하면 그 뒤에 선 다른 요청(비교견적 생성 등)이 통째로 굶었다(2026-08-21 실측).
  const params = new URLSearchParams();
  if (options?.inline) params.set("inline", "1");
  if (options?.version) params.set("v", options.version);
  const query = params.toString();
  return `${API_BASE_URL}/api/entity-quotes/${entityQuoteId}/pdf${query ? `?${query}` : ""}`;
}

export function getEntityQuoteXlsxUrl(entityQuoteId: string): string {
  return `${API_BASE_URL}/api/entity-quotes/${entityQuoteId}/xlsx`;
}

export class ApiError extends Error {}

// FastAPI 검증 에러(422)의 detail은 문자열이 아니라 {msg, loc, ...} 객체 배열로 온다 —
// 그대로 Error 메시지로 넘기면 "[object Object]"로 깨져서 그 형태도 처리해야 한다.
function detailToMessage(detail: unknown, status: number): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const msgs = detail.map((d) => (d && typeof d === "object" && "msg" in d ? String(d.msg) : String(d)));
    if (msgs.length > 0) return msgs.join(", ");
  }
  return `요청 실패 (${status})`;
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(detailToMessage(body?.detail, res.status));
  }
  return res.json();
}

export async function fetchTaskTypes(): Promise<string[]> {
  const res = await fetch(`${API_BASE_URL}/api/task-types`);
  return handle<string[]>(res);
}

export async function fetchEstimateSets(): Promise<EstimateSetSummary[]> {
  const res = await fetch(`${API_BASE_URL}/api/estimate-sets`, { cache: "no-store" });
  return handle<EstimateSetSummary[]>(res);
}

export async function deleteEstimateSet(id: string): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/estimate-sets/${id}`, { method: "DELETE" });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(detailToMessage(body?.detail, res.status));
  }
}

export async function fetchEntities(taskType: string): Promise<EntityOption[]> {
  const res = await fetch(
    `${API_BASE_URL}/api/entities?task_type=${encodeURIComponent(taskType)}`
  );
  return handle<EntityOption[]>(res);
}

export type EntitySelectionInput = {
  entity_id: string;
  is_primary: boolean;
  task_types: string[];
  // 비교견적 마크업 배율(예: 0.10 = +10%) — primary는 무시된다. 없으면 백엔드 기본값(+10%)을 쓴다.
  markup_ratio?: number;
};

export type CreateEstimateSetInput = {
  project_name: string;
  recipient_name?: string;
  recipient_contact?: string;
  recipient_phone?: string;
  recipient_email?: string;
  total_amount: number;
  vat_included: boolean;
  entities: EntitySelectionInput[];
  service_name?: string;
};

export async function createEstimateSet(
  input: CreateEstimateSetInput
): Promise<EstimateSet> {
  const res = await fetch(`${API_BASE_URL}/api/estimate-sets`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return handle<EstimateSet>(res);
}

export async function fetchEstimateSet(id: string): Promise<EstimateSet> {
  const res = await fetch(`${API_BASE_URL}/api/estimate-sets/${id}`, { cache: "no-store" });
  return handle<EstimateSet>(res);
}

export async function fetchModuleOptions(estimateSetId: string): Promise<EntityModuleOptions[]> {
  const res = await fetch(`${API_BASE_URL}/api/estimate-sets/${estimateSetId}/module-options`);
  return handle<EntityModuleOptions[]>(res);
}

export type CatalogModuleOptions = {
  has_modules: boolean;
  groups: ModuleGroup[];
};

// 견적 세트를 만들기 전(마법사의 기업/과업 선택 단계)에 기업×과업종류만으로 모듈 체크박스를
// 미리 보여줄 때 쓴다 — fetchModuleOptions는 entity_quote가 이미 있어야 하므로 대신 이걸 쓴다.
export async function fetchCatalogModuleOptions(
  entityId: string,
  taskType: string
): Promise<CatalogModuleOptions> {
  const res = await fetch(
    `${API_BASE_URL}/api/catalog/module-options?entity_id=${encodeURIComponent(entityId)}&task_type=${encodeURIComponent(taskType)}`
  );
  return handle<CatalogModuleOptions>(res);
}

export async function generateEstimateSet(
  id: string,
  selections: Record<string, string[]>
): Promise<EstimateSet> {
  const res = await fetch(`${API_BASE_URL}/api/estimate-sets/${id}/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ selections }),
  });
  return handle<EstimateSet>(res);
}

export type LineItemsUpdateResult = {
  entity_quote: EntityQuote;
  // 본견적 금액을 바꾸면 비교견적 금액도 서버에서 즉시 따라온다(AI 호출 없음) — 세트 전체를
  // 다시 조회하지 않고 이 값으로 화면을 바로 갱신한다(2026-08-17).
  synced_comparison_quotes: EntityQuote[];
  // 본견적 항목이 추가·삭제돼 1:1 대응이 깨진 비교견적 id들. 금액만으로는 못 맞추므로
  // 사용자에게 "비교견적 다시 생성"을 안내한다(2026-08-21).
  comparisons_need_regeneration: string[];
};

/** 본견적 수정을 저장할 때 비교견적을 어떻게 할지. keep=그대로 / sync=금액만 즉시 반영 / regenerate=문장까지 다시 쓰기(AI) */
export type ComparisonMode = "keep" | "sync" | "regenerate";

export async function updateLineItems(
  entityQuoteId: string,
  items: LineItem[],
  editRequestText?: string,
  comparisonMode: ComparisonMode = "sync"
): Promise<LineItemsUpdateResult> {
  const res = await fetch(`${API_BASE_URL}/api/entity-quotes/${entityQuoteId}/line-items`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ items, edit_request_text: editRequestText ?? null, comparison_mode: comparisonMode }),
  });
  return handle<LineItemsUpdateResult>(res);
}

/** 확정된 본견적을 기준으로 비교견적을 (다시) 생성한다. AI 호출이라 10~20초 걸린다. */
export async function regenerateComparisons(id: string): Promise<EstimateSet> {
  const res = await fetch(`${API_BASE_URL}/api/estimate-sets/${id}/regenerate-comparisons`, {
    method: "POST",
  });
  return handle<EstimateSet>(res);
}

/** 비교견적의 인상률(%)만 바꾼다. 저장 후 regenerateComparisons를 부르면 그 비율로 다시 쓴다. */
export async function updateMarkupRatio(
  entityQuoteId: string,
  markupRatio: number
): Promise<EntityQuote> {
  const res = await fetch(`${API_BASE_URL}/api/entity-quotes/${entityQuoteId}/markup-ratio`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ markup_ratio: markupRatio }),
  });
  return handle<EntityQuote>(res);
}

export type QuoteVersion = {
  version_no: number;
  edit_request_text: string | null;
  edited_at: string;
  line_items: LineItem[];
};

export async function fetchQuoteVersions(entityQuoteId: string): Promise<QuoteVersion[]> {
  const res = await fetch(`${API_BASE_URL}/api/entity-quotes/${entityQuoteId}/versions`, { cache: "no-store" });
  return handle<QuoteVersion[]>(res);
}

export async function updateServiceName(
  entityQuoteId: string,
  serviceName: string
): Promise<EntityQuote> {
  const res = await fetch(`${API_BASE_URL}/api/entity-quotes/${entityQuoteId}/service-name`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ service_name: serviceName }),
  });
  return handle<EntityQuote>(res);
}

export async function updateQuoteDate(
  entityQuoteId: string,
  quoteDate: string
): Promise<EntityQuote> {
  const res = await fetch(`${API_BASE_URL}/api/entity-quotes/${entityQuoteId}/quote-date`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ quote_date: quoteDate }),
  });
  return handle<EntityQuote>(res);
}

export type RecipientInfoInput = {
  recipient_name?: string;
  recipient_contact?: string;
  recipient_phone?: string;
  recipient_email?: string;
};

export async function updateRecipientInfo(
  entityQuoteId: string,
  input: RecipientInfoInput
): Promise<EntityQuote> {
  const res = await fetch(`${API_BASE_URL}/api/entity-quotes/${entityQuoteId}/recipient-info`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return handle<EntityQuote>(res);
}

/** 채팅에 붙이는 파일. PDF는 Claude가 직접 읽고, xlsx는 서버가 표 텍스트로 펴서 넣는다. */
export type ChatAttachment = { filename: string; data: string };

export type EditResult = {
  /** 모델이 사람에게 하는 답. 채팅창에 그대로 표시한다(2026-08-21). */
  reply: string;
  scope: "quote_only" | "catalog_update" | "ambiguous";
  entity_quote: EntityQuote;
  changed_items: LineItem[];
};

export async function editEntityQuote(
  entityQuoteId: string,
  editRequestText: string,
  attachment?: ChatAttachment
): Promise<EditResult> {
  const res = await fetch(`${API_BASE_URL}/api/entity-quotes/${entityQuoteId}/edit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ edit_request_text: editRequestText, attachment: attachment ?? null }),
  });
  return handle<EditResult>(res);
}
