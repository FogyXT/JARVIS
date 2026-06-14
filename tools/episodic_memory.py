"""
Episodic Buffer — rýchla, časovo-indexovaná pamäť s Ebbinghaus zabúdaním.

Inšpirované hipokampom. Implementuje:
- Working memory buffer (64 položiek, numpy cosine similarity, sub-ms prístup)
- Episodic buffer (256 položiek s decay scores, timestamped)
- Ebbinghaus decay: score(t) = (n_accesses)^beta × exp(-lambda × delta_t) × importance
- Forget threshold (0.05) — slabé spomienky sa zahadzujú
- Promote threshold (0.65 alebo 5+ prístupov za 14 dní) — silné spomienky idú do sémantickej pamäte
- Access-based reinforcement — každé čítanie posilní pamäť

Použitie:
    from tools.episodic_memory import EpisodicBuffer

    buf = EpisodicBuffer(working_capacity=64, episodic_capacity=256)
    buf.store("fogy_favorite_color", "modrá", importance=0.7)
    results = buf.retrieve(query="obľúbená farba", k=3)
    buf.decay()  # periodické volanie
    promoted = buf.get_promotable()  # vráti položky na povýšenie do semantic store
"""

import os
import sys
import json
import time
import math
import threading
from typing import Optional, Any
from dataclasses import dataclass, field, asdict

import numpy as np

# Robust import — funguje z tools/ aj z koreňa projektu
try:
    from tools.jarvis_logging import log
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from tools.jarvis_logging import log


# ── Config ────────────────────────────────────────────────────────────────

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUFFER_FILE = os.path.join(PROJECT_ROOT, "episodic_buffer.json")

# Ebbinghaus decay parameters (Wixted 1991, CortexGraph 2026)
DEFAULT_BETA = 0.3        # recency boost exponent
DEFAULT_LAMBDA = 1e-6     # decay rate per second (~30 days to forget threshold)
FORGET_THRESHOLD = 0.05   # score below this → remove
PROMOTE_THRESHOLD = 0.55  # score above this → promote to semantic (lowered from 0.65 — was unreachable with default importance=0.5)
PROMOTE_ACCESS_COUNT = 5  # OR this many accesses within window
PROMOTE_ACCESS_WINDOW = 14 * 24 * 3600  # 14 days in seconds


# ── Data Model ────────────────────────────────────────────────────────────

@dataclass
class MemoryItem:
    """Jedna epizodická spomienka."""
    key: str
    value: str
    timestamp: float = field(default_factory=time.time)
    last_access: float = field(default_factory=time.time)
    access_count: int = 1
    importance: float = 0.5
    current_score: float = 1.0
    embedding: Optional[np.ndarray] = None
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        if self.embedding is not None:
            d["embedding"] = self.embedding.tolist()
        else:
            d["embedding"] = None
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "MemoryItem":
        emb = d.pop("embedding", None)
        item = cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
        if emb is not None:
            item.embedding = np.array(emb, dtype=np.float32)
        return item


# ── Module-level Embedding Singleton ──────────────────────────────────────
# (pred class definíciou, aby module-level kód neprerušil class body)

_global_embed_fn = None
_global_embed_dim = 768  # unified to all-mpnet-base-v2 (was 384/MiniLM — caused centroid mismatch with agents)


def _get_global_embed_fn(dim: int = 768):
    """Module-level singleton — embedding model sa loaduje len raz."""
    global _global_embed_fn, _global_embed_dim
    if _global_embed_fn is not None:
        return _global_embed_fn
    _global_embed_dim = dim
    try:
        from sentence_transformers import SentenceTransformer
        _global_embed_fn = SentenceTransformer("all-mpnet-base-v2")
        log.info("Embedding model loaded (global singleton)", module="episodic",
                data={"model": "all-mpnet-base-v2", "dim": dim})
    except ImportError:
        log.warn("SentenceTransformer not available, using random embeddings", module="episodic")
        class _RandomEmbed:
            @staticmethod
            def encode(texts):
                return np.random.randn(len(texts), dim).astype(np.float32)
        _global_embed_fn = _RandomEmbed()
    return _global_embed_fn


