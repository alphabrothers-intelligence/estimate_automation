"""PDF 캐시·LibreOffice 재기동 자체 점검 — `python backend/tests/test_pdf_memory_bounds.py`.

Render 인스턴스가 메모리 한도를 넘겨 자동 재시작되던 원인 두 가지(끝없이 늘어나는 PDF 캐시,
영영 안 죽는 상주 LibreOffice)를 막는 장치가 실제로 도는지 본다. 여기가 조용히 풀리면
증상은 몇 시간 뒤 OOM 메일로만 나타나서 알아채기 어렵다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import pdf_service


def test_pdf_cache_is_bounded():
    pdf_service._pdf_cache.clear()
    for i in range(pdf_service._PDF_CACHE_MAX + 5):
        pdf_service._cache_pdf(f"quote-{i}", "hash", b"x" * 1024)

    assert len(pdf_service._pdf_cache) == pdf_service._PDF_CACHE_MAX
    # 오래된 것부터 버린다 — 마지막 것은 남고 첫 것은 없다.
    assert "quote-0" not in pdf_service._pdf_cache
    assert f"quote-{pdf_service._PDF_CACHE_MAX + 4}" in pdf_service._pdf_cache


def test_listener_restarts_every_n_conversions():
    calls = []
    pdf_service.stop_lo_listener = lambda: calls.append("stop")
    pdf_service.start_lo_listener = lambda: calls.append("start")
    pdf_service._conversions_since_restart = 0

    for _ in range(pdf_service._LO_RESTART_EVERY - 1):
        pdf_service._recycle_lo_listener_if_needed()
    assert calls == [], "한도 전에는 멀쩡한 리스너를 건드리지 않는다"

    pdf_service._recycle_lo_listener_if_needed()
    assert calls == ["stop", "start"]

    for _ in range(pdf_service._LO_RESTART_EVERY):
        pdf_service._recycle_lo_listener_if_needed()
    assert calls == ["stop", "start", "stop", "start"], "카운터가 0부터 다시 센다"


if __name__ == "__main__":
    test_pdf_cache_is_bounded()
    test_listener_restarts_every_n_conversions()
    print("ok")
