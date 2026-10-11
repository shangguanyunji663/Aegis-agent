"""本地中文嵌入引擎：bge-small-zh-v1.5（ONNX，CPU 推理）。

设计约定（与 app/rag/reranker.py 同模式）：
- 模型目录按 transformers.js 转换版组织：``onnx/model.onnx`` + ``tokenizer.json``。
- 池化：CLS（``last_hidden_state[:, 0]``）+ L2 归一化——bge 官方检索用法；
  query 与文档共用同一编码口径（v1.5 对检索指令前缀非必需）。
- 会话与分词器进程内缓存（懒加载一次）。
- 任何加载/推理失败都向上抛异常，由调用方回退并记录原因——检索永不因此中断。
"""
from __future__ import annotations

from pathlib import Path

_SESSION = None
_TOKENIZER = None
_LOAD_ERROR = ""
_MODEL_DIR = ""
_MAX_SEQ_LEN = 512


def reset_cache() -> None:
    """清空进程内模型缓存（测试用）。"""
    global _SESSION, _TOKENIZER, _LOAD_ERROR, _MODEL_DIR
    _SESSION = None
    _TOKENIZER = None
    _LOAD_ERROR = ""
    _MODEL_DIR = ""


def is_loaded() -> bool:
    return _SESSION is not None


def _load(model_dir: str) -> None:
    global _SESSION, _TOKENIZER, _LOAD_ERROR, _MODEL_DIR
    if _SESSION is not None and _MODEL_DIR == model_dir:
        return
    if _LOAD_ERROR and _MODEL_DIR == model_dir:
        raise RuntimeError(_LOAD_ERROR)
    path = Path(model_dir)
    onnx_path = path / "onnx" / "model.onnx"
    if not onnx_path.exists():
        onnx_path = path / "model.onnx"
    tokenizer_path = path / "tokenizer.json"
    if not onnx_path.exists() or not tokenizer_path.exists():
        _LOAD_ERROR = (
            f"zh embedding model incomplete under {path}: need (onnx/model.onnx|model.onnx) + tokenizer.json"
        )
        _MODEL_DIR = model_dir
        raise RuntimeError(_LOAD_ERROR)
    try:
        import onnxruntime as ort
        from tokenizers import Tokenizer

        tokenizer = Tokenizer.from_file(str(tokenizer_path))
        tokenizer.enable_truncation(max_length=_MAX_SEQ_LEN)
        pad_id = tokenizer.token_to_id("<pad>")
        pad_token = "<pad>"
        if pad_id is None:
            pad_id = tokenizer.token_to_id("[PAD]")
            pad_token = "[PAD]"
        if pad_id is None:
            pad_id = 0
            pad_token = tokenizer.id_to_token(0) or "[PAD]"
        tokenizer.enable_padding(pad_id=pad_id, pad_token=pad_token)
        session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    except Exception as exc:  # noqa: BLE001 - 统一转译为回退信号
        _LOAD_ERROR = f"zh embedding model load failed: {exc}"
        _MODEL_DIR = model_dir
        raise RuntimeError(_LOAD_ERROR) from exc
    _SESSION = session
    _TOKENIZER = tokenizer
    _LOAD_ERROR = ""
    _MODEL_DIR = model_dir


def embed_texts(texts: list[str], model_dir: str) -> list[list[float]]:
    """将文本批量编码为 L2 归一化的 512 维向量（CLS 池化）。"""
    if not texts:
        return []
    _load(model_dir)
    import numpy as np

    normalized = [text if text.strip() else " " for text in texts]
    encodings = _TOKENIZER.encode_batch(normalized)
    input_ids = np.array([encoding.ids for encoding in encodings], dtype=np.int64)
    attention_mask = np.array([encoding.attention_mask for encoding in encodings], dtype=np.int64)
    feed = {"input_ids": input_ids, "attention_mask": attention_mask}
    available = {item.name for item in _SESSION.get_inputs()}
    if "token_type_ids" in available:
        feed["token_type_ids"] = np.zeros_like(input_ids)
    outputs = _SESSION.run(None, {key: value for key, value in feed.items() if key in available})
    hidden = outputs[0]
    cls = hidden[:, 0, :]
    norm = np.linalg.norm(cls, axis=1, keepdims=True)
    vectors = cls / np.maximum(norm, 1e-12)
    return [[float(value) for value in row] for row in vectors]


class LocalZhEmbeddingFunction:
    """可调用嵌入函数：实例化一次，供向量后端（与评测脚本）复用。"""

    def __init__(self, model_dir: str):
        self.model_dir = model_dir
        self.model_name = "bge-small-zh-v1.5"

    def __call__(self, input: list[str]) -> list[list[float]]:
        return embed_texts(list(input), self.model_dir)
