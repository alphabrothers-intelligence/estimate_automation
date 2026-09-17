// 로그인(계정) 기능이 아니라 공용 비밀번호 한 개로 막는 문이다 — 사용자가 1인이고 계정을
// 나눌 이유가 없는데, 주소만 알면 아무나 들어와 견적서를 뽑을 수 있는 게 문제였다
// (2026-09-17 사용자 요청).
//
// 비밀번호는 APP_PASSWORD 환경변수에서만 읽는다(CLAUDE.md 5장). 코드에는 없다.

export const AUTH_COOKIE = "eq_auth";

// 30일. 매번 다시 치게 하면 "비번만 간단히 치고 바로 쓴다"는 요구와 어긋난다.
export const AUTH_MAX_AGE = 60 * 60 * 24 * 30;

/** 쿠키에 담을 값. 비밀번호 원문 대신 해시를 담아, 쿠키를 들여다봐도 비밀번호는 안 나오게 한다.
 *
 * Web Crypto라 Edge(proxy.ts)와 Node(route handler) 양쪽에서 같은 코드가 돈다. */
export async function authToken(password: string): Promise<string> {
  const data = new TextEncoder().encode(`estimate-automation:${password}`);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}