def _embed_text(text: str) -> np.ndarray:
    """Vytvor embedding pre text — používa globálny singleton model."""
    fn = _get_global_embed_fn(_global_embed_dim)
    return np.array(fn.encode([text])[0], dtype=np.float32)


# ── Episodic Buffer ──────────────────────────────────────────────────────

class EpisodicBuffer:
    """3-vrstvový buffer: working (64) → episodic (256) → persistent (ChromaDB/JSON)."""

    def __init__(
        self,
        working_capacity: int = 64,
        episodic_capacity: int = 256,
        beta: float = DEFAULT_BETA,
        lambd: float = DEFAULT_LAMBDA,
        embedding_dim: int = 768,
    ):
        self.working_capacity = working_capacity
        self.episodic_capacity = episodic_capacity
        self.beta = beta
        self.lambd = lambd
        self.embedding_dim = embedding_dim

        self.working: list[MemoryItem] = []
        self.episodic: list[MemoryItem] = []

        self._working_embeddings: Optional[np.ndarray] = None
        self._episodic_embeddings: Optional[np.ndarray] = None

        self._lock = threading.RLock()  # protects working/episodic/stats under concurrent access

        self.stats = {
            "stores": 0, "retrievals": 0, "decays": 0,
            "forgets": 0, "promotions": 0,
            "hits_working": 0, "hits_episodic": 0, "misses": 0,
        }

    # ── Embedding helpers ──────────────────────────────────────────────

    def _rebuild_embeddings(self, target: str = "both"):
        if target in ("working", "both") and self.working:
            embs = []
            for item in self.working:
                if item.embedding is None:
                    item.embedding = _embed_text(f"{item.key}: {item.value}")
                embs.append(item.embedding)
            self._working_embeddings = np.stack(embs) if embs else None
        if target in ("episodic", "both") and self.episodic:
            embs = []
            for item in self.episodic:
                if item.embedding is None:
                    item.embedding = _embed_text(f"{item.key}: {item.value}")
                embs.append(item.embedding)
            self._episodic_embeddings = np.stack(embs) if embs else None

    # ── Cosine Similarity Search ───────────────────────────────────────

    def _cosine_search(self, query_emb: np.ndarray, embeddings: np.ndarray,
                       items: list, k: int) -> list[tuple[MemoryItem, float]]:
        if embeddings is None or len(items) == 0:
            return []
        query_norm = query_emb / (np.linalg.norm(query_emb) + 1e-8)
        emb_norm = embeddings / (np.linalg.norm(embeddings, axis=1, keepdims=True) + 1e-8)
        similarities = np.dot(emb_norm, query_norm)
        top_k = min(k, len(items))
        top_indices = np.argsort(similarities)[-top_k:][::-1]
        return [(items[i], float(similarities[i])) for i in top_indices]

    # ── Store ──────────────────────────────────────────────────────────

    def store(self, key: str, value: str, importance: float = 0.5,
              tags: list[str] = None) -> MemoryItem:
        with self._lock:
            log.debug(f"store({key})", module="episodic",
                     data={"importance": importance, "tags": tags})

            item = MemoryItem(key=key, value=value, importance=importance, tags=tags or [])
            item.embedding = _embed_text(f"{key}: {value}")
            self.working.append(item)

            if len(self.working) > self.working_capacity:
                overflow = self.working.pop(0)
                self._promote_to_episodic(overflow)

            self._rebuild_embeddings("working")
            self.stats["stores"] += 1
            return item

    def _promote_to_episodic(self, item: MemoryItem):
        self.episodic.append(item)
        if len(self.episodic) > self.episodic_capacity:
            self.decay(target="episodic")
            # Evict lowest-scored item (was: FIFO pop(0) — score-blind)
            self.episodic.sort(key=lambda x: x.current_score)
            removed = self.episodic.pop(0)
            log.debug(f"Forgetting: {removed.key} (score={removed.current_score:.4f})",
                     module="episodic")
            self.stats["forgets"] += 1
        self._rebuild_embeddings("episodic")

    # ── Retrieve ───────────────────────────────────────────────────────

    def retrieve(self, query: str = None, key: str = None, k: int = 5) -> list[dict]:
        with self._lock:
            self.stats["retrievals"] += 1
            results = []

            if key:
                for item in reversed(self.working):
                    if item.key == key:
                        self._reinforce(item)
                        results.append(self._item_to_result(item, 1.0, "working"))
                        break
                if not results:
                    for item in reversed(self.episodic):
                        if item.key == key:
                            self._reinforce(item)
                            results.append(self._item_to_result(item, item.current_score, "episodic"))
                            break
                if not results:
                    self.stats["misses"] += 1
                return results

            if query:
                query_emb = _embed_text(query)
                if self.working:
                    for item, sim in self._cosine_search(query_emb, self._working_embeddings,
                                                         self.working, k):
                        self._reinforce(item)
                        results.append(self._item_to_result(item, sim, "working"))
                        self.stats["hits_working"] += 1
                remaining = k - len(results)
                if remaining > 0 and self.episodic:
                    for item, sim in self._cosine_search(query_emb, self._episodic_embeddings,
                                                         self.episodic, remaining):
                        if any(r["key"] == item.key for r in results):
                            continue
                        self._reinforce(item)
                        results.append(self._item_to_result(item, sim, "episodic"))
                        self.stats["hits_episodic"] += 1

            if not results:
                self.stats["misses"] += 1
            return results[:k]

    def _reinforce(self, item: MemoryItem):
        item.access_count += 1
        item.last_access = time.time()
        boost = min(0.1, 1.0 - item.current_score)
        item.current_score = min(1.0, item.current_score + boost)
        item.embedding = None

    def _item_to_result(self, item: MemoryItem, score: float, source: str) -> dict:
        return {
            "key": item.key, "value": item.value,
            "score": round(score, 4), "source": source,
            "timestamp": item.timestamp, "last_access": item.last_access,
            "access_count": item.access_count,
            "importance": item.importance, "tags": item.tags,
        }

    # ── Decay ──────────────────────────────────────────────────────────

    def decay(self, target: str = "both"):
        with self._lock:
            now = time.time()
            self.stats["decays"] += 1

            if target in ("working", "both"):
                for item in self.working:
                    item.current_score = self._decay_score(item, now - item.last_access)

            if target in ("episodic", "both"):
                for item in self.episodic:
                    item.current_score = self._decay_score(item, now - item.last_access)
                before = len(self.episodic)
                self.episodic = [i for i in self.episodic if i.current_score >= FORGET_THRESHOLD]
                forgotten = before - len(self.episodic)
                if forgotten > 0:
                    self.stats["forgets"] += forgotten
                    log.debug(f"Decay: {forgotten} memories forgotten", module="episodic",
                             data={"episodic_size": len(self.episodic)})
                    self._rebuild_embeddings("episodic")

    def _decay_score(self, item: MemoryItem, delta_t: float) -> float:
        score = (item.access_count ** self.beta) * math.exp(-self.lambd * delta_t) * item.importance
        return min(1.0, score)

    # ── Promotion ──────────────────────────────────────────────────────

    def get_promotable(self) -> list[MemoryItem]:
        with self._lock:
            now = time.time()
            promotable = []

            # Check BOTH working and episodic (previously only checked episodic,
            # but items never reach episodic until working overflows at 64 items)
            for item in self.working + self.episodic:
                if item.current_score >= PROMOTE_THRESHOLD:
                    promotable.append(item)
                elif item.access_count >= PROMOTE_ACCESS_COUNT:
                    if now - item.timestamp <= PROMOTE_ACCESS_WINDOW:
                        promotable.append(item)
                # Time-based promotion: item older than 24h with decent score
                elif (now - item.timestamp > 24 * 3600
                      and item.current_score >= 0.40
                      and item.access_count >= 3):
                    promotable.append(item)

            if promotable:
                self.stats["promotions"] += len(promotable)
                sources = {"working": sum(1 for i in promotable if i in self.working),
                           "episodic": sum(1 for i in promotable if i in self.episodic)}
                log.info(f"Promoting {len(promotable)} memories to semantic store (w={sources['working']}, e={sources['episodic']})",
                        module="episodic")
            return promotable

    def remove_promoted(self, items: list[MemoryItem]):
        with self._lock:
            keys = {item.key for item in items}
            before = len(self.working) + len(self.episodic)
            self.working = [i for i in self.working if i.key not in keys]
            self.episodic = [i for i in self.episodic if i.key not in keys]
            after = len(self.working) + len(self.episodic)
            log.debug(f"Removed {before - after} promoted items from buffers", module="episodic")
            self._rebuild_embeddings("both")

    # ── Persistencia ───────────────────────────────────────────────────

    def save(self, path: str = None):
        with self._lock:
            fp = path or BUFFER_FILE
            data = {
                "working": [item.to_dict() for item in self.working],
                "episodic": [item.to_dict() for item in self.episodic],
                "stats": self.stats,
                "config": {
                    "working_capacity": self.working_capacity,
                    "episodic_capacity": self.episodic_capacity,
                    "beta": self.beta, "lambd": self.lambd,
                },
            }
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            with open(fp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            log.debug(f"Buffer saved: {len(self.working)}w + {len(self.episodic)}e",
                     module="episodic", data={"path": fp})

    def load(self, path: str = None):
        fp = path or BUFFER_FILE
        if not os.path.exists(fp):
            log.debug("No saved buffer found, starting fresh", module="episodic")
            return
        with open(fp, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.working = [MemoryItem.from_dict(d) for d in data.get("working", [])]
        self.episodic = [MemoryItem.from_dict(d) for d in data.get("episodic", [])]
        self.stats = data.get("stats", self.stats)
        self._rebuild_embeddings("both")
        log.info(f"Buffer loaded: {len(self.working)}w + {len(self.episodic)}e",
                module="episodic", data={"path": fp})

    # ── Utilities ──────────────────────────────────────────────────────

    def size(self) -> dict:
        with self._lock:
            return {"working": len(self.working), "episodic": len(self.episodic),
                    "total": len(self.working) + len(self.episodic)}

    def clear(self):
        with self._lock:
            self.working.clear()
            self.episodic.clear()
            self._working_embeddings = None
            self._episodic_embeddings = None
            log.info("Buffer cleared", module="episodic")

    def health(self) -> dict:
        with self._lock:
            avg_w = float(np.mean([i.current_score for i in self.working])) if self.working else 0.0
            avg_e = float(np.mean([i.current_score for i in self.episodic])) if self.episodic else 0.0
            return {
                **{"working": len(self.working), "episodic": len(self.episodic),
                   "total": len(self.working) + len(self.episodic)},
                "stats": self.stats,
                "avg_score_working": round(avg_w, 4),
                "avg_score_episodic": round(avg_e, 4),
                "forget_threshold": FORGET_THRESHOLD,
                "promote_threshold": PROMOTE_THRESHOLD,
            }


# ── Singleton ─────────────────────────────────────────────────────────────

_buffer: Optional[EpisodicBuffer] = None


def get_buffer() -> EpisodicBuffer:
    """Získaj singleton EpisodicBuffer (lenivá inicializácia)."""
    global _buffer
    if _buffer is None:
        _buffer = EpisodicBuffer()
        _buffer.load()
    return _buffer
