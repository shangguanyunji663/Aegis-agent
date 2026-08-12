from __future__ import annotations

import math
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from app.config import Settings

PRIMARY_RETRIEVAL_LABEL = "Chroma vector + BM25 hybrid + local reranker"
FALLBACK_RETRIEVAL_LABEL = "local BM25 + hybrid_score reranker"


class VectorStoreUnavailable(RuntimeError):
    pass


class VectorSearchBackend:
    backend_name = "disabled"
    embedding_model = "none"

    def __init__(self):
        self.last_error = ""

    def enabled(self) -> bool:
        return False

    def available(self) -> bool:
        return self.enabled()

    def upsert(self, source: str, chunks: list[str], chunk_ids: list[int] | None = None) -> None:
        return None

    def rebuild(self, records: Iterable[tuple[str, list[str]]]) -> None:
        self.reset()
        for source, chunks in records:
            self.upsert(source, chunks)

    def reset(self) -> None:
        return None

    def search(self, query: str, top_k: int) -> list[dict]:
        return []

    def count(self) -> int:
        return 0

    def snapshot(self) -> str | None:
        return None

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [embed_text(text) for text in texts]


class LocalVectorBackend(VectorSearchBackend):
    backend_name = "local"
    embedding_model = "local-hash"

    def __init__(self):
        super().__init__()
        self._records: list[dict] = []

    def enabled(self) -> bool:
        return True

    def upsert(self, source: str, chunks: list[str], chunk_ids: list[int] | None = None) -> None:
        self._records = [record for record in self._records if record["source"] != source]
        embeddings = self.embed_texts(chunks)
        for index, chunk in enumerate(chunks):
            chunk_id = chunk_ids[index] if chunk_ids and index < len(chunk_ids) else None
            self._records.append(
                {
                    "id": f"knowledge-chunk-{chunk_id}" if chunk_id is not None else f"{source}:{index}",
                    "db_id": chunk_id,
                    "source": source,
                    "source_index": index,
                    "chunk": chunk,
                    "embedding": embeddings[index],
                }
            )

    def reset(self) -> None:
        self._records = []

    def search(self, query: str, top_k: int) -> list[dict]:
        query_embedding = self.embed_texts([query])[0]
        ranked = []
        for record in self._records:
            score = cosine_similarity(query_embedding, record["embedding"])
            if score <= 0:
                continue
            ranked.append((record, score))
        ranked.sort(key=lambda item: item[1], reverse=True)
        return [
            {
                "chunk_id": record["id"],
                "db_id": record.get("db_id"),
                "source": record["source"],
                "source_index": record["source_index"],
                "snippet": record["chunk"][:320],
                "content": record["chunk"],
                "score": float(f"{score:.4f}"),
            }
            for record, score in ranked[:top_k]
        ]

    def count(self) -> int:
        return len(self._records)


