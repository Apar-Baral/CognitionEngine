"""Unified Chroma-backed memory (optional semantic embeddings)."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.core.constants import COGNITION_DIR

logger = logging.getLogger(__name__)

COLLECTIONS = ("sessions", "tasks", "insights", "code_chunks")


class VectorMemoryStore:
    """Persistent vector memory under .cognition/memory_chroma/."""

    def __init__(self, project_path: Path | str, project_name: str = "default") -> None:
        self.project_path = Path(project_path).resolve()
        self.project_name = project_name
        self.db_path = self.project_path / COGNITION_DIR / "memory_chroma"
        self.db_path.mkdir(parents=True, exist_ok=True)
        self._client: Any = None
        self._embedder: Any = None
        self._init_client()

    def _init_client(self) -> None:
        try:
            import chromadb

            self._client = chromadb.PersistentClient(path=str(self.db_path))
        except Exception:
            logger.warning("Chroma unavailable; using keyword fallback only")
            self._client = None

    def _collection(self, name: str) -> Any:
        if not self._client:
            return None
        return self._client.get_or_create_collection(
            name=f"{self.project_name}_{name}",
            metadata={"hnsw:space": "cosine"},
        )

    def _embed(self, text: str) -> list[float] | None:
        try:
            from sentence_transformers import SentenceTransformer

            if self._embedder is None:
                self._embedder = SentenceTransformer("all-MiniLM-L6-v2")
            vec = self._embedder.encode(text, show_progress_bar=False)
            return vec.tolist() if hasattr(vec, "tolist") else list(vec)
        except Exception:
            return None

    def add(
        self,
        collection: str,
        document: str,
        metadata: dict[str, Any] | None = None,
        doc_id: str | None = None,
    ) -> str:
        if collection not in COLLECTIONS:
            raise ValueError(f"Unknown collection: {collection}")
        doc_id = doc_id or f"{collection}_{uuid.uuid4().hex[:12]}"
        meta = dict(metadata or {})
        meta["ts"] = datetime.now(timezone.utc).isoformat()
        col = self._collection(collection)
        if col is None:
            self._fallback_write(collection, doc_id, document, meta)
            return doc_id
        emb = self._embed(document)
        if emb:
            col.add(ids=[doc_id], documents=[document], metadatas=[meta], embeddings=[emb])
        else:
            col.add(ids=[doc_id], documents=[document], metadatas=[meta])
        return doc_id

    def search(self, collection: str, query: str, n: int = 5) -> list[dict[str, Any]]:
        col = self._collection(collection)
        if col is None:
            return self._fallback_search(collection, query, n)
        emb = self._embed(query)
        if emb:
            res = col.query(query_embeddings=[emb], n_results=n)
        else:
            res = col.query(query_texts=[query], n_results=n)
        out: list[dict[str, Any]] = []
        docs = res.get("documents") or [[]]
        metas = res.get("metadatas") or [[]]
        for i, doc in enumerate(docs[0] if docs else []):
            out.append(
                {
                    "document": doc,
                    "metadata": (metas[0][i] if metas and metas[0] else {}) or {},
                }
            )
        return out

    def index_session_summary(self, summary: dict[str, Any]) -> None:
        text = json.dumps(
            {
                "session_id": summary.get("session_id"),
                "notes": summary.get("completion_notes", ""),
                "files": summary.get("files_modified", []),
            },
            default=str,
        )
        self.add("sessions", text, {"session_id": str(summary.get("session_id", ""))})

    def index_tasks_from_dna(self, dna: dict[str, Any]) -> None:
        for phase in dna.get("master_plan", {}).get("phase_sequence", []):
            if not isinstance(phase, dict):
                continue
            status = phase.get("status", "")
            tier = "present" if status == "in_progress" else "future"
            if status == "completed":
                tier = "past"
            doc = f"{phase.get('id')}: {phase.get('name')} — {phase.get('description', '')[:200]}"
            self.add(
                "tasks",
                doc,
                {"phase_id": phase.get("id", ""), "tier": tier, "status": status},
            )

    def _fallback_path(self, collection: str) -> Path:
        return self.db_path / f"{collection}_fallback.jsonl"

    def _fallback_write(
        self, collection: str, doc_id: str, document: str, meta: dict[str, Any]
    ) -> None:
        line = json.dumps({"id": doc_id, "document": document, "metadata": meta}) + "\n"
        with self._fallback_path(collection).open("a", encoding="utf-8") as f:
            f.write(line)

    def _fallback_search(self, collection: str, query: str, n: int) -> list[dict[str, Any]]:
        path = self._fallback_path(collection)
        if not path.is_file():
            return []
        q = query.lower()
        hits: list[tuple[int, dict[str, Any]]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            doc = str(row.get("document", ""))
            score = sum(1 for w in q.split() if w in doc.lower())
            if score:
                hits.append((score, row))
        hits.sort(key=lambda x: -x[0])
        return [{"document": h["document"], "metadata": h.get("metadata", {})} for _, h in hits[:n]]
