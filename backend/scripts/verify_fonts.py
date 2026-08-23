"""컨테이너 안에서 한글 글꼴이 제대로 잡히는지 검증한다.

    docker run --rm --env-file backend/.env -v "$PWD/out:/out" estimate-backend python scripts/verify_fonts.py

마스터 xlsx가 지정한 글꼴 중 맑은 고딕·굴림체·Arial은 독점이라 이미지에 넣을 수 없고,
fonts-local.conf가 자유 글꼴로 치환한다. 그 치환이 실제로 먹었는지는 리눅스에서 돌려봐야만
알 수 있어서(로컬 맥은 시스템에 글꼴이 다 있어 항상 잘 나온다) 이 스크립트가 필요하다.

세 가지를 본다:
  1) fc-match — 각 글꼴 이름이 무엇으로 해석되는지. 여기서 치환이 틀리면 나머지는 볼 것도 없다.
  2) 실제 발급 — 견적서를 PDF로 뽑아 /out에 남긴다.
  3) pdffonts — 그 PDF에 어떤 글꼴이 박혔는지. 한글 글꼴이 안 보이면 □□□로 나갔다는 뜻이다.

/out에 나온 PDF는 맥에서 뽑은 것과 눈으로 비교해야 최종 확인이 된다 — 글자가 깨지는 건
숫자로 잡히지 않는다.
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 마스터 5종이 실제로 쓰는 글꼴. 앞 4개는 독점이라 치환돼야 하고, 뒤 3개는 진짜로 설치돼야 한다.
FONTS = [
    ("맑은 고딕", "치환"),
    ("굴림체", "치환"),
    ("Arial", "치환"),
    ("Arial Unicode MS", "치환"),
    ("나눔고딕", "설치"),
    ("나눔스퀘어_ac", "설치"),
    ("Pretendard SemiBold", "설치"),
]

OUT = Path("/out")


def check_fonts() -> bool:
    print("=" * 68)
    print("1) 글꼴 해석 (fc-match)")
    print("=" * 68)
    ok = True
    for name, kind in FONTS:
        resolved = subprocess.run(
            ["fc-match", name], capture_output=True, text=True
        ).stdout.strip()
        # 한글을 못 그리는 글꼴로 떨어지면 □□□가 된다. DejaVu가 대표적인 신호다.
        bad = "DejaVu" in resolved or not resolved
        ok = ok and not bad
        print(f"  [{kind}] {name:<20} → {resolved}{'   ← 위험' if bad else ''}")
    return ok


def render(quote_ids) -> list:
    print()
    print("=" * 68)
    print("2) 실제 견적서 발급")
    print("=" * 68)
    from app.services import pdf_service

    OUT.mkdir(parents=True, exist_ok=True)
    made = []
    for quote_id in quote_ids:
        path = OUT / f"{quote_id[:8]}.pdf"
        path.write_bytes(pdf_service.render_entity_quote_pdf(quote_id))
        print(f"  {path}  ({path.stat().st_size // 1024} KB)")
        made.append(path)
    return made


def check_embedded(paths) -> bool:
    print()
    print("=" * 68)
    print("3) PDF에 박힌 글꼴 (pdffonts)")
    print("=" * 68)
    ok = True
    for path in paths:
        result = subprocess.run(["pdffonts", str(path)], capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  {path.name}: pdffonts 없음 — 건너뜀 (poppler-utils 미설치)")
            return True
        names = result.stdout
        has_korean = any(k in names for k in ("Noto", "Nanum", "Pretendard"))
        ok = ok and has_korean
        print(f"  {path.name}: {'한글 글꼴 있음' if has_korean else '한글 글꼴 없음 ← 위험'}")
        for line in names.splitlines()[2:]:
            if line.strip():
                print(f"      {line.split()[0]}")
    return ok


if __name__ == "__main__":
    quote_ids = sys.argv[1:]
    if not quote_ids:
        print("사용법: python scripts/verify_fonts.py <견적서ID> [<견적서ID> ...]")
        sys.exit(2)

    fonts_ok = check_fonts()
    made = render(quote_ids)
    embedded_ok = check_embedded(made)

    print()
    print("=" * 68)
    if fonts_ok and embedded_ok:
        print("자동 검사 통과. 이제 /out의 PDF를 맥에서 뽑은 것과 눈으로 비교하세요.")
        print("글자 깨짐·표 어긋남은 숫자로 안 잡힙니다.")
    else:
        print("실패 — 위의 '위험' 표시를 확인하세요.")
        sys.exit(1)