"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { createContext, useContext, useState, type Dispatch, type ReactNode, type SetStateAction } from "react";

const navigation = [
  { href: "/estimates", label: "견적서 목록", icon: "list" },
  { href: "/", label: "견적서 작성", icon: "create" },
] as const;

const GeneratedEstimateLayoutContext = createContext<Dispatch<SetStateAction<boolean>>>(() => undefined);

export function useGeneratedEstimateLayout() {
  return useContext(GeneratedEstimateLayoutContext);
}

function NavIcon({ name }: { name: (typeof navigation)[number]["icon"] }) {
  if (name === "list") {
    return <path d="M8 6h11M8 12h11M8 18h11M4 6h.01M4 12h.01M4 18h.01" />;
  }
  return <path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4Z" />;
}

export default function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const [generatedEstimateLayout, setGeneratedEstimateLayout] = useState(false);

  return (
    <GeneratedEstimateLayoutContext.Provider value={setGeneratedEstimateLayout}>
    <div
      className={
        generatedEstimateLayout
          ? "min-h-screen min-[1900px]:grid min-[1900px]:grid-cols-[248px_1fr]"
          : "min-h-screen xl:grid xl:grid-cols-[248px_1fr]"
      }
    >
      <header
        className={`sticky top-0 z-30 flex h-16 items-center justify-between border-b border-slate-200 bg-white/95 px-4 backdrop-blur ${
          generatedEstimateLayout ? "min-[1900px]:hidden" : "xl:hidden"
        }`}
      >
        <div className="flex items-center gap-2.5">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-slate-900 text-white">
            <svg className="h-[18px] w-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M7 3h7l4 4v14H7zM14 3v5h5M10 13h5M10 17h5" />
            </svg>
          </span>
          <div>
            <p className="text-sm font-bold tracking-tight text-slate-900">AutoQuote</p>
            <p className="text-[10px] text-slate-400">견적서 자동화</p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => setMenuOpen(true)}
          className="grid h-10 w-10 place-items-center rounded-xl border border-slate-200 text-slate-600 transition hover:bg-slate-50"
          aria-label="메뉴 열기"
          aria-expanded={menuOpen}
        >
          <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <path d="M4 7h16M4 12h16M4 17h16" />
          </svg>
        </button>
      </header>

      {menuOpen && (
        <button
          type="button"
          className={`fixed inset-0 z-40 bg-slate-950/30 backdrop-blur-[1px] ${
            generatedEstimateLayout ? "min-[1900px]:hidden" : "xl:hidden"
          }`}
          onClick={() => setMenuOpen(false)}
          aria-label="메뉴 닫기"
        />
      )}

      <aside
        className={
          "fixed inset-y-0 left-0 z-50 w-[248px] border-r border-slate-200 bg-white transition-transform duration-200 " +
          (generatedEstimateLayout
            ? "min-[1900px]:sticky min-[1900px]:top-0 min-[1900px]:h-screen min-[1900px]:translate-x-0 "
            : "xl:sticky xl:top-0 xl:h-screen xl:translate-x-0 ") +
          (menuOpen ? "translate-x-0" : "-translate-x-full")
        }
      >
        <div className="flex h-full flex-col">
          <div className="flex h-20 items-center gap-3 border-b border-slate-100 px-5">
            <span className="grid h-9 w-9 place-items-center rounded-lg bg-slate-900 text-white">
              <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M7 3h7l4 4v14H7zM14 3v5h5M10 13h5M10 17h5" />
              </svg>
            </span>
            <div>
              <p className="font-bold tracking-tight text-slate-900">AutoQuote</p>
              <p className="text-[11px] text-slate-400">견적서 자동화</p>
            </div>
            <button
              type="button"
              onClick={() => setMenuOpen(false)}
              className={`ml-auto h-9 w-9 place-items-center rounded-lg text-slate-400 hover:bg-slate-50 hover:text-slate-700 ${
                generatedEstimateLayout ? "grid min-[1900px]:hidden" : "grid xl:hidden"
              }`}
              aria-label="메뉴 닫기"
            >
              <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <path d="m6 6 12 12M18 6 6 18" />
              </svg>
            </button>
          </div>
          <nav className="space-y-1 p-4">
            {navigation.map((item) => {
              const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={() => setMenuOpen(false)}
                  className={`flex shrink-0 items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
                    active ? "bg-slate-100 text-slate-950" : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
                  }`}
                >
                  <svg className="h-[18px] w-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                    <NavIcon name={item.icon} />
                  </svg>
                  {item.label}
                </Link>
              );
            })}
          </nav>
          <div className="mt-auto border-t border-slate-100 p-5">
            <div className="flex items-center gap-3">
              <span className="grid h-8 w-8 place-items-center rounded-full bg-slate-900 text-xs font-semibold text-white">DS</span>
              <div>
                <p className="text-sm font-medium text-slate-700">데이터솔루션팀</p>
                <p className="text-xs text-slate-400">관리자</p>
              </div>
            </div>
          </div>
        </div>
      </aside>
      <div className="min-w-0">{children}</div>
    </div>
    </GeneratedEstimateLayoutContext.Provider>
  );
}
