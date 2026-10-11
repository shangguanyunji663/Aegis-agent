# -*- coding: utf-8 -*-
"""组装 200 块规模的实验知识库（隔离于 data/scale-test/，不触碰生产 knowledge/）。

- 输入：data/scale-test/batches/batch-*.json
  每批结构：{"docs": [{"name": "...", "topic": "...", "risk_level": "...", "body": "..."}]}
- 输出：data/scale-test/knowledge-200/（原库 24 篇拷贝 + 合成文档，CRLF 落盘）
- 校验：重名检查、body 长度与切块统计（复用 app.rag.chunking 的精确逻辑）
用法：.conda/python.exe scripts/build_scale_library.py
"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.rag.chunking import chunk_text, parse_knowledge_document  # noqa: E402

SRC_KNOWLEDGE = ROOT / "knowledge"
BATCH_DIR = ROOT / "data" / "scale-test" / "batches"
OUT_DIR = ROOT / "data" / "scale-test" / "knowledge-200"
CHUNK_SIZE, CHUNK_OVERLAP = 512, 64
LAST_REVIEWED = "2026-10-10"


def build() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.md"):
        stale.unlink()

    originals = sorted(SRC_KNOWLEDGE.glob("*.md"))
    original_names = {path.name for path in originals}
    for path in originals:
        shutil.copy2(path, OUT_DIR / path.name)

    docs = []
    for batch_path in sorted(BATCH_DIR.glob("batch-*.json")):
        if "-append" in batch_path.name:
            continue
        payload = json.loads(batch_path.read_text(encoding="utf-8"))
        docs.extend(payload["docs"])

    seen = set(original_names)
    for doc in docs:
        name = doc["name"]
        assert name not in seen, f"duplicate name: {name}"
        seen.add(name)
        frontmatter = (
            "---\n"
            f"topic: {doc['topic']}\n"
            "audience: student\n"
            f"risk_level: {doc['risk_level']}\n"
            "source_type: synthetic_scale_test\n"
            f"last_reviewed: {LAST_REVIEWED}\n"
            "---\n\n"
        )
        full = frontmatter + doc["body"].strip() + "\n"
        (OUT_DIR / name).write_bytes(full.encode("utf-8").replace(b"\n", b"\r\n"))

    files = sorted(OUT_DIR.glob("*.md"))
    print(f"== 组装完成：{len(files)} 个文件（原库 {len(originals)} + 合成 {len(docs)}）")
    total_chunks = 0
    short, long_ = [], []
    for path in files:
        content = path.read_text(encoding="utf-8")
        _meta, body = parse_knowledge_document(path.name, content)
        chunks = chunk_text(body, CHUNK_SIZE, CHUNK_OVERLAP)
        total_chunks += len(chunks)
        if path.name not in original_names:
            if len(chunks) < 2:
                short.append((path.name, len(body)))
            elif len(chunks) > 2:
                long_.append((path.name, len(body)))
    print(f"== 预计总块数：{total_chunks}")
    if short:
        print(f"== 仅 1 块的合成文档 {len(short)} 篇（body 不足 513 字符，需加长）：")
        for name, length in short[:25]:
            print(f"   {name}: body={length}")
    if long_:
        print(f"== 超 2 块的合成文档 {len(long_)} 篇（body 超 960 字符，需缩短）：")
        for name, length in long_[:25]:
            print(f"   {name}: body={length}")


if __name__ == "__main__":
    build()
