// 모든 페이지 요청 앞단에서 비밀번호 쿠키를 확인한다. Next 16부터 middleware.ts는 폐기 예정이고
// proxy.ts가 같은 자리를 대신한다(빌드 시 경고로 안내됨).
//
// APP_PASSWORD가 없으면 통과시키지 않는다 — 환경변수를 빠뜨렸을 때 문이 조용히 열려 있는 쪽이
// 문이 닫혀 있는 쪽보다 훨씬 위험하다. 이 경우 /login이 "설정되지 않았습니다"라고 알려준다.

import { NextResponse, type NextRequest } from "next/server";

import { AUTH_COOKIE, authToken } from "@/lib/auth";

export async function proxy(request: NextRequest) {
  const password = process.env.APP_PASSWORD;
  const token = request.cookies.get(AUTH_COOKIE)?.value;

  if (password && token && token === (await authToken(password))) {
    return NextResponse.next();
  }

  const loginUrl = new URL("/login", request.url);
  // 딥링크로 들어온 사람이 비번을 치고 나면 원래 보려던 화면으로 보낸다.
  const target = request.nextUrl.pathname + request.nextUrl.search;
  if (target !== "/") {
    loginUrl.searchParams.set("next", target);
  }
  return NextResponse.redirect(loginUrl);
}

export const config = {
  // 로그인 화면과 그 API, 정적 자산은 막지 않는다(막으면 로그인 화면 자체가 안 뜬다).
  matcher: ["/((?!login|api/login|_next/static|_next/image|favicon.ico).*)"],
};
