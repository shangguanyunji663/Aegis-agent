"""RAG 检索子系统:文本分词、混合打分、知识切块、记忆摘要与向量后端。"""
from app.rag.chunking import (
    chunk_text,
    knowledge_metadata_summary,
    metadata_matches,
    parse_knowledge_document,
    rewrite_query,
)
from app.rag.memory import build_memory_summary, compact_sentence
from app.rag.scoring import (
    bm25_scores,
    expand_best_hit,
    fused_score,
    keyword_score,
    normalize_scores,
    phrase_score,
    query_token_coverage,
    rerank_score,
)
from app.rag.text import counts, token_cosine, tokenize
from app.rag.vector_store import (
    FALLBACK_RETRIEVAL_LABEL,
    PRIMARY_RETRIEVAL_LABEL,
    VectorStoreUnavailable,
    build_vector_backend,
    embed_text,
)

__all__ = [
    "chunk_text",
    "knowledge_metadata_summary",
    "metadata_matches",
    "parse_knowledge_document",
    "rewrite_query",
    "build_memory_summary",
    "compact_sentence",
    "bm25_scores",
    "expand_best_hit",
    "fused_score",
    "keyword_score",
    "normalize_scores",
    "phrase_score",
    "query_token_coverage",
    "rerank_score",
    "counts",
    "token_cosine",
    "tokenize",
    "FALLBACK_RETRIEVAL_LABEL",
    "PRIMARY_RETRIEVAL_LABEL",
    "VectorStoreUnavailable",
    "build_vector_backend",
    "embed_text",
]
