from __future__ import annotations

import math
import re
import time
from collections import Counter
from dataclasses import dataclass
from typing import Iterable

from apps.api.app.db import Database
from packages.shared.schemas import Citation, Role


TOKEN = re.compile(r"[a-z0-9]+")
STOPWORDS = {"a", "an", "and", "are", "can", "for", "how", "i", "is", "it", "my", "of", "on", "the", "to"}


def tokenize(text: str) -> list[str]:
    return [token for token in TOKEN.findall(text.lower()) if token not in STOPWORDS]


def chunk_document(text: str, max_tokens: int = 90, overlap: int = 15) -> list[str]:
    words = text.split()
    if not words:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(words):
        chunks.append(" ".join(words[start : start + max_tokens]))
        if start + max_tokens >= len(words):
            break
        start += max(1, max_tokens - overlap)
    return chunks


def _cosine(left: Counter[str], right: Counter[str]) -> float:
    common = sum(left[word] * right[word] for word in left.keys() & right.keys())
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    return common / (left_norm * right_norm) if left_norm and right_norm else 0.0


@dataclass
class RetrievalResult:
    citations: list[Citation]
    confidence: float
    latency_ms: float


class HybridRetriever:
    """Deterministic BM25-style + lexical-vector hybrid retrieval.

    Qdrant is the production adapter target; this local backend intentionally keeps CI and demos
    offline while preserving metadata filtering, chunking, ranking, and confidence semantics.
    """

    def __init__(self, db: Database):
        self.db = db

    def ingest(
        self,
        document_id: str,
        title: str,
        content: str,
        intent: str,
        tenant_id: str = "demo-tenant",
        roles: Iterable[Role] = tuple(Role),
    ) -> None:
        import json

        from apps.api.app.db import utcnow

        # Each short SOP is one persisted document; chunking is applied during indexing/retrieval.
        self.db.execute(
            "INSERT OR REPLACE INTO knowledge_documents VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                document_id,
                title,
                content,
                intent,
                tenant_id,
                json.dumps([role.value for role in roles]),
                1,
                "1.0",
                f"sop://{document_id}",
                utcnow(),
            ),
        )

    def search(
        self,
        query: str,
        role: Role,
        tenant_id: str = "demo-tenant",
        intent: str | None = None,
        limit: int = 3,
    ) -> RetrievalResult:
        import json

        started = time.perf_counter()
        rows = self.db.fetchall(
            "SELECT * FROM knowledge_documents WHERE approved=1 AND tenant_id=?",
            (tenant_id,),
        )
        query_tokens = tokenize(query)
        query_counter = Counter(query_tokens)
        ranked: list[tuple[float, Citation]] = []
        for row in rows:
            if role.value not in json.loads(row["allowed_roles"]):
                continue
            best_score = 0.0
            best_excerpt = ""
            for chunk in chunk_document(row["content"]):
                tokens = tokenize(f"{row['title']} {chunk}")
                counts = Counter(tokens)
                matches = sum(min(query_counter[t], counts[t]) for t in query_counter)
                keyword = matches / max(1, len(set(query_tokens)))
                vector = _cosine(query_counter, counts)
                intent_boost = 0.22 if intent and row["intent"] == intent else 0.0
                score = min(1.0, 0.52 * keyword + 0.26 * vector + intent_boost)
                if score > best_score:
                    best_score = score
                    best_excerpt = chunk
            if best_score > 0.05:
                ranked.append(
                    (
                        best_score,
                        Citation(
                            document_id=row["id"],
                            title=row["title"],
                            excerpt=best_excerpt[:280],
                            score=round(best_score, 4),
                        ),
                    )
                )
        ranked.sort(key=lambda item: (-item[0], item[1].document_id))
        citations = [item[1] for item in ranked[:limit]]
        confidence = citations[0].score if citations else 0.0
        return RetrievalResult(citations, confidence, (time.perf_counter() - started) * 1000)

