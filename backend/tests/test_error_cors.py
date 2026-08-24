from fastapi.testclient import TestClient

from app.main import app


@app.get("/api/_boom")
def _boom():
    raise RuntimeError("펑")


def test_unhandled_error_reaches_browser_with_cors_headers():
    # CORS 헤더가 빠지면 브라우저가 응답을 막아 화면에 원인이 안 뜬다 — 이게 회귀의 핵심이다.
    res = TestClient(app).get("/api/_boom", headers={"Origin": "http://localhost:3001"})
    assert res.status_code == 500
    assert res.json()["detail"] == "RuntimeError: 펑"
    assert res.headers["access-control-allow-origin"] == "http://localhost:3001"
