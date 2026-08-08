"""
법인 마스터 xlsx/xls 원본을 Supabase Storage(quote-templates 버킷)에 올린다.

quote_templates.storage_path에 저장된 경로를 그대로 버킷 내 경로로 쓰며, DB에 있는
storage_path 목록을 그대로 소스로 삼는다(로컬 파일명 매핑을 따로 하드코딩하면 DB가
바뀔 때 스크립트가 조용히 낡아버리는 걸 실제로 겪었다 — blendedlab이 .xls에서 .xlsx로
바뀐 뒤에도 이 스크립트는 예전 .xls만 올리고 있었음). 최초 이관, 또는 로컬에서 직접 파일을
바꾼 뒤 동기화할 때 실행한다 — 평소 웹 UI(/templates)로 양식을 바꾸면 template_service가
Storage에 바로 반영하므로 이 스크립트를 쓸 필요 없다.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

BUCKET = "quote-templates"
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


def main():
    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SECRET_KEY"])
    storage = client.storage

    existing_buckets = {b.name for b in storage.list_buckets()}
    if BUCKET not in existing_buckets:
        storage.create_bucket(BUCKET, options={"public": False})
        print(f"버킷 생성: {BUCKET}")
    else:
        print(f"버킷 이미 존재: {BUCKET}")

    rows = client.table("quote_templates").select("storage_path").execute().data
    storage_paths = sorted({row["storage_path"] for row in rows})

    for storage_path in storage_paths:
        local_path = TEMPLATES_DIR / Path(storage_path).name
        if not local_path.exists():
            print(f"건너뜀 (로컬에 없음): {local_path}")
            continue
        data = local_path.read_bytes()
        storage.from_(BUCKET).upload(storage_path, data, file_options={"upsert": "true"})
        print(f"업로드 완료: {local_path.name} -> {BUCKET}/{storage_path} ({len(data):,} bytes)")


if __name__ == "__main__":
    main()
