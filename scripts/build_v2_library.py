# -*- coding: utf-8 -*-
"""组装 v2 实验库：原 24 篇 + 爬取素材（crawled_univs）+ AI 扩充（ai_expanded）。

- 输入：knowledge/（原库）、data/scale-test/raw-crawl/articles-kept.json、
        data/scale-test/v2/ai-batches/*.json
- 输出：data/scale-test/knowledge-v2/（CRLF 落盘）
"""
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.rag.chunking import chunk_text, parse_knowledge_document  # noqa: E402

SRC = ROOT / "knowledge"
RAW_KEPT = ROOT / "data" / "scale-test" / "raw-crawl" / "articles-raw.json"
AI_DIR = ROOT / "data" / "scale-test" / "v2" / "ai-batches"
OUT = ROOT / "data" / "scale-test" / "knowledge-v2"
LAST_REVIEWED = "2026-10-10"


def clean_title(raw_title: str) -> str:
    return raw_title.split(" - ")[0].strip()


def clean_body(text: str) -> str:
    text = re.sub(r"\n{2,}", "\n", text).strip()
    # 去尾部图片/供图说明
    text = re.sub(r"[（(]?图[为片][^。\n]{0,50}(供图|提供|摄)[）)]?[。]?\s*$", "", text).strip()
    text = re.sub(r"[（(]?本文图片[^。\n]{0,50}[）)]?[。]?\s*$", "", text).strip()
    return text


def write_md(path: Path, meta: dict, title: str, body: str) -> None:
    lines = ["---"]
    for key, value in meta.items():
        lines.append(f"{key}: {value}")
    lines.append("---")
    lines.append("")
    if title and not body.lstrip().startswith("#"):
        lines.append(f"# {title}")
        lines.append("")
    full = "\n".join(lines) + body.strip() + "\n"
    path.write_bytes(full.encode("utf-8").replace(b"\n", b"\r\n"))


def build() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for stale in OUT.glob("*.md"):
        stale.unlink()

    originals = sorted(SRC.glob("*.md"))
    original_names = {p.name for p in originals}
    for p in originals:
        shutil.copy2(p, OUT / p.name)

    # 1) 爬取素材
    kept = json.loads(RAW_KEPT.read_text(encoding="utf-8"))
    seen_titles: set[str] = set()
    crawled_count = 0
    for article in kept:
        title = clean_title(article["title"])
        if title in seen_titles:
            continue
        seen_titles.add(title)
        body = clean_body(article["body"])
        name = f"c{article['url'].rstrip('/').split('/')[-1].replace('.shtml', '')}-crawled.md"
        meta = {
            "topic": "crawled_univs",
            "audience": "student",
            "risk_level": "low",
            "source_type": "crawled_univs",
            "origin": article["url"],
            "last_reviewed": LAST_REVIEWED,
        }
        write_md(OUT / name, meta, title, body)
        crawled_count += 1

    # 2) AI 扩充
    ai_docs = []
    for batch in sorted(AI_DIR.glob("batch-*.json")):
        if "-append" in batch.name:
            continue
        ai_docs.extend(json.loads(batch.read_text(encoding="utf-8"))["docs"])
    for doc in ai_docs:
        name = doc["name"]
        assert name not in original_names and not (OUT / name).exists(), f"duplicate: {name}"
        meta = {
            "topic": doc["topic"],
            "audience": "student",
            "risk_level": doc["risk_level"],
            "source_type": "ai_expanded",
            "last_reviewed": LAST_REVIEWED,
        }
        write_md(OUT / name, meta, "", doc["body"])

    # 3) 百科词条
    wiki_path = ROOT / "data" / "scale-test" / "v2" / "wiki-terms.json"
    wiki_count = 0
    if wiki_path.exists():
        for idx, term in enumerate(json.loads(wiki_path.read_text(encoding="utf-8")), 1):
            name = f"wiki-{idx:03d}.md"
            if (OUT / name).exists():
                continue
            meta = {
                "topic": "psychology_wiki",
                "audience": "student",
                "risk_level": "low",
                "source_type": "wikibaike_mobile",
                "origin": term["url"],
                "last_reviewed": LAST_REVIEWED,
            }
            write_md(OUT / name, meta, term["title"], term["body"])
            wiki_count += 1

    # 4) 统计
    files = sorted(OUT.glob("*.md"))
    total_blocks = 0
    short_ai = []
    for p in files:
        content = p.read_text(encoding="utf-8")
        _meta, body = parse_knowledge_document(p.name, content)
        blocks = chunk_text(body, 512, 64)
        total_blocks += len(blocks)
        if p.name not in original_names and "crawled" not in p.name and len(blocks) < 3:
            short_ai.append((p.name, len(body), len(blocks)))
    print(
        f"== v2 库：{len(files)} 个文件（原 {len(originals)} + 爬取 {crawled_count} + AI {len(ai_docs)} + 词条 {wiki_count}）"
    )
    print(f"== 总块数：{total_blocks}")
    if short_ai:
        print(f"== AI 文档不足 3 块的 {len(short_ai)} 篇：")
        for name, length, blocks in short_ai:
            print(f"   {name}: {length} chars / {blocks} 块")


if __name__ == "__main__":
    build()
