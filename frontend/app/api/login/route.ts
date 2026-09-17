import { NextResponse } from "next/server";

import { AUTH_COOKIE, AUTH_MAX_AGE, authToken } from "@/lib/auth";

export async function POST(request: Request) {
  const password = process.env.APP_PASSWORD;
  if (!password) {
    return NextResponse.json(
      { detail: "서버에 APP_PASSWORD가 설정되지 않았습니다. 배포 환경변수를 확인해주세요." },
      { status: 500 },
    );
  }

  const { password: input } = (await request.json()) as { password?: string };
  // 원문끼리 비교하지 않고 해시끼리 비교한다 — 길이가 항상 같아서 비교 시간으로 비밀번호를
  // 더듬어 볼 여지를 없앤다.
  if (!input || (await authToken(input)) !== (await authToken(password))) {
    return NextResponse.json({ detail: "비밀번호가 올바르지 않습니다." }, { status: 401 });
  }

  const response = NextResponse.json({ ok: true });
  response.cookies.set(AUTH_COOKIE, await authToken(password), {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: AUTH_MAX_AGE,
  });
  return response;
}
