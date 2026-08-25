"""법인 마스터 양식을 Supabase Storage에 올린다.

사용법:
    python3 scripts/upload_templates.py comparison_forms.xlsx   # 지정한 것만 올림 (권장)
    python3 scripts/upload_templates.py --dry-run               # 뭘 올릴지만 보여줌
    python3 scripts/upload_templates.py                         # 로컬과 다른 것 전부
    python3 scripts/upload_templates.py --force                 # 같아도 전부 다시

**파일명을 지정하는 쪽을 권한다.** 로컬과 Storage는 같은 양식이어도 바이트가 다를 수 있고
(압축 방식 차이 — blendedlab.xlsx가 실제로 그랬다, 2026-08-25), 그러면 인자 없이 돌렸을 때
"다르다"고 판단해 잘 돌아가던 운영 파일까지 덮어쓴다. 바꾼 파일만 이름으로 짚어 올리는 게
안전하다.

왜 따로 실행하나 — 앱은 마스터 양식을 저장소가 아니라 **Supabase Storage**에서 읽는다
(`template_storage.download`). 그래서 templates/ 에 파일을 커밋하고 배포해도 발급에는 반영되지
않는다. 실제로 이것 때문에 052(비교견적 양식 5종)가 배포 후에도 동작하지 않았다(2026-08-25).

컨테이너 시작 시 자동 동기화하지 않는 이유:
  · 양식은 1년에 몇 번 바뀐다. 매 부팅마다 확인할 이유가 없다.
  · 이 앱은 Render에서 콜드스타트가 잦아서, 부팅 경로에 네트워크 I/O를 더하는 게 손해다.
  · `template_storage.download`가 프로세스별 lru_cache라, 올려도 재시작 전엔 안 읽힌다.
따라서 양식을 바꿨을 때만 손으로 한 번 돌리는 게 맞다.
"""

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import template_storage

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
# .bak_* 같은 백업본과 구형 .xls는 올리지 않는다 — 발급에 쓰이는 건 .xlsx뿐이다.
PATTERN = "*.xlsx"


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:12]


def main(argv: list) -> int:
    force = "--force" in argv
    dry_run = "--dry-run" in argv
    wanted = [a for a in argv if not a.startswith("--")]

    files = sorted(p for p in TEMPLATES_DIR.glob(PATTERN) if not p.name.startswith("~$"))
    if wanted:
        by_name = {p.name: p for p in files}
        missing = [n for n in wanted if n not in by_name]
        if missing:
            print(f"templates/ 에 없는 파일: {', '.join(missing)}")
            return 1
        files = [by_name[n] for n in wanted]
    if not files:
        print(f"올릴 파일이 없습니다: {TEMPLATES_DIR}/{PATTERN}")
        return 1

    uploaded = skipped = failed = 0
    for path in files:
        remote_path = f"templates/{path.name}"
        local = path.read_bytes()

        if not force:
            try:
                if _digest(template_storage.download(remote_path)) == _digest(local):
                    print(f"  = {remote_path}  (같음, 건너뜀)")
                    skipped += 1
                    continue
            except Exception:
                pass  # 아직 없는 파일이면 그냥 올린다

        if dry_run:
            print(f"  ↑ {remote_path}  ({len(local):,} bytes)  [dry-run]")
            uploaded += 1
            continue

        try:
            template_storage.upload(remote_path, local)
            print(f"  ↑ {remote_path}  ({len(local):,} bytes)")
            uploaded += 1
        except Exception as e:  # noqa: BLE001 — 어느 파일에서 왜 실패했는지 그대로 보여준다
            print(f"  ✗ {remote_path}  {type(e).__name__}: {e}")
            failed += 1

    print(f"\n올림 {uploaded} / 건너뜀 {skipped} / 실패 {failed}")
    if failed:
        return 1
    if uploaded and not dry_run:
        print("※ 이미 떠 있는 백엔드는 양식을 프로세스 캐시에 들고 있습니다 — 재배포하거나 재시작해야 반영됩니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
