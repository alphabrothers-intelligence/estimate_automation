"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ApiError, deleteEstimateSet, fetchEstimateSets, type EstimateSetSummary } from "@/lib/api";

function formatDate(value: string) {
  return new Intl.DateTimeFormat("ko-KR", { year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(value));
}

export default function EstimatesPage() {
  const router = useRouter();
  const [items, setItems] = useState<EstimateSetSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    fetchEstimateSets()
      .then(setItems)
      .catch((e) => setError(e instanceof ApiError ? e.message : "견적서 목록을 불러오지 못했습니다."))
      .finally(() => setLoading(false));
  }, []);

  function toggleOne(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAll() {
    setSelected((prev) => (prev.size === items.length ? new Set() : new Set(items.map((i) => i.id))));
  }

  async function handleDeleteSelected() {
    if (selected.size === 0) return;
    if (!confirm(`선택한 견적서 ${selected.size}건을 삭제할까요? 되돌릴 수 없습니다.`)) return;
    setDeleting(true);
    try {
      await Promise.all([...selected].map((id) => deleteEstimateSet(id)));
      setItems((prev) => prev.filter((item) => !selected.has(item.id)));
      setSelected(new Set());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "견적서 삭제에 실패했습니다.");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <main className="px-5 py-8 sm:px-8 lg:px-12 lg:py-10">
      <div className="mx-auto max-w-6xl">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-sm font-semibold text-indigo-600">견적서 목록</p>
            <h1 className="mt-1 text-3xl font-bold tracking-tight text-slate-900">생성한 견적서</h1>
            <p className="mt-2 text-sm text-slate-500">사업 건별 본견적과 비교견적을 한곳에서 확인합니다.</p>
          </div>
          <div className="flex items-center gap-2">
            {selected.size > 0 && (
              <button
                onClick={handleDeleteSelected}
                disabled={deleting}
                className="rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-sm font-semibold text-red-700 hover:bg-red-100 disabled:opacity-50"
              >
                {deleting ? "삭제 중…" : `선택 삭제 (${selected.size})`}
              </button>
            )}
            <Link href="/" className="rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-indigo-700">
              + 새 견적서 작성
            </Link>
          </div>
        </div>

        <section className="mt-8 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          {loading && <p className="p-8 text-center text-sm text-slate-400">불러오는 중…</p>}
          {error && <p className="m-5 rounded-lg bg-red-50 p-4 text-sm text-red-700">{error}</p>}
          {!loading && !error && items.length === 0 && (
            <div className="px-6 py-16 text-center">
              <div className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-indigo-50 text-indigo-600">
                <svg className="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M7 3h7l4 4v14H7zM14 3v5h5M10 13h5M10 17h5" /></svg>
              </div>
              <p className="mt-4 font-semibold text-slate-700">아직 생성한 견적서가 없습니다.</p>
              <p className="mt-1 text-sm text-slate-400">첫 견적서를 만들면 여기에 표시됩니다.</p>
            </div>
          )}
          {items.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px] text-sm">
                <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                  <tr>
                    <th className="w-10 px-6 py-3.5">
                      <input
                        type="checkbox"
                        checked={selected.size === items.length && items.length > 0}
                        onChange={toggleAll}
                        className="h-4 w-4 rounded border-slate-300"
                        aria-label="전체 선택"
                      />
                    </th>
                    <th className="px-4 py-3.5">사업명</th><th className="px-4 py-3.5">과업</th><th className="px-4 py-3.5">발행 법인</th><th className="px-4 py-3.5 text-right">총액</th><th className="px-6 py-3.5 text-right">생성일</th></tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {items.map((item) => (
                    <tr
                      key={item.id}
                      onClick={() => router.push(`/estimates/${item.id}`)}
                      className="cursor-pointer hover:bg-slate-50/70"
                    >
                      <td className="px-6 py-4" onClick={(e) => e.stopPropagation()}>
                        <input
                          type="checkbox"
                          checked={selected.has(item.id)}
                          onChange={() => toggleOne(item.id)}
                          className="h-4 w-4 rounded border-slate-300"
                          aria-label={`${item.project_name} 선택`}
                        />
                      </td>
                      <td className="px-4 py-4 font-semibold text-slate-800">{item.project_name}</td>
                      <td className="px-4 py-4"><span className="rounded-full bg-indigo-50 px-2.5 py-1 text-xs font-medium text-indigo-700">{item.task_type}</span></td>
                      <td className="px-4 py-4 text-slate-500">{item.entity_names.join(" · ")} <span className="text-slate-300">({item.quote_count})</span></td>
                      <td className="px-4 py-4 text-right font-medium text-slate-700">{item.total_amount.toLocaleString()}원</td>
                      <td className="px-6 py-4 text-right text-slate-400">{formatDate(item.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
