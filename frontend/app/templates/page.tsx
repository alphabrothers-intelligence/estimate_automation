"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError, deleteTemplate, fetchTemplates, replaceTemplate, type QuoteTemplateSummary } from "@/lib/api";

function fileSize(value: number | null) {
  if (value == null) return "";
  return value > 1024 * 1024 ? `${(value / 1024 / 1024).toFixed(1)} MB` : `${Math.ceil(value / 1024)} KB`;
}

function TemplateCard({ item, onChanged }: { item: QuoteTemplateSummary; onChanged: (next: QuoteTemplateSummary) => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onUpload(file: File | undefined) {
    if (!file) return;
    setBusy(true); setError(null);
    try { onChanged(await replaceTemplate(item.entity_id, file)); }
    catch (e) { setError(e instanceof ApiError ? e.message : "양식 업로드에 실패했습니다."); }
    finally { setBusy(false); if (inputRef.current) inputRef.current.value = ""; }
  }

  async function onDelete() {
    if (!window.confirm(`${item.entity_name} 양식을 삭제할까요? 삭제 후에는 새 양식을 올리기 전까지 이 법인 견적을 발급할 수 없습니다.`)) return;
    setBusy(true); setError(null);
    try {
      await deleteTemplate(item.entity_id);
      onChanged({ ...item, is_available: false, file_size: null, updated_at: null });
    } catch (e) { setError(e instanceof ApiError ? e.message : "양식 삭제에 실패했습니다."); }
    finally { setBusy(false); }
  }

  return (
    <article className={`rounded-xl border bg-white p-5 transition-shadow hover:shadow-md ${item.is_available ? "border-slate-200" : "border-dashed border-slate-300"}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <span className={`grid h-11 w-11 shrink-0 place-items-center rounded-xl ${item.is_available ? "bg-emerald-50 text-emerald-600" : "bg-slate-100 text-slate-400"}`}>
            <svg className="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M7 3h7l4 4v14H7zM14 3v5h5M9.5 12.5h6M9.5 16h6" /></svg>
          </span>
          <div className="min-w-0"><h2 className="font-bold text-slate-800">{item.entity_name}</h2><p className="mt-0.5 truncate text-xs text-slate-400">{item.file_name ?? "등록된 양식 없음"}</p></div>
        </div>
        <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${item.is_available ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>{item.is_available ? "사용 중" : "미등록"}</span>
      </div>
      <div className="mt-5 min-h-24 rounded-lg bg-slate-50 p-3 text-xs text-slate-500">
        {item.is_available ? <><p><span className="text-slate-400">파일 크기</span><span className="float-right font-medium text-slate-600">{fileSize(item.file_size)}</span></p><p className="mt-2"><span className="text-slate-400">적용 과업</span><span className="float-right max-w-[68%] text-right font-medium text-slate-600">{item.task_types.join(" · ")}</span></p><p className="mt-2"><span className="text-slate-400">연결 시트</span><span className="float-right max-w-[68%] truncate text-right font-medium text-slate-600">{item.sheet_names.join(" · ")}</span></p></> : <div className="grid h-full min-h-16 place-items-center text-center"><p>원본 XLSX/XLS 양식을<br />업로드해 주세요.</p></div>}
      </div>
      {error && <p className="mt-3 text-xs text-red-600">{error}</p>}
      <input ref={inputRef} type="file" accept=".xlsx,.xls" className="hidden" onChange={(e) => onUpload(e.target.files?.[0])} />
      <div className="mt-4 flex gap-2">
        <button type="button" disabled={busy} onClick={() => inputRef.current?.click()} className="flex-1 rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-2 text-sm font-semibold text-indigo-700 hover:bg-indigo-100 disabled:opacity-50">{busy ? "처리 중…" : item.is_available ? "다시 업로드" : "양식 업로드"}</button>
        {item.is_available && <button type="button" disabled={busy} onClick={onDelete} className="rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-500 hover:border-red-200 hover:bg-red-50 hover:text-red-600 disabled:opacity-50">삭제</button>}
      </div>
    </article>
  );
}

export default function TemplatesPage() {
  const [items, setItems] = useState<QuoteTemplateSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { fetchTemplates().then(setItems).catch((e) => setError(e instanceof ApiError ? e.message : "양식 목록을 불러오지 못했습니다.")).finally(() => setLoading(false)); }, []);
  function update(next: QuoteTemplateSummary) { setItems((prev) => prev.map((item) => item.entity_id === next.entity_id ? next : item)); }
  return (
    <main className="px-5 py-8 sm:px-8 lg:px-12 lg:py-10"><div className="mx-auto max-w-6xl">
      <p className="text-sm font-semibold text-indigo-600">견적서 양식 관리</p><h1 className="mt-1 text-3xl font-bold tracking-tight text-slate-900">법인별 원본 양식</h1><p className="mt-2 text-sm text-slate-500">로고·도장·고정 문구가 포함된 Excel 원본을 관리합니다. 교체한 양식은 다음 견적부터 바로 적용됩니다.</p>
      <div className="mt-6 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800"><strong>양식 구조를 유지해 주세요.</strong> 기존 셀 위치나 시트명을 변경하면 저장된 셀 매핑과 맞지 않을 수 있습니다.</div>
      {loading && <p className="mt-10 text-center text-sm text-slate-400">양식을 불러오는 중…</p>}{error && <p className="mt-6 rounded-lg bg-red-50 p-4 text-sm text-red-700">{error}</p>}
      {!loading && !error && <section className="mt-7 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{items.map((item) => <TemplateCard key={item.entity_id} item={item} onChanged={update} />)}</section>}
    </div></main>
  );
}
