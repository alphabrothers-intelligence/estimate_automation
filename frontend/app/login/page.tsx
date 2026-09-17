"use client";

import { useState } from "react";

export default function LoginPage() {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const response = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        setError(body?.detail ?? "로그인에 실패했습니다.");
        return;
      }
      // useSearchParams는 Suspense 경계를 요구해서 화면 하나 때문에 구조가 늘어난다 — 제출
      // 시점에 주소창에서 한 번만 읽으면 그만이다.
      const next = new URLSearchParams(window.location.search).get("next");
      // 외부 주소로 튕겨 보내는 데 쓰이지 않도록 내부 경로만 허용한다.
      window.location.href = next?.startsWith("/") && !next.startsWith("//") ? next : "/";
    } catch {
      setError("서버에 연결하지 못했습니다.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="grid min-h-screen place-items-center bg-slate-50 px-6">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex items-center gap-2.5">
          <span className="grid h-9 w-9 place-items-center rounded-lg bg-slate-900 text-white">
            <svg
              className="h-5 w-5"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M7 3h7l4 4v14H7zM14 3v5h5M10 13h5M10 17h5" />
            </svg>
          </span>
          <div>
            <p className="text-base font-bold tracking-tight text-slate-900">AutoQuote</p>
            <p className="text-xs text-slate-400">견적서 자동화</p>
          </div>
        </div>

        <form
          onSubmit={handleSubmit}
          className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
        >
          <label htmlFor="password" className="block text-sm font-medium text-slate-700">
            비밀번호
          </label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoFocus
            autoComplete="current-password"
            aria-invalid={error ? true : undefined}
            aria-describedby={error ? "password-error" : undefined}
            className="mt-2 w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm text-slate-900 outline-none transition focus:border-slate-400 focus:ring-2 focus:ring-slate-200"
          />
          {error ? (
            <p id="password-error" role="alert" className="mt-2 text-sm text-rose-600">
              {error}
            </p>
          ) : null}
          <button
            type="submit"
            disabled={submitting || !password}
            className="mt-5 w-full rounded-xl bg-slate-900 py-2.5 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            {submitting ? "확인 중…" : "들어가기"}
          </button>
        </form>
      </div>
    </main>
  );
}
