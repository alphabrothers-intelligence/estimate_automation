import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.routers import catalog, estimates
from app.services import pdf_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    pdf_service.start_lo_listener()
    yield
    pdf_service.stop_lo_listener()


app = FastAPI(title="견적서 자동화 API", lifespan=lifespan)

# 배포된 프론트엔드 주소. Vercel 도메인은 사람마다 다르고 프리뷰 배포마다 바뀌므로
# 코드에 박지 않고 환경변수로 받는다. 쉼표로 여러 개 넣을 수 있다.
# 예: FRONTEND_ORIGINS=https://estimate-automation.vercel.app,https://견적.내도메인.com
FRONTEND_ORIGINS = [o.strip() for o in os.getenv("FRONTEND_ORIGINS", "").split(",") if o.strip()]


# Starlette는 처리되지 않은 예외를 CORS 미들웨어보다 바깥에서 500으로 바꾼다. 그 응답에는
# CORS 헤더가 없어서 브라우저가 응답을 통째로 막고, fetch는 네트워크 에러로 실패한다. 그래서
# 배포 환경에서는 원인이 사라진 "실패했습니다" 문구만 남는다(2026-08-24 확인). CORS보다
# 안쪽에서 먼저 잡아 JSON으로 돌려주면 에러 원문이 화면까지 도달한다.
# add_middleware는 나중에 등록한 것이 바깥이므로 이 순서(에러 핸들러 → CORS)를 바꾸지 않는다.
@app.middleware("http")
async def surface_errors(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as exc:
        logging.exception("unhandled error: %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": f"{type(exc).__name__}: {exc}"})


app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    # localhost와 127.0.0.1은 브라우저에게 서로 다른 출처다. 127.0.0.1:3001로 열면 모든 API가
    # 차단돼 과업·법인 목록이 통째로 빈 화면으로 보인다(2026-08-21 사용자 신고).
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(catalog.router)
app.include_router(estimates.router)
app.include_router(estimates.entity_quotes_router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
