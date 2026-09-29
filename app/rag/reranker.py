"""Cross-Encoder 重排引擎：ONNX CPU 推理，服务「粗排 top-N → 模型精排」两段式。

设计约定（对应学习指南 9.7.0 Q3）：
- 词法 rerank 保持「全库重打分」现状不变；本引擎只在
  ``KNOWLEDGE_RERANK_ENGINE=cross_encoder`` 时被 ``store.search_knowledge`` 调用。
- 模型文件按目录组织：``model.onnx`` 或 ``model_quantized.onnx`` + ``tokenizer.json``。
  tokenizer.json 必须与 onnx 同源（含 pair 模板，用于 (query, doc) 成对编码）。
- 任何加载/推理失败都向上抛异常，由调用方回退词法公式并记录原因——检索永不因此中断。
- 会话与分词器进程内缓存（懒加载一次）。
"""
from __future__ import annotations

import math
from pathlib import Path

from app.entities import KnowledgeChunk

_SESSION = None
_TOKENIZER = None
_LOAD_ERROR = ""
_MAX_SEQ_LEN = 512


def reset_cache() -> None:
    """清空进程内模型缓存（测试用）。"""
    global _SESSION, _TOKENIZER, _LOAD_ERROR
    _SESSION = None
    _TOKENIZER = None
    _LOAD_ERROR = ""


def is_loaded() -> bool:
    return _SESSION is not None


def _load(model_dir: str) -> None:
    global _SESSION, _TOKENIZER, _LOAD_ERROR
    if _SESSION is not None:
        return
    if _LOAD_ERROR:
        raise RuntimeError(_LOAD_ERROR)
    path = Path(model_dir)
    onnx_path = path / "model_quantized.onnx"
    if not onnx_path.exists():
        onnx_path = path / "model.onnx"
    tokenizer_path = path / "tokenizer.json"
    if not onnx_path.exists() or not tokenizer_path.exists():
        _LOAD_ERROR = (
            f"cross-encoder model incomplete under {path}: need (model.onnx|model_quantized.onnx) + tokenizer.json"
        )
        raise RuntimeError(_LOAD_ERROR)
    try:
        import onnxruntime as ort
        from tokenizers import Tokenizer

        tokenizer = Tokenizer.from_file(str(tokenizer_path))
        tokenizer.enable_truncation(max_length=_MAX_SEQ_LEN)
        session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    except Exception as exc:  # noqa: BLE001 - 统一转译为回退信号
        _LOAD_ERROR = f"cross-encoder load failed: {exc}"
        raise RuntimeError(_LOAD_ERROR) from exc
    _SESSION = session
    _TOKENIZER = tokenizer


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    exp_value = math.exp(value)
    return exp_value / (1.0 + exp_value)


def _score_pairs(query: str, texts: list[str]) -> list[float]:
    import numpy as np

    pair_inputs = [(query, text) for text in texts]
    try:
        encodings = _TOKENIZER.encode_batch(pair_inputs)
    except Exception:
        # tokenizer.json 无 pair 模板时退化为单序列拼接（query 与 doc 以特殊 token 分隔由模板保证的场景不支持）
        encodings = [_TOKENIZER.encode(f"{query} [SEP] {text}") for text in texts]
    # 手动 padding 成规整矩阵:onnxruntime 无法从锯齿状 list[list[int]] 创建张量
    max_len = max(len(encoding.ids) for encoding in encodings)
    pad_id = _TOKENIZER.token_to_id("<pad>") or 1
    input_ids = np.full((len(encodings), max_len), pad_id, dtype=np.int64)
    attention_mask = np.zeros((len(encodings), max_len), dtype=np.int64)
    for index, encoding in enumerate(encodings):
        length = len(encoding.ids)
        input_ids[index, :length] = encoding.ids
        attention_mask[index, :length] = encoding.attention_mask
    available = {item.name for item in _SESSION.get_inputs()}
    feed = {"input_ids": input_ids, "attention_mask": attention_mask}
    feed = {name: value for name, value in feed.items() if name in available}
    output = _SESSION.run(None, feed)[0]
    logits = [float(row[0]) if hasattr(row, "__len__") else float(row) for row in output]
    return [_sigmoid(value) for value in logits]


def cross_encoder_rerank(
    query: str, ranked: list[tuple[KnowledgeChunk, float]], model_dir: str
) -> list[tuple[KnowledgeChunk, float]]:
    """对 (chunk, base_score) 列表做 Cross-Encoder 精排，返回同结构新列表。

    分数被替换为模型相关性分（0~1）；调用方负责 top-N 截断与失败回退。
    """
    if not ranked:
        return []
    _load(model_dir)
    texts = [(chunk.content or "")[:2000] for chunk, _ in ranked]
    scores = _score_pairs(query, texts)
    return [(chunk, score) for (chunk, _), score in zip(ranked, scores)]
