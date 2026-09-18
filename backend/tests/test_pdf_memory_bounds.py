"""PDF 캐시 상한 자체 점검 — `python backend/tests/test_pdf_memory_bounds.py`.

Render 인스턴스가 메모리 한도를 넘겨 자동 재시작되던 원인 중 하나(끝없이 늘어나는 PDF
캐시)를 막는 장치가 실제로 도는지 본다. 상주 LibreOffice 리스너로 인한 누적은 리스너
자체를 없애 해결했다(2026-09-18) — 매 변환마다 새 프로세스를 띄우고 바로 죽이므로 볼
상태가 없다.
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


if __name__ == "__main__":
    test_pdf_cache_is_bounded()
    print("ok")
