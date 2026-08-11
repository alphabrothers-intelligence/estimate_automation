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
  // 썬데이워커 전용 — 투입 MM(작업일×수량÷20 근사치, PRD 7.4)과 항목별 세액(공급가액×10%).
  input_mm?: number;
  tax_amount?: number;
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
  // 법인마다 실제 원본 양식의 컬럼 명칭·순서가 다르다(예: 작업일/소요일, 수량/작업수량) —
  // 백엔드가 각 법인의 실제 템플릿에서 그대로 계산해 내려준다(2026-07-10).
  column_labels: Record<string, string>;
  detail_column_order: string[];
  // 알파브라더스처럼 항목 블록마다 구분(대)/구분(중)이 있는 양식인지 (item.task_type로 채움)
  show_category_split: boolean;
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

export type QuoteTemplateSummary = {
  entity_id: string;
  entity_name: string;
  storage_path: string | null;
  file_name: string | null;
  file_size: number | null;
  updated_at: string | null;
  is_available: boolean;
  task_types: string[];
  sheet_names: string[];
};

export function getEntityQuotePdfUrl(entityQuoteId: string, options?: { inline?: boolean }): string {
  const suffix = options?.inline ? "?inline=1" : "";
  return `${API_BASE_URL}/api/entity-quotes/${entityQuoteId}/pdf${suffix}`;
}

export function getEntityQuoteXlsxUrl(entityQuoteId: string): string {
  return `${API_BASE_URL}/api/entity-quotes/${entityQuoteId}/xlsx`;
}

export class ApiError extends Error {}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(body?.detail ?? `요청 실패 (${res.status})`);
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
    throw new ApiError(body?.detail ?? `요청 실패 (${res.status})`);
  }
}

export async function fetchTemplates(): Promise<QuoteTemplateSummary[]> {
  const res = await fetch(`${API_BASE_URL}/api/templates`, { cache: "no-store" });
  return handle<QuoteTemplateSummary[]>(res);
}

export async function replaceTemplate(entityId: string, file: File): Promise<QuoteTemplateSummary> {
  const body = new FormData();
  body.append("file", file);
  const res = await fetch(`${API_BASE_URL}/api/templates/${entityId}`, { method: "PUT", body });
  return handle<QuoteTemplateSummary>(res);
}

export async function deleteTemplate(entityId: string): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/templates/${entityId}`, { method: "DELETE" });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(body?.detail ?? `요청 실패 (${res.status})`);
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
};

export type CreateEstimateSetInput = {
  project_name: string;
  recipient_name: string;
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

export async function updateLineItems(
  entityQuoteId: string,
  items: LineItem[]
): Promise<EntityQuote> {
  const res = await fetch(`${API_BASE_URL}/api/entity-quotes/${entityQuoteId}/line-items`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ items }),
  });
  return handle<EntityQuote>(res);
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

export type EditResult = {
  scope: "quote_only" | "catalog_update" | "ambiguous";
  entity_quote: EntityQuote;
  changed_items: LineItem[];
};

export async function editEntityQuote(
  entityQuoteId: string,
  editRequestText: string
): Promise<EditResult> {
  const res = await fetch(`${API_BASE_URL}/api/entity-quotes/${entityQuoteId}/edit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ edit_request_text: editRequestText }),
  });
  return handle<EditResult>(res);
}
