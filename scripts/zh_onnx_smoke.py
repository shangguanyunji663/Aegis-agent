# -*- coding: utf-8 -*-
"""bge-small-zh-v1.5 ONNX 冒烟：输入输出签名、CLS 池化、语义区分度、速度。

用法: .conda/python.exe scripts/zh_onnx_smoke.py
"""
import sys
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "data" / "models" / "bge-small-zh-onnx"
ONNX_PATH = MODEL_DIR / "onnx" / "model.onnx"
TOKENIZER_PATH = MODEL_DIR / "tokenizer.json"

print("== 1. ONNX 签名 ==")
sess = ort.InferenceSession(str(ONNX_PATH), providers=["CPUExecutionProvider"])
for item in sess.get_inputs():
    print(f"  IN  {item.name} {item.shape} {item.type}")
for item in sess.get_outputs():
    print(f"  OUT {item.name} {item.shape} {item.type}")

print("== 2. Tokenizer ==")
tok = Tokenizer.from_file(str(TOKENIZER_PATH))
tok.enable_truncation(max_length=512)
pad_id = tok.token_to_id("<pad>")
pad_token = "<pad>"
if pad_id is None:
    pad_id = tok.token_to_id("[PAD]")
    pad_token = "[PAD]"
if pad_id is None:
    pad_id = 0
    pad_token = tok.id_to_token(0) or "[PAD]"
tok.enable_padding(pad_id=pad_id, pad_token=pad_token)
print(f"  pad_id={pad_id} pad_token={pad_token!r} vocab={tok.get_vocab_size()}")


def embed(texts):
    encodings = tok.encode_batch(texts)
    ids = np.array([e.ids for e in encodings], dtype=np.int64)
    mask = np.array([e.attention_mask for e in encodings], dtype=np.int64)
    feed = {"input_ids": ids, "attention_mask": mask}
    available = {item.name for item in sess.get_inputs()}
    if "token_type_ids" in available:
        feed["token_type_ids"] = np.zeros_like(ids)
    outputs = sess.run(None, {k: v for k, v in feed.items() if k in available})
    hidden = outputs[0]
    cls = hidden[:, 0, :]
    norm = np.linalg.norm(cls, axis=1, keepdims=True)
    return cls / np.maximum(norm, 1e-12)


print("== 3. 语义区分度 ==")
query = "考试前总是紧张，晚上睡不好，该怎么办"
docs = [
    "考试季压力真实存在，可能出现睡眠变浅，把任务拆成可执行的下一步。",
    "固定起床时间有助于改善睡眠困扰，稳定身体反应。",
    "今天天气真好，适合出门散步。",
]
vectors = embed([query] + docs)
q = vectors[0]
for doc, vec in zip(docs, vectors[1:]):
    cos = float(np.dot(q, vec))
    print(f"  cos={cos:.4f}  {doc[:26]}...")

print("== 4. 速度 ==")
t0 = time.perf_counter()
embed([query])
t1 = time.perf_counter()
print(f"  单条(含首次): {(t1 - t0) * 1000:.0f} ms")
t0 = time.perf_counter()
for _ in range(10):
    embed([query])
t1 = time.perf_counter()
print(f"  单条(热): {(t1 - t0) / 10 * 1000:.1f} ms")
t0 = time.perf_counter()
embed(docs)
t1 = time.perf_counter()
print(f"  批量3条(热): {(t1 - t0) * 1000:.1f} ms")
