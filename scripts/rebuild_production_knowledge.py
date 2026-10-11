# -*- coding: utf-8 -*-
"""生产知识库完整重建：knowledge/ 目录 → DB 文本块 + Chroma 向量索引。

与 rebuild_production_vector.py（仅重建向量）不同：本脚本会重新灌入目录下的全部文档。
用法：.conda/python.exe scripts/rebuild_production_knowledge.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.database import build_engine, build_session_factory, create_schema
from app.repository import DatabaseStore

settings = get_settings()
print(f"[config] embedding_provider = {settings.embedding_provider}")
print(f"[config] vector_backend = {settings.vector_backend} | chroma_dir = {settings.chroma_dir}")
print(f"[config] collection = {settings.chroma_collection_name} | fusion_mode = {settings.knowledge_fusion_mode}")
print(f"[config] rerank_engine = {settings.knowledge_rerank_engine} | lambda = {getattr(settings, 'knowledge_ce_fusion_lambda', '?')}")
print(f"[config] knowledge_dir = {settings.resolve_path(settings.knowledge_dir)}")

schema_engine = build_engine(settings)
create_schema(schema_engine)
session_factory = build_session_factory(settings)
store = DatabaseStore(session_factory, settings=settings)

before = store.vector_backend.count()
print(f"[before] chunks in vector index = {before}")

result = store.rebuild_knowledge_dir(settings.resolve_path(settings.knowledge_dir))
print(f"[rebuild] chunks = {result['chunks']}")
print(f"[after]  chunks in vector index = {store.vector_backend.count()}")

for query in [
    "考试前紧张睡不着怎么办",
    "和朋友闹矛盾心里很难受",
    "总是觉得自己不够好",
    "想了解聚光灯效应",
]:
    print(f"\n[smoke] {query}")
    for item in store.search_knowledge(query, 3):
        print(f"   {item['score']} | {item['source']} | {item['content'][:44]}")

schema_engine.dispose()
getattr(store.db_factory, "kw", {}).get("bind").dispose()
backend = store.vector_backend
client = getattr(backend, "client", None)
if client is not None and callable(getattr(client, "close", None)):
    client.close()
print("\nREBUILD_KNOWLEDGE_DONE")