class ChromaVectorBackend(VectorSearchBackend):
    """Primary RAG path: OpenAI embeddings stored and queried in persistent Chroma."""

    backend_name = "chroma"

    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self.can_embed = False
        self._available = False
        self.client = None
        self.collection = None
        self.persist_dir: Path | None = None
        self.embedding_model = settings.openai_embedding_model

        if not settings.vector_enabled:
            self.last_error = "Chroma 向量库未启用"
            return
        if not settings.openai_api_key.strip():
            message = f"缺少 OPENAI_API_KEY，Chroma + {settings.openai_embedding_model} 不可用，已回退到{FALLBACK_RETRIEVAL_LABEL}"
            if settings.vector_required:
                raise VectorStoreUnavailable(
                    f"缺少 OPENAI_API_KEY，无法启用 Chroma + {settings.openai_embedding_model} 主检索方案"
                )
            self.last_error = message
            return
        try:
            import chromadb
        except ImportError as exc:
            message = f"缺少 chromadb 依赖，Chroma + {settings.openai_embedding_model} 不可用，已回退到{FALLBACK_RETRIEVAL_LABEL}"
            if settings.vector_required:
                raise VectorStoreUnavailable("缺少 chromadb 依赖，无法启用 Chroma + OpenAI embeddings 主检索方案") from exc
            self.last_error = message
            return

        try:
            if settings.chroma_host.strip():
                self.client = chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)
                self.persist_dir = None
            else:
                path = settings.resolve_path(settings.chroma_dir)
                path.mkdir(parents=True, exist_ok=True)
                self.persist_dir = path
                self.client = chromadb.PersistentClient(path=str(path))
            self.collection = self.client.get_or_create_collection(
                name=settings.chroma_collection_name,
                embedding_function=None,
                metadata={"hnsw:space": "cosine", "embedding_model": settings.openai_embedding_model},
            )
            self.can_embed = True
            self._available = True
        except Exception as exc:
            message = str(exc)
            if settings.vector_required:
                raise VectorStoreUnavailable(message) from exc
            self.last_error = message
            self._available = False

    def enabled(self) -> bool:
        return self._available and self.can_embed

    def available(self) -> bool:
        return self.enabled()

    def upsert(self, source: str, chunks: list[str], chunk_ids: list[int] | None = None) -> None:
        if not self.collection or not self.can_embed:
            return
        self.collection.delete(where={"source": source})
        if not chunks:
            return
        embeddings = self.embed_texts(chunks)
        ids = []
        metadatas = []
        for index, _ in enumerate(chunks):
            chunk_id = chunk_ids[index] if chunk_ids and index < len(chunk_ids) else None
            ids.append(self._id(chunk_id) if chunk_id is not None else f"{source}:{index}")
            metadatas.append(
                {
                    "db_id": int(chunk_id) if chunk_id is not None else index,
                    "source": source,
                    "source_index": index,
                    "chunk_id": ids[-1],
                }
            )
        self.collection.upsert(ids=ids, documents=chunks, metadatas=metadatas, embeddings=embeddings)
        self.snapshot()

    def reset(self) -> None:
        if self.collection:
            existing = self.collection.get().get("ids", [])
            if existing:
                self.collection.delete(ids=existing)

    def search(self, query: str, top_k: int) -> list[dict]:
        if not self.collection or not self.can_embed:
            return []
        query_embedding = self.embed_texts([query])[0]
        result = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        rows = []
        for index, document in enumerate(documents):
            metadata = metadatas[index] if index < len(metadatas) else {}
            distance = float(distances[index]) if index < len(distances) else 1.0
            source = str(metadata.get("source", ""))
            source_index = int(metadata.get("source_index", index))
            chunk_id = metadata.get("chunk_id") or (
                self._id(int(metadata["db_id"])) if metadata.get("db_id") is not None else f"{source}:{source_index}"
            )
            rows.append(
                {
                    "chunk_id": chunk_id,
                    "db_id": metadata.get("db_id"),
                    "source": source,
                    "source_index": source_index,
                    "snippet": (document or "")[:320],
                    "content": document or "",
                    "score": float(f"{1.0 / (1.0 + max(0.0, distance)):.4f}"),
                }
            )
        return rows

    def count(self) -> int:
        if not self.collection or not self.can_embed:
            return 0
        return int(self.collection.count())

    def snapshot(self) -> str | None:
        if not self.can_embed or self.persist_dir is None or not self.persist_dir.exists():
            return None
        snapshot_root = self.settings.resolve_path(self.settings.chroma_snapshot_dir)
        snapshot_root.mkdir(parents=True, exist_ok=True)
        destination = snapshot_root / datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
        shutil.copytree(self.persist_dir, destination)
        snapshots = sorted([path for path in snapshot_root.iterdir() if path.is_dir()], reverse=True)
        keep = max(1, self.settings.chroma_snapshot_keep)
        for stale in snapshots[keep:]:
            shutil.rmtree(stale, ignore_errors=True)
        return str(destination)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not self.can_embed:
            raise VectorStoreUnavailable(self.last_error or "Chroma + OpenAI embeddings 主检索方案不可用")
        import httpx

        payload = {
            "model": self.settings.openai_embedding_model,
            "input": [text if text.strip() else " " for text in texts],
        }
        headers = {"Authorization": f"Bearer {self.settings.openai_api_key}"}
        response = httpx.post(
            f"{self.settings.openai_base_url.rstrip('/')}/embeddings",
            headers=headers,
            json=payload,
            timeout=self.settings.embedding_timeout_seconds,
        )
        response.raise_for_status()
        rows = sorted(response.json().get("data", []), key=lambda item: item.get("index", 0))
        embeddings = [row.get("embedding") for row in rows]
        if len(embeddings) != len(texts) or any(not embedding for embedding in embeddings):
            raise VectorStoreUnavailable("OpenAI embeddings 接口返回向量数量不匹配")
        return [[float(value) for value in embedding] for embedding in embeddings]

    def _id(self, chunk_id: int) -> str:
        return f"knowledge-chunk-{chunk_id}"


def build_vector_backend(settings: Settings) -> VectorSearchBackend:
    if not settings.vector_enabled:
        return VectorSearchBackend()

    backend_name = settings.vector_backend.strip().lower()
    if backend_name in {"chroma", "openai", "openai-chroma"}:
        try:
            backend = ChromaVectorBackend(settings)
        except VectorStoreUnavailable:
            if settings.vector_required:
                raise
            return LocalVectorBackend()
        if backend.enabled():
            return backend
        if settings.vector_required:
            raise VectorStoreUnavailable(backend.last_error or "vector backend required but unavailable")
        # Missing API key / chromadb: still allow hybrid BM25 path; local vector helps offline demos.
        return LocalVectorBackend()

    return LocalVectorBackend()


def embed_text(text: str, size: int = 64) -> list[float]:
    vector = [0.0] * size
    compact = "".join(ch.lower() for ch in text if ch.strip())
    if not compact:
        return vector
    for index in range(max(1, len(compact) - 1)):
        gram = compact[index:index + 2]
        bucket = hash(gram) % size
        vector[bucket] += 1.0
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    return sum(a * b for a, b in zip(left, right))
