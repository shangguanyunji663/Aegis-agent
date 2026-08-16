"""一次性数据迁移:把 data/aegis.sqlite 的全部表复制到 MySQL(.env 的 DATABASE_URL)。

用法:
    python -m scripts.migrate_sqlite_to_mysql            # 目标表非空时拒绝执行
    python -m scripts.migrate_sqlite_to_mysql --force    # 目标有数据也照常插入(可能撞唯一键)

迁移完成后旧 SQLite 文件保留为备份,不会删除。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import create_engine, func, inspect, select

from app import entities  # noqa: F401 - 注册全部 ORM 实体
from app.database import Base, build_engine, resolve_database_url

ROOT = Path(__file__).resolve().parents[1]
SQLITE_PATH = ROOT / "data" / "aegis.sqlite"


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate aegis sqlite data to MySQL.")
    parser.add_argument("--force", action="store_true", help="目标表非空时仍继续插入")
    args = parser.parse_args()

    if not SQLITE_PATH.exists():
        print(f"[skip] 未找到 SQLite 文件: {SQLITE_PATH}")
        return

    mysql_url = resolve_database_url()
    if not mysql_url.startswith("mysql"):
        print(f"[skip] 当前 DATABASE_URL 不是 MySQL: {mysql_url}")
        return

    source = create_engine(f"sqlite:///{SQLITE_PATH}", connect_args={"check_same_thread": False})
    target = build_engine()
    inspector = inspect(target)
    target_tables = set(inspector.get_table_names())

    total_rows = 0
    with source.connect() as src_conn, target.begin() as dst_conn:
        for table in Base.metadata.sorted_tables:
            rows = src_conn.execute(table.select()).mappings().all()
            existing = 0
            if table.name in target_tables:
                existing = dst_conn.execute(select(func.count()).select_from(table)).scalar() or 0
            if existing and not args.force:
                print(f"[skip] {table.name}: 目标已有 {existing} 行(--force 可强制)")
                continue
            if rows:
                dst_conn.execute(table.insert(), [dict(row) for row in rows])
            total_rows += len(rows)
            print(f"[ok] {table.name}: 迁移 {len(rows)} 行")
    print(f"\n完成:共迁移 {total_rows} 行 → {mysql_url.split('@')[-1]}")
    print(f"原 SQLite 文件保留于: {SQLITE_PATH}")


if __name__ == "__main__":
    sys.exit(main())
