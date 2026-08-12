"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

const navigation = [
  { href: "/estimates", label: "견적서 목록", icon: "list" },
  { href: "/", label: "견적서 작성", icon: "create" },
] as const;

function NavIcon({ name }: { name: (typeof navigation)[number]["icon"] }) {
  if (name === "list") {
    return <path d="M8 6h11M8 12h11M8 18h11M4 6h.01M4 12h.01M4 18h.01" />;
  }
  return <path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4Z" />;
}

export default function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="min-h-screen md:grid md:grid-cols-[248px_1fr]">
      <aside className="border-b border-slate-200 bg-white md:sticky md:top-0 md:h-screen md:border-b-0 md:border-r">
        <div className="flex h-full flex-col">
          <div className="flex h-20 items-center gap-3 border-b border-slate-100 px-6">
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-indigo-600 text-white shadow-sm shadow-indigo-200">
              <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M7 3h7l4 4v14H7zM14 3v5h5M10 13h5M10 17h5" />
              </svg>
            </span>
            <div>
              <p className="font-bold tracking-tight text-slate-900">AutoQuote</p>
              <p className="text-[11px] text-slate-400">견적서 자동화</p>
            </div>
          </div>
          <nav className="flex gap-1 overflow-x-auto p-3 md:block md:space-y-1 md:overflow-visible md:p-4">
            {navigation.map((item) => {
              const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`flex shrink-0 items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
                    active ? "bg-indigo-50 text-indigo-700" : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
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
          <div className="mt-auto hidden border-t border-slate-100 p-5 md:block">
            <div className="flex items-center gap-3">
              <span className="grid h-8 w-8 place-items-center rounded-full bg-indigo-100 text-xs font-semibold text-indigo-700">DS</span>
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
  );
}
