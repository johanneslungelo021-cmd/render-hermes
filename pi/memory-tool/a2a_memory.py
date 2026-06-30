#!/usr/bin/env python3
"""
a2a-memory — Vector Memory System
===================================
Persistent agent memory with:
  - Qdrant for vector storage & semantic search
  - Embedding API (Mistral-compatible) for text→vector
  - Supabase REST for structured history logging
  - Context injection: relevant memories auto-inserted into agent context

Usage:
  from a2a_memory import MemorySystem
  mem = MemorySystem()
  mem.store("User prefers short answers", agent_name="pi")
  results = mem.recall("What does the user prefer?")
"""

import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests

# Ensure the memory-tool directory is in the path
_this_dir = os.path.dirname(os.path.abspath(__file__))
if _this_dir not in sys.path:
    sys.path.insert(0, _this_dir)

from a2a_core import MemoryEntry, AgentEvent, EventType

# ── Config ──────────────────────────────────────────

QDRANT_PATH = os.environ.get("QDRANT_PATH", "/root/pi/memory-tool/qdrant_data")
QDRANT_HOST = os.environ.get("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.environ.get("QDRANT_PORT", "6333"))
QDRANT_URL = os.environ.get("QDRANT_URL", "")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY", "")
QDRANT_COLLECTION = os.environ.get("QDRANT_COLLECTION", "agent_memories")

EMBEDDING_API_URL = os.environ.get(
    "EMBEDDING_API_URL",
    "https://api.mistral.ai/v1/embeddings",
)
EMBEDDING_API_KEY = os.environ.get("EMBEDDING_API_KEY", "")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "mistral-embed")
EMBEDDING_DIMS = int(os.environ.get("EMBEDDING_DIMS", "1024"))

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

AGENT_NAME = os.environ.get("A2A_AGENT_NAME", "pi-agent")


# ── Embedding Client ────────────────────────────────

