"""
DB 마이그레이션 실행 스크립트 (up/down).

사용법:
    python scripts/migrate.py up          # 아직 적용 안 된 마이그레이션을 순서대로 모두 적용
    python scripts/migrate.py up 003      # 특정 파일 번호까지만 적용
    python scripts/migrate.py down        # 가장 마지막에 적용된 마이그레이션 1개 롤백
    python scripts/migrate.py status      # 적용 현황 조회

DATABASE_URL은 .env 에서 읽는다 (CLAUDE.md 5장 규칙 — 코드에 직접 입력 금지).
각 마이그레이션 파일은 "-- up" / "-- down" 섹션 주석으로 구분한다.
"""

import os
import re
import sys
from pathlib import Path
from typing import Optional

import psycopg2
from dotenv import load_dotenv

load_dotenv()

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
DATABASE_URL = os.environ.get("DATABASE_URL")

UP_MARKER = re.compile(r"--\s*up\b", re.IGNORECASE)
DOWN_MARKER = re.compile(r"--\s*down\b", re.IGNORECASE)


def get_connection():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL이 .env에 설정되어 있지 않습니다.")
    return psycopg2.connect(DATABASE_URL)


def ensure_migrations_table(cur):
    cur.execute(
        """
        create table if not exists schema_migrations (
            filename text primary key,
            applied_at timestamptz not null default now()
        )
        """
    )


def list_migration_files():
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def split_up_down(sql_text: str):
    up_match = UP_MARKER.search(sql_text)
    down_match = DOWN_MARKER.search(sql_text)
    if not up_match:
        raise ValueError("'-- up' 섹션 마커가 없습니다.")
    up_start = up_match.end()
    up_end = down_match.start() if down_match else len(sql_text)
    up_sql = sql_text[up_start:up_end].strip()
    down_sql = sql_text[down_match.end():].strip() if down_match else ""
    return up_sql, down_sql


def cmd_status():
    with get_connection() as conn, conn.cursor() as cur:
        ensure_migrations_table(cur)
        conn.commit()
        cur.execute("select filename from schema_migrations order by filename")
        applied = {row[0] for row in cur.fetchall()}

    for path in list_migration_files():
        mark = "✅" if path.name in applied else "⬜"
        print(f"{mark} {path.name}")


def cmd_up(target: Optional[str] = None):
    with get_connection() as conn, conn.cursor() as cur:
        ensure_migrations_table(cur)
        conn.commit()
        cur.execute("select filename from schema_migrations")
        applied = {row[0] for row in cur.fetchall()}

    for path in list_migration_files():
        stem_prefix = path.name.split("_")[0]
        if target and stem_prefix > target:
            break
        if path.name in applied:
            continue

        sql_text = path.read_text(encoding="utf-8")
        up_sql, _ = split_up_down(sql_text)

        print(f"적용 중: {path.name}")
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(up_sql)
            cur.execute(
                "insert into schema_migrations (filename) values (%s)", (path.name,)
            )
            conn.commit()
        print(f"완료: {path.name}")


def cmd_down():
    with get_connection() as conn, conn.cursor() as cur:
        ensure_migrations_table(cur)
        conn.commit()
        cur.execute(
            "select filename from schema_migrations order by filename desc limit 1"
        )
        row = cur.fetchone()

    if not row:
        print("롤백할 마이그레이션이 없습니다.")
        return

    filename = row[0]
    path = MIGRATIONS_DIR / filename
    sql_text = path.read_text(encoding="utf-8")
    _, down_sql = split_up_down(sql_text)

    if not down_sql:
        raise ValueError(f"{filename}에 '-- down' 섹션이 정의되어 있지 않습니다.")

    print(f"롤백 중: {filename}")
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(down_sql)
        cur.execute("delete from schema_migrations where filename = %s", (filename,))
        conn.commit()
    print(f"롤백 완료: {filename}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]
    if command == "up":
        cmd_up(sys.argv[2] if len(sys.argv) > 2 else None)
    elif command == "down":
        cmd_down()
    elif command == "status":
        cmd_status()
    else:
        print(f"알 수 없는 명령: {command}")
        print(__doc__)
        sys.exit(1)
