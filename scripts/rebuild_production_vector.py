# -*- coding: utf-8 -*-
"""生产向量索引重建：把知识块嵌入（local-zh，bge-small-zh-v1.5）写入新 collection。

- 使用真实 .env 配置（MySQL 数据源 + data/chroma 持久化目录）
- 仅重建向量：读 knowledge_chunks → 嵌入 → 写入当前 CHROMA_COLLECTION_NAME 指向的集合
- 不动 MySQL 数据；旧集合（aegis_knowledge，MiniLM 384 维）完整保留，可随时回滚
- 回滚方式：恢复 .env 的 EMBEDDING_PROVIDER=local 与 CHROMA_COLLECTION_NAME=aegis_knowledge

用法（确认配置后执行）：.conda/python.exe scripts/rebuild_production_vector.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.database import build_engine, build_session_factory
from app.repository import DatabaseStore

settings = get_settings()
print(f"[config] embedding_provider = {settings.embedding_provider}")
print(f"[config] vector_backend = {settings.vector_backend} | chroma_dir = {settings.chroma_dir}")
print(f"[config] collection = {settings.chroma_collection_name} | fusion_mode = {settings.knowledge_fusion_mode}")

engine = build_engine(settings)
session_factory = build_session_factory(settings)
store = DatabaseStore(session_factory, settings=settings)

backend = store.vector_backend
print(f"[before] backend={backend.backend_name} model={getattr(backend, 'embedding_model', '?')} count={backend.count()}")

result = store.rebuild_vector_index()
print(f"[rebuild] {result}")
print(
    f"[after] count={store.vector_backend.count()} "
    f"model={getattr(store.vector_backend, 'embedding_model', '?')}"
)

print("\n[smoke] search: 考试前紧张睡不着怎么办")
for item in store.search_knowledge("考试前紧张睡不着怎么办", 3):
    print(f"  {item['score']} | {item['source']} | {item['content'][:24]}")

engine.dispose()
getattr(store.db_factory, "kw", {}).get("bind").dispose()
print("\nPRODUCTION_REBUILD_DONE")