class EmbeddingClient:
    """Generate embeddings via Mistral API (or any OpenAI-compatible endpoint)."""

    def __init__(self, api_url: str = EMBEDDING_API_URL,
                 api_key: str = EMBEDDING_API_KEY,
                 model: str = EMBEDDING_MODEL):
        self.api_url = api_url
        self.api_key = api_key
        self.model = model
        self._cache: dict[str, list[float]] = {}

    def embed(self, text: str) -> list[float]:
        """Generate embedding for a text string."""
        if not text or not text.strip():
            return [0.0] * EMBEDDING_DIMS

        # Check cache
        cache_key = text.strip()[:200]
        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            resp = requests.post(
                self.api_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "input": text.strip(),
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            embedding = data["data"][0]["embedding"]
            self._cache[cache_key] = embedding
            return embedding
        except Exception as e:
            print(f"  [Memory] Embedding error: {e}")
            return [0.0] * EMBEDDING_DIMS

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts."""
        results = []
        for text in texts:
            results.append(self.embed(text))
            time.sleep(0.05)  # rate limit spacing
        return results


# ── Qdrant Client ───────────────────────────────────

class QdrantStore:
    """Qdrant vector store for agent memories."""

    def __init__(self, collection: str = QDRANT_COLLECTION,
                 host: str = QDRANT_HOST, port: int = QDRANT_PORT,
                 local_path: Optional[str] = QDRANT_PATH,
                 url: str = QDRANT_URL, api_key: str = QDRANT_API_KEY):
        self.collection = collection
        self.local_path = local_path
        self.url = url
        self.api_key = api_key
        self._client = None
        self._init_client()

    def _init_client(self):
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.http import models as qmodels

            # Try cloud Qdrant first (if URL configured)
            if self.url:
                try:
                    kwargs = {"url": self.url, "timeout": 10}
                    if self.api_key:
                        kwargs["api_key"] = self.api_key
                    self._client = QdrantClient(**kwargs)
                    self._client.get_collections()
                    print(f"  [Memory] Connected to Qdrant Cloud at {self.url}")
                except Exception as e:
                    print(f"  [Memory] Cloud Qdrant failed ({e}), trying local...")
                    self._client = None

            # Try local Qdrant server next
            if not self._client:
                try:
                    self._client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=5)
                    self._client.get_collections()
                    print(f"  [Memory] Connected to Qdrant at {QDRANT_HOST}:{QDRANT_PORT}")
                except Exception:
                    # Fall back to local (embedded) mode
                    if self.local_path:
                        os.makedirs(self.local_path, exist_ok=True)
                        self._client = QdrantClient(path=self.local_path)
                        print(f"  [Memory] Qdrant local mode at {self.local_path}")
                    else:
                        # In-memory (volatile, for testing)
                        self._client = QdrantClient(location=":memory:")
                        print(f"  [Memory] Qdrant in-memory mode (volatile)")

            self.qmodels = qmodels
            self._ensure_collection()

        except ImportError:
            print(f"  [Memory] qdrant_client not installed. Falling back to file-based storage.")
            self._client = None

    def _ensure_collection(self):
        if not self._client:
            return
        try:
            collections = self._client.get_collections().collections
            existing = [c.name for c in collections]
            if self.collection not in existing:
                self._client.create_collection(
                    collection_name=self.collection,
                    vectors_config=self.qmodels.VectorParams(
                        size=EMBEDDING_DIMS,
                        distance=self.qmodels.Distance.COSINE,
                    ),
                )
                print(f"  [Memory] Created collection '{self.collection}' ({EMBEDDING_DIMS}d)")
        except Exception as e:
            print(f"  [Memory] Collection check error: {e}")

    def upsert(self, entry: MemoryEntry):
        """Store a memory entry."""
        if not self._client:
            return
        try:
            self._client.upsert(
                collection_name=self.collection,
                points=[self.qmodels.PointStruct(
                    id=entry.id,
                    vector=entry.embedding,
                    payload={
                        "text": entry.text[:5000],
                        "source": entry.source,
                        "agent_name": entry.agent_name,
                        "parent_task_id": entry.parent_task_id,
                        "timestamp": entry.timestamp,
                        "metadata": json.dumps(entry.metadata),
                    },
                )],
            )
        except Exception as e:
            print(f"  [Memory] Upsert error: {e}")

    def search(self, query_embedding: list[float], limit: int = 5,
               score_threshold: float = 0.6) -> list[tuple[MemoryEntry, float]]:
        """Search for similar memories."""
        if not self._client:
            return []
        try:
            results = self._client.search(
                collection_name=self.collection,
                query_vector=query_embedding,
                limit=limit,
                score_threshold=score_threshold,
            )
            entries = []
            for r in results:
                payload = r.payload or {}
                try:
                    meta = json.loads(payload.get("metadata", "{}"))
                except (json.JSONDecodeError, TypeError):
                    meta = {}
                entry = MemoryEntry(
                    id=r.id,
                    text=payload.get("text", ""),
                    source=payload.get("source", ""),
                    agent_name=payload.get("agent_name", ""),
                    parent_task_id=payload.get("parent_task_id", ""),
                    timestamp=payload.get("timestamp", ""),
                    metadata=meta,
                )
                entries.append((entry, r.score if hasattr(r, 'score') else 0.0))
            return entries
        except Exception as e:
            print(f"  [Memory] Search error: {e}")
            return []

    def count(self) -> int:
        if not self._client:
            return 0
        try:
            info = self._client.get_collection(collection_name=self.collection)
            return info.points_count
        except Exception:
            return 0

    def delete_old(self, max_age_days: int = 30):
        """Delete memories older than max_age_days."""
        if not self._client:
            return
        try:
            cutoff = datetime.now(timezone.utc).timestamp() - (max_age_days * 86400)
            self._client.delete(
                collection_name=self.collection,
                points_selector=self.qmodels.FilterSelector(
                    filter=self.qmodels.Filter(
                        must=[self.qmodels.FieldCondition(
                            key="timestamp",
                            range=self.qmodels.Range(lt=cutoff),
                        )],
                    ),
                ),
            )
        except Exception as e:
            print(f"  [Memory] Delete old error: {e}")


# ── Supabase History Logger ─────────────────────────

class SupabaseLogger:
    """Logs structured history to Supabase via REST API."""

    def __init__(self, url: str = SUPABASE_URL, key: str = SUPABASE_KEY):
        self.url = url.rstrip("/")
        self.key = key
        self.headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }

    def log_event(self, event_type: str, data: dict,
                  agent_name: str = AGENT_NAME) -> bool:
        """Log an agent event to the moltcorp_transaction_logs table."""
        try:
            resp = requests.post(
                f"{self.url}/rest/v1/moltcorp_transaction_logs",
                headers=self.headers,
                json={
                    "service": "a2a-agent",
                    "event_type": event_type,
                    "level": "info" if event_type != "error" else "error",
                    "success": event_type != "error",
                    "context": data,
                    "raw_payload": data,
                    "pushed_by": agent_name,
                    "agent_name": agent_name,
                },
                timeout=10,
            )
            return resp.status_code in (200, 201, 204)
        except Exception as e:
            print(f"  [Supabase] Log error: {e}")
            return False

    def log_memory(self, entry: MemoryEntry) -> bool:
        """Log a memory entry to Supabase."""
        return self.log_event(
            event_type="memory_store",
            data={
                "memory_id": entry.id,
                "text": entry.text[:1000],
                "source": entry.source,
                "agent_name": entry.agent_name or AGENT_NAME,
                "task_id": entry.parent_task_id,
            },
            agent_name=entry.agent_name or AGENT_NAME,
        )

    def log_task(self, task, agent_name: str = AGENT_NAME) -> bool:
        """Log a task lifecycle event."""
        return self.log_event(
            event_type=f"task_{task.status.value}",
            data={
                "task_id": task.id,
                "query": task.query[:500],
                "status": task.status.value,
                "role": task.role.value,
                "parent_task_id": task.parent_task_id,
                "subordinate_agent": task.subordinate_agent,
                "result": task.result[:500] if task.result else None,
            },
            agent_name=agent_name,
        )


# ── Memory System ──────────────────────────────────

class MemorySystem:
    """Unified memory system: embedding + Qdrant + Supabase + context injection."""

    def __init__(self):
        self.embedder = EmbeddingClient()
        self.qdrant = QdrantStore()
        self.logger = SupabaseLogger()
        self._event_listeners: list = []

    def store(self, text: str, source: str = "conversation",
              agent_name: str = AGENT_NAME, task_id: str = "",
              metadata: Optional[dict] = None) -> Optional[MemoryEntry]:
        """Store a memory: embed → Qdrant → Supabase."""
        if not text or not text.strip():
            return None

        embedding = self.embedder.embed(text)

        entry = MemoryEntry(
            text=text[:5000],
            embedding=embedding,
            source=source,
            agent_name=agent_name,
            parent_task_id=task_id,
            metadata=metadata or {},
        )

        self.qdrant.upsert(entry)
        self.logger.log_memory(entry)

        for listener in self._event_listeners:
            try:
                listener(AgentEvent.memory_store(task_id or "", text[:200]))
            except Exception:
                pass

        return entry

    def recall(self, query: str, limit: int = 5,
               score_threshold: float = 0.6) -> list[MemoryEntry]:
        """Semantic search for relevant memories."""
        embedding = self.embedder.embed(query)
        results = self.qdrant.search(embedding, limit=limit,
                                     score_threshold=score_threshold)
        return [entry for entry, score in results]

    def inject_context(self, task_id: str, user_message: str) -> str:
        """
        Find relevant memories and format them as context for the LLM.
        Returns a context string to inject.
        """
        memories = self.recall(user_message, limit=5, score_threshold=0.5)
        if not memories:
            return ""

        for listener in self._event_listeners:
            try:
                listener(AgentEvent.memory_recall(
                    task_id, [m.to_dict() for m in memories]
                ))
            except Exception:
                pass

        parts = ["## Relevant Context from Memory\n"]
        for m in memories:
            ts = m.timestamp[:19] if m.timestamp else ""
            parts.append(f"- [{ts}] ({m.source}) {m.text[:300]}")
        parts.append("")

        for listener in self._event_listeners:
            try:
                listener(AgentEvent.status(task_id, f"Found {len(memories)} relevant memories"))
            except Exception:
                pass

        return "\n".join(parts)

    def status(self) -> dict:
        mode = "cloud" if self.qdrant.url else "server" if QDRANT_HOST == "localhost" else "local"
        return {
            "vector_count": self.qdrant.count(),
            "embedding_model": EMBEDDING_MODEL,
            "qdrant_collection": QDRANT_COLLECTION,
            "qdrant_mode": mode,
            "qdrant_url": self.qdrant.url or f"{QDRANT_HOST}:{QDRANT_PORT}",
            "supabase_connected": bool(self.logger.url),
        }

    def on_event(self, listener):
        self._event_listeners.append(listener)

    def remove_listener(self, listener):
        if listener in self._event_listeners:
            self._event_listeners.remove(listener)


# ── CLI Test ────────────────────────────────────────

if __name__ == "__main__":
    import sys
    mem = MemorySystem()

    if len(sys.argv) > 1 and sys.argv[1] == "store":
        text = " ".join(sys.argv[2:]) or "Test memory entry"
        entry = mem.store(text, source="cli_test")
        print(f"Stored: {entry.id if entry else 'failed'}")

    elif len(sys.argv) > 1 and sys.argv[1] == "recall":
        query = " ".join(sys.argv[2:]) or "test"
        results = mem.recall(query)
        print(f"Found {len(results)} results:")
        for r in results:
            print(f"  [{r.source}] {r.text[:100]}")

    elif len(sys.argv) > 1 and sys.argv[1] == "status":
        print(json.dumps(mem.status(), indent=2))

    else:
        print("Usage: python3 a2a-memory.py [store|recall|status] [text]")
        print(json.dumps(mem.status(), indent=2))
