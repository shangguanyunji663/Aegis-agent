# -*- coding: utf-8 -*-
"""百度百科（移动版）心理学词条批量抓取：word → 知识文档。

- 词条正文 = div[data-tag=paragraph] 段落拼接，累计截取 ~1400 字符（≥3 块）
- 用法：.conda/python.exe scripts/crawl_wiki_terms.py --limit 40
- 输出：data/scale-test/v2/wiki-terms.json
"""
import argparse
import json
import re
import time
from pathlib import Path
from urllib.parse import quote

import httpx
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "scale-test" / "v2" / "wiki-terms.json"
H_MOBILE = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

TERMS = [
    # 经典心理效应
    "聚光灯效应", "巴纳姆效应", "达克效应", "皮格马利翁效应", "晕轮效应", "首因效应", "近因效应",
    "锚定效应", "安慰剂效应", "旁观者效应", "破窗效应", "马太效应", "标签效应", "刻板印象威胁",
    "认知失调", "确认偏误", "幸存者偏差", "沉没成本", "损失厌恶", "禀赋效应", "心理账户",
    "框架效应", "羊群效应", "从众心理", "霍桑效应", "习得性无助", "心流", "斯德哥尔摩综合征",
    "吊桥效应", "罗密欧与朱丽叶效应", "情绪ABC理论", "艾宾浩斯遗忘曲线", "近因效应", "自我实现预言",
    # 情绪与心理现象
    "精神内耗", "拖延症", "社交恐惧症", "容貌焦虑", "空心病", "情绪颗粒度", "共情", "边界感",
    "讨好型人格", "回避型依恋", "原生家庭", "煤气灯效应", "情绪价值", "正念", "冥想",
    "非暴力沟通", "心理韧性", "自我关怀", "自卑情结", "优越情结", "防御机制", "心理暗示",
    # 情绪障碍与健康
    "职业倦怠", "季节性情绪失调", "抑郁症", "焦虑症", "强迫症", "惊恐发作", "失眠",
    "创伤后应激障碍", "进食障碍", "双相情感障碍", "社交焦虑障碍", "述情障碍", "微笑抑郁症",
    # 关系与成长
    "依恋理论", "安全型依恋", "焦虑型依恋", "刺猬效应", "多米诺骨牌效应", "蝴蝶效应",
    "南风效应", "自己人效应", "缄默效应", "超限效应", "拆屋效应", "安慰剂",
    "第一印象", "暗示效应", "逆反心理", "怀旧心理", "延迟满足", "内在动机", "成长型思维",
    "心锚", "冥想放松", "生理反馈", "森田疗法", "认知行为疗法", "情绪管理", "社交技巧",
]


def fetch_term(name: str) -> dict | None:
    url = "https://wapbaike.baidu.com/item/" + quote(name)
    try:
        response = httpx.get(url, timeout=18, follow_redirects=True, headers=H_MOBILE)
    except Exception:
        return None
    if response.status_code != 200:
        return None
    response.encoding = "utf-8"
    soup = BeautifulSoup(response.text, "html.parser")
    title_node = soup.find("title")
    title = title_node.get_text(strip=True) if title_node else name
    paragraphs = []
    for para in soup.select('div[data-tag="paragraph"]'):
        for badge in para.select('div[class*="refSup"], sup'):
            badge.decompose()
        text = para.get_text("", strip=True)
        if text:
            paragraphs.append(text)
    if not paragraphs:
        return None
    body = ""
    for text in paragraphs:
        if len(body) >= 1400:
            break
        body += text + "\n"
    body = body.strip()
    if len(body) < 600:
        return None
    return {"name": name, "title": title.split("_")[0].split("（")[0].strip(), "url": url, "body": body}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--offset", type=int, default=0)
    args = parser.parse_args()

    terms = list(dict.fromkeys(TERMS))[args.offset : args.offset + args.limit]
    results, failed = [], []
    for index, term in enumerate(terms, 1):
        data = fetch_term(term)
        if data:
            results.append(data)
            print(f"[{index}/{len(terms)}] OK  {len(data['body']):>5} | {term}", flush=True)
        else:
            failed.append(term)
            print(f"[{index}/{len(terms)}] --  {term}（未收录/失败）", flush=True)
        time.sleep(1.6)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if OUT.exists() and args.offset > 0:
        existing = json.loads(OUT.read_text(encoding="utf-8"))
    merged = existing + results
    OUT.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    lengths = sorted(len(x["body"]) for x in results)
    print(f"\n[saved] {OUT} | 本轮成功 {len(results)} / 失败 {len(failed)} | 累计 {len(merged)}")
    if lengths:
        print(f"body: min={lengths[0]} median={lengths[len(lengths)//2]} max={lengths[-1]}")


if __name__ == "__main__":
    main()
