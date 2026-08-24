"""第二轮训练数据准备：补充隐式高危样本，重新平衡 train/dev split。"""
from __future__ import annotations

import json
import hashlib
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRAINING_SRC = ROOT / "training" / "src"
if str(TRAINING_SRC) not in sys.path:
    sys.path.insert(0, str(TRAINING_SRC))

from aegis_training.data_contract import (
    DataContractError,
    RiskSample,
    label_distribution,
    write_jsonl,
    normalize_message,
    text_hash,
)
from aegis_training.leakage_guard import assert_no_final_holdout_leakage
from aegis_training.source_ingest import (
    load_hongzhi_candidate_pool,
    load_project_candidate_pool,
)

EXPLICIT_HIGH_WORDS = frozenset({
    "自杀", "割腕", "跳楼", "上吊", "跳下去", "遗书", "安眠药",
    "去死", "想死", "赴死", "自残", "自杀未遂", "杀了我",
    "勒死", "溺死", "烧炭", "煤气", "跳河", "跳海",
    "服毒", "喝药", "毒药", "跳江", "坠楼",
})

EXPLICIT_THIRD_PARTY = re.compile(
    r"(新闻|报道|看到|刷到|朋友|同学|室友|家人|她|他|他们|电视剧|电影|小说|论文|微博|热搜).{0,30}"
    r"(自杀|轻生|跳楼|割腕|自残|死亡|去世|想死|离开)"
)

IMPLICIT_HIGH_PATTERNS = re.compile(
    r"(从没出生|不该来|不该活|消失|撑不下去|撑不住|坚持不下去|"
    r"永远停|不想面对|结束|放弃|没意义|没意思|活着累|"
    r"不配活着|多余|离开这个世界|走了|解脱|不在了|一了百了|"
    r"不想活|活不下去|没希望|绝望|活够|累了|"
    r"想睡过去|永远睡|不要醒来|不再醒来|不愿醒来|结束生命|"
    r"离开人世|告别|最后一|承受不了|扛不住|崩溃|"
    r"没有意义|没有意思|不如死了|死了算了|好想死|想去死|"
    r"活着的意义|活着干吗|活着干嘛|活着受罪|活着痛苦|"
    r"人生没有意义|人生毫无意义)"
)

