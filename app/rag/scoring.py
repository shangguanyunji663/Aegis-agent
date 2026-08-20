"""混合检索打分:BM25、词法重排、向量+BM25 融合与邻块扩展。"""
from __future__ import annotations

import math
import re
from typing import Hashable

from app.entities import KnowledgeChunk
from app.rag.text import counts, token_cosine, tokenize


def bm25_scores(query: str, chunks: list[KnowledgeChunk]) -> dict[int, float]:
    query_terms = counts(tokenize(query))
    if not query_terms or not chunks:
        return {}
    documents = []
    doc_freqs: dict[str, int] = {}
    for chunk in chunks:
        if chunk.id is None:
            continue
        token_counts = counts(tokenize(chunk.content))
        documents.append((chunk.id, token_counts, sum(token_counts.values())))
        for term in token_counts:
            doc_freqs[term] = doc_freqs.get(term, 0) + 1
    total_docs = len(documents)
    if total_docs == 0:
        return {}
    average_length = sum(length for _, _, length in documents) / total_docs or 1.0
    k1 = 1.5
    b = 0.75
    scores: dict[int, float] = {}
    for chunk_id, token_counts, doc_length in documents:
        score = 0.0
        length_norm = k1 * (1.0 - b + b * doc_length / average_length)
        for term, query_frequency in query_terms.items():
            term_frequency = token_counts.get(term, 0)
            if term_frequency == 0:
                continue
            doc_frequency = doc_freqs.get(term, 0)
            idf = math.log(1.0 + (total_docs - doc_frequency + 0.5) / (doc_frequency + 0.5))
            query_boost = 1.0 + math.log(query_frequency)
            score += idf * query_boost * (term_frequency * (k1 + 1.0)) / (term_frequency + length_norm)
        if score > 0:
            scores[chunk_id] = score
    return scores


def rerank_score(query: str, content: str, base_score: float) -> float:
    lexical = token_cosine(query, content)
    coverage = query_token_coverage(query, content)
    phrase = phrase_score(query, content)
    keyword = keyword_score(query, content)
    hybrid = lexical * 0.75 + keyword * 0.25
    return base_score * 0.55 + hybrid * 0.25 + coverage * 0.15 + phrase * 0.05


def fused_score(vector_score: float, bm25_score: float, vector_weight: float, bm25_weight: float) -> float:
    if vector_weight <= 0 and bm25_weight <= 0:
        bm25_weight = 1.0
    return vector_score * vector_weight + bm25_score * bm25_weight


def rrf_fused_score(vector_rank: int | None, bm25_rank: int | None, k: int = 60) -> float:
    """Reciprocal Rank Fusion: 按两路排名融合,分数越高越相关。

    Args:
        vector_rank: 向量召回中的排名(1-based),None 表示未在向量结果中
        bm25_rank: BM25 召回中的排名(1-based),None 表示未在 BM25 结果中
        k: RRF 常数,默认 60
    """
    score = 0.0
    if vector_rank is not None:
        score += 1.0 / (k + vector_rank)
    if bm25_rank is not None:
        score += 1.0 / (k + bm25_rank)
    return score


def normalize_scores(scores: dict[Hashable, float]) -> dict[Hashable, float]:
    if not scores:
        return {}
    values = list(scores.values())
    lo = min(values)
    hi = max(values)
    if hi == lo:
        return {key: 1.0 if value > 0 else 0.0 for key, value in scores.items()}
    return {key: (value - lo) / (hi - lo) if value > 0 else 0.0 for key, value in scores.items()}


def query_token_coverage(query: str, content: str) -> float:
    query_tokens = set(tokenize(query))
    if not query_tokens:
        return 0.0
    content_tokens = set(tokenize(content))
    return len(query_tokens & content_tokens) / len(query_tokens)


def phrase_score(query: str, content: str) -> float:
    normalized_query = re.sub(r"\s+", "", query.lower())
    if not normalized_query:
        return 0.0
    return 1.0 if normalized_query in re.sub(r"\s+", "", content.lower()) else 0.0


def keyword_score(query: str, content: str) -> float:
    query_tokens = [token for token in tokenize(query) if len(token.strip()) >= 1]
    if not query_tokens:
        return 0.0
    content_text = content.lower()
    hits = sum(1 for token in query_tokens if token.lower() in content_text)
    return hits / len(query_tokens)


def expand_best_hit(ranked: list[tuple[KnowledgeChunk, float]], chunks: list[KnowledgeChunk]) -> list[tuple[KnowledgeChunk, float]]:
    """命中冠军块时合并其同源相邻块,避免答案被切块截断。"""
    if not ranked:
        return ranked
    best_chunk, best_score = ranked[0]
    neighbors = sorted(
        [
            chunk
            for chunk in chunks
            if chunk.source == best_chunk.source and abs(chunk.source_index - best_chunk.source_index) <= 1
        ],
        key=lambda item: item.source_index,
    )
    if len(neighbors) <= 1:
        return ranked
    expanded_content = " ".join(chunk.content for chunk in neighbors)
    expanded = KnowledgeChunk(
        source=best_chunk.source,
        source_index=best_chunk.source_index,
        content=expanded_content,
        embedding_json=best_chunk.embedding_json,
    )
    return [(expanded, best_score)] + ranked[1:]
