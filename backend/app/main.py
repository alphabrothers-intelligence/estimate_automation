from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import catalog, estimates, templates

app = FastAPI(title="견적서 자동화 API")

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://localhost:\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(catalog.router)
app.include_router(estimates.router)
app.include_router(estimates.entity_quotes_router)
app.include_router(templates.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