SYNTHETIC_SAMPLES = [
    # ===== 从没出生过 (wish never born) =====
    RiskSample("synth-impl-neverborn-01", "我有时候希望自己从没出生过", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-neverborn-02", "真希望自己从没来到这个世界", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-neverborn-03", "要是从来没出生就好了", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-neverborn-04", "我宁愿自己从没被生下来", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-neverborn-05", "如果可以选择，我不想来到这个世界", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-neverborn-06", "有时候真希望自己一开始就不存在", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-neverborn-07", "从没出生过该多好，就不用受这些苦了", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-neverborn-08", "真希望自己从没存在过", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-neverborn-09", "要是妈当初没生我就好了", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    # ===== 消失大家更好 (disappear better) =====
    RiskSample("synth-impl-disappear-01", "我总在想如果自己消失大家会不会更好", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-disappear-02", "也许我消失了，对所有人都好", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-disappear-03", "没有我，大家会过得更轻松吧", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-disappear-04", "如果我从这个世界上消失，谁会难过呢", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-disappear-05", "我消失的话，应该没人会在意吧", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-disappear-06", "是不是我走了，大家就都解脱了", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-disappear-07", "有时候觉得，没有我大家会更好", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-disappear-08", "我消失了对谁都好，不是吗", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-disappear-09", "我离开的话，大家都会轻松一些吧", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    # ===== 不该继续活下去 (shouldn't live) =====
    RiskSample("synth-impl-shouldnt-01", "我觉得自己不该继续活下去了", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-shouldnt-02", "像我这样的人，活着有什么意义", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-shouldnt-03", "我真的不配活着，浪费空气", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-shouldnt-04", "活着好累，也许不该再坚持了", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-shouldnt-05", "像我这样失败的人，活着干嘛", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-shouldnt-06", "真的不想再活下去了，没意思", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-shouldnt-07", "我这种人活着就是给别人添麻烦", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-shouldnt-08", "我这样的人有什么资格活着", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-shouldnt-09", "像我这样一无是处的人，活着干什么", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    # ===== 撑不下去 (can't hold on) =====
    RiskSample("synth-impl-canthold-01", "我撑不下去了，真的不想再继续了", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-canthold-02", "我真的撑不住了，好想放弃一切", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-canthold-03", "快撑不住了，感觉自己已经到了极限", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-canthold-04", "我真的坚持不下去了，太累了", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-canthold-05", "撑不住了，好想就这样算了", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-canthold-06", "我已经到极限了，真的撑不下去了", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-canthold-07", "感觉自己快撑不住了，每天都在崩溃边缘", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-canthold-08", "我真的撑不下去了，好想停下来", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-canthold-09", "坚持好难，我真的撑不住了", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    # ===== 永远停下 (stop forever) =====
    RiskSample("synth-impl-stop-01", "我总想，想让这一切停下来永远地", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-stop-02", "我好想让这一切永远地停下", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-stop-03", "真想按下暂停键，让一切停止", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-stop-04", "好想让这一切都停下来，永远不要再继续", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-stop-05", "希望时间停止，一切都结束", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-stop-06", "想让这痛苦的一切都停下来", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-stop-07", "好想停止这一切，永远地", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-stop-08", "让这一切都结束吧，我受不了了", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    # ===== 不想面对明天 (don't face tomorrow) =====
    RiskSample("synth-impl-tomorrow-01", "我不想再面对明天了", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-tomorrow-02", "不想醒来面对新的一天", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-tomorrow-03", "害怕天亮，不想面对明天", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-tomorrow-04", "如果可以，我想永远沉睡，不要醒来", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-tomorrow-05", "不想看到明天的太阳，太累了", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-tomorrow-06", "每天醒来都是一种折磨，不想再面对", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-tomorrow-07", "好害怕明天到来，真的不想面对", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-tomorrow-08", "我不想过明天了，今天就结束吧", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    # ===== 结束对大家都好 (ending better) =====
    RiskSample("synth-impl-ending-01", "我在想，是不是结束了对大家都好", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-ending-02", "也许结束一切才是最好的选择", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-ending-03", "是不是结束了，大家就都解脱了", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-ending-04", "结束这一切，对所有人都好吧", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-ending-05", "我在想，如果我结束了，大家会不会更轻松", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-ending-06", "结束也许是最好的出路", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-ending-07", "是不是只有结束了，一切才会好起来", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-ending-08", "结束这一切，对谁都好", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    # ===== 放弃念头 (giving up) =====
    RiskSample("synth-impl-giveup-01", "我每天都在和想放弃的念头搏斗", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-giveup-02", "每天都在想放弃，真的好累", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-giveup-03", "放弃的念头一直在脑子里挥之不去", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-giveup-04", "我快被这些想放弃的想法淹没了", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-giveup-05", "每天都在挣扎，好想就这样放弃", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-giveup-06", "那些放弃的念头越来越强烈了", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-giveup-07", "我快要撑不住了，放弃的念头好强烈", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-giveup-08", "好想就这样放弃一切，什么都不管了", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    # ===== 活着没意义 (meaningless) =====
    RiskSample("synth-impl-meaningless-01", "我觉得活着真的一点意义都没有", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-meaningless-02", "每天都一样，活着有什么意思", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-meaningless-03", "我找不到活着的意义，好迷茫", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-meaningless-04", "这样活着有什么意义呢，不如算了", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-meaningless-05", "人生毫无意义，我真的好累", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-meaningless-06", "活着到底为了什么，我真的找不到答案", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-meaningless-07", "每一天都是重复，这样的活着有什么意义", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-meaningless-08", "我真的找不到活下去的理由了", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-meaningless-09", "人生没有意义，活着就是受罪", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    # ===== 想解脱 (want relief) =====
    RiskSample("synth-impl-relief-01", "好想解脱，真的太累了", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-relief-02", "什么时候才能解脱，我真的好累", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-relief-03", "活着太痛苦了，什么时候才能结束", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-relief-04", "我受够了，真的不想再坚持了", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-relief-05", "好想逃，逃到一个没有痛苦的地方", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-relief-06", "真的受够了，好想一了百了", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-relief-07", "好想彻底消失，再也没有痛苦", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-relief-08", "我只想安静地离开，不再有烦恼", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
    RiskSample("synth-impl-relief-09", "太痛苦了，好想结束这一切", "high", "存在自身自伤自杀意向", "synthetic-implicit-high", source_version="v1", label_method="synthetic", speaker_scope="self"),
]


def _is_self_implicit_high(text: str) -> bool:
    """检查文本是否包含自身隐式高危表达（非第三方、非显式自杀词）。"""
    if EXPLICIT_THIRD_PARTY.search(text):
        return False
    # Must have implicit high pattern
    if not IMPLICIT_HIGH_PATTERNS.search(text):
        return False
    # Must not be ONLY explicit words
    explicit_count = sum(1 for w in EXPLICIT_HIGH_WORDS if w in text)
    if explicit_count >= 2:
        return False
    return True


def extract_hongzhiq_implicit_high(source_root: Path) -> list[RiskSample]:
    """从 HongzhiQ 低风险标签中提取隐式高危表达。"""
    path = source_root / "data" / "suicide" / "suicide_train_LLM.csv"
    import csv
    rows = list(csv.DictReader(path.open(encoding="utf-8", newline=""), delimiter="\t"))
    samples: list[RiskSample] = []
    for row in rows:
        text = (row.get("comment") or "").strip()
        label = (row.get("label") or "").strip()
        if not text or label not in {"0", "1"}:
            continue
        if label == "0" and _is_self_implicit_high(text):
            samples.append(
                RiskSample(
                    sample_id=f"hongzhi-implhigh-{row['id']}",
                    message=text,
                    risk_level="high",
                    reason="存在自身自伤自杀意向",
                    source="hongzhiq-suicide-implicit",
                    source_version="SupervisedVsLLM-EfficacyEval@78fb4d1",
                    label_method="synthetic",
                    review_status="not_reviewed",
                    annotator="weak-risk-mapping-v2",
                    speaker_scope="self",
                    adjudication_note="extracted from low-label data; implicit high-risk expression",
                )
            )
    return samples


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Prepare round 2 risk SFT data with more implicit high samples")
    parser.add_argument("--external-root", type=Path, default=Path("C:/Users/17536/AppData/Local/Temp/hongzhi-eval"))
    parser.add_argument("--output-root", type=Path, default=Path("D:/AegisTraining/data/risk_sft_v2_round2"))
    parser.add_argument("--train-size", type=int, default=720)
    parser.add_argument("--dev-size", type=int, default=120)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    # 1. Load existing data
    print("Loading existing candidate pool...")
    existing = load_hongzhi_candidate_pool(args.external_root, include_validation=True)
    project_base = load_project_candidate_pool(ROOT)
    existing.extend(project_base)
    print(f"  Project base: {len(project_base)}")
    print(f"  Existing candidates: {len(existing)}")

    # 2. Add synthetic implicit high samples
    print(f"Adding {len(SYNTHETIC_SAMPLES)} synthetic implicit high samples...")
    existing.extend(SYNTHETIC_SAMPLES)

    # 3. Extract implicit high samples from HongzhiQ low-label data
    hongzhiq_impl = extract_hongzhiq_implicit_high(args.external_root)
    print(f"Extracted {len(hongzhiq_impl)} implicit high samples from HongzhiQ low-label data...")
    existing.extend(hongzhiq_impl)

    # 4. Check for stress holdout leakage
    print("Checking for stress holdout leakage...")
    try:
        assert_no_final_holdout_leakage(existing)
    except AssertionError as exc:
        print(f"  LEAKAGE DETECTED: {exc}")
        return 2
    print("  No leakage detected.")

    # 5. Stratified split
    train_size = args.train_size
    dev_size = args.dev_size

    # Count by level
    groups = defaultdict(list)
    for sample in existing:
        groups[sample.risk_level].append(sample)

    for level in ["low", "medium", "high"]:
        print(f"  {level}: {len(groups[level])} candidates")

    # Use deterministic ordering
    def stable_order(samples, seed, label):
        return sorted(
            samples,
            key=lambda s: hashlib.sha256(f"{seed}:{label}:{s.sample_id}".encode("utf-8")).hexdigest(),
        )

    for level in groups:
        groups[level] = stable_order(groups[level], args.seed, level)

    # Round 2: increase high proportion to improve implicit high recall
    # Train: 240 low, 240 medium, 240 high
    # Dev: 40 low, 40 medium, 40 high
    levels = ["low", "medium", "high"]
    train_quotas = {level: train_size // 3 for level in levels}
    dev_quotas = {level: dev_size // 3 for level in levels}

    train = []
    dev = []
    for level in levels:
        needed = train_quotas[level] + dev_quotas[level]
        available = len(groups[level])
        if available < needed:
            print(f"  WARNING: only {available} {level} samples, need {needed}")
            # Use all available
            train.extend(groups[level][:train_quotas[level]])
            dev.extend(groups[level][train_quotas[level]:needed])
        else:
            train.extend(groups[level][:train_quotas[level]])
            dev.extend(groups[level][train_quotas[level]:needed])

    print(f"\nTrain: {len(train)} ({label_distribution(train)})")
    print(f"Dev: {len(dev)} ({label_distribution(dev)})")

    # 6. Write output
    args.output_root.mkdir(parents=True, exist_ok=True)
    train_records = [s.to_sft_record() for s in train]
    dev_records = [s.to_sft_record() for s in dev]

    write_jsonl(train_records, args.output_root / "train.jsonl")
    write_jsonl(dev_records, args.output_root / "dev.jsonl")

    # 7. Manifest
    manifest = {
        "round": 2,
        "train_count": len(train),
        "dev_count": len(dev),
        "train_label_distribution": dict(label_distribution(train)),
        "dev_label_distribution": dict(label_distribution(dev)),
        "train_source_distribution": dict(Counter(s.source for s in train)),
        "dev_source_distribution": dict(Counter(s.source for s in dev)),
        "synthetic_implicit_high_added": len(SYNTHETIC_SAMPLES),
        "hongzhiq_implicit_high_extracted": len(hongzhiq_impl),
        "seed": args.seed,
    }
    (args.output_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nOutput written to {args.output_root}")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())