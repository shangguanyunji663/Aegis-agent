# -*- coding: utf-8 -*-
"""扩库语料爬虫：从公开心理健康平台抓取真实科普文章。

- 源：中国大学生在线（dxs.moe.gov.cn 心理健康栏目）、全国高校心理健康平台（xinli.univs.cn）
- 输出：data/scale-test/raw-crawl/articles-raw.json（[{url,title,site,body}]）
- 用法：.conda/python.exe scripts/crawl_scale_corpus.py --limit 20
"""
import argparse
import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "scale-test" / "raw-crawl"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

LIST_PAGES = [
    ("xinli.univs.cn", "https://xinli.univs.cn/", r'href="(/a/[a-z_]+/\d{6}/\d+\.shtml)(?:\?[^"]*)?"'),
    ("xinli.univs.cn", "https://xinli.univs.cn/pbjy/", r'href="(/a/[a-z_]+/\d{6}/\d+\.shtml)(?:\?[^"]*)?"'),
    ("xinli.univs.cn", "https://xinli.univs.cn/pbjy/xlzs/", r'href="(/a/[a-z_]+/\d{6}/\d+\.shtml)(?:\?[^"]*)?"'),
]


def fetch(url: str) -> httpx.Response:
    response = httpx.get(url, timeout=20, follow_redirects=True, headers=HEADERS)
    if not response.encoding or response.encoding.lower() in {"iso-8859-1", "ascii"}:
        response.encoding = "utf-8"
    return response


def collect_links() -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    seen: set[str] = set()
    for site, list_url, pattern in LIST_PAGES:
        try:
            response = fetch(list_url)
            found = re.findall(pattern, response.text)
            for path in found:
                full = urljoin(list_url, path)
                if full not in seen:
                    seen.add(full)
                    links.append((site, full))
            print(f"[list] {site}: {len(found)} links found")
        except Exception as exc:  # noqa: BLE001
            print(f"[list] {site}: FAIL {type(exc).__name__} {exc}")
        time.sleep(1)
    return links


def extract_article(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "iframe", "noscript"]):
        tag.decompose()
    title_node = soup.find("title")
    title = re.sub(r"\s+", " ", title_node.get_text(strip=True)) if title_node else ""
    for selector in (
        "div.detail-content",
        "div.detail-main-l",
        "div.TRS_Editor",
        "div.wp_articlecontent",
        "div.article-content",
        "div#article-content",
        "div.article",
        "div.content",
        "div#content",
        "div.main-content",
        "article",
    ):
        node = soup.select_one(selector)
        if node is not None:
            text = node.get_text("\n", strip=True)
            if len(text) >= 400:
                return title, text
    best_node = None
    best_len = 0
    for node in soup.find_all(["div", "article", "section"]):
        length = len(node.get_text("", strip=True))
        if length > best_len:
            best_node, best_len = node, length
    if best_node is None:
        return title, ""
    return title, best_node.get_text("\n", strip=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=20, help="本次抓取的文章数量上限")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    links = collect_links()
    print(f"[links] total {len(links)}")
    links = links[: args.limit]

    articles = []
    for index, (site, url) in enumerate(links, 1):
        try:
            response = fetch(url)
            title, body = extract_article(response.text)
            body = re.sub(r"\n{2,}", "\n", body).strip()
            articles.append({"url": url, "title": title, "site": site, "body": body})
            print(f"[{index}/{len(links)}] {len(body):>5} chars | {title[:40]}")
        except Exception as exc:  # noqa: BLE001
            print(f"[{index}/{len(links)}] FAIL {url} -> {type(exc).__name__} {str(exc)[:60]}")
        time.sleep(1.2)

    out = OUT_DIR / "articles-raw.json"
    out.write_text(json.dumps(articles, ensure_ascii=False, indent=2), encoding="utf-8")
    lengths = sorted(len(a["body"]) for a in articles)
    print(f"\n[saved] {out} | {len(articles)} articles")
    if lengths:
        print(f"body length: min={lengths[0]} median={lengths[len(lengths)//2]} max={lengths[-1]}")
        print(f">= 1100 chars: {sum(1 for x in lengths if x >= 1100)}/{len(lengths)}")


if __name__ == "__main__":
    main()
