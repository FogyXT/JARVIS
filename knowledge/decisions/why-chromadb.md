# Why ChromaDB for JARVIS RAG memory

**Date:** 2026-06-10
**Status:** accepted

## Context

JARVIS needed a long-term semantic memory beyond the simple JSON key-value store.
Requirements:
- Runs fully locally (no cloud dependency)
- Semantic search (not just exact key match)
- Embedding model must run offline
- Zero-config — no separate server process
- Must survive Python process restarts

## Options considered

| Option | Pros | Cons |
|--------|------|------|
| **ChromaDB** (embedded) | No server, SQLite backend, cosine similarity, simple API | Smaller community than some alternatives |
| FAISS + manual JSON | Very fast, lightweight | No built-in metadata, manual persistence, more code |
| Qdrant (local) | Powerful filtering, gRPC API | Requires running a separate server — overkill |
| LanceDB | Embedded like ChromaDB, columnar | Less mature at time of evaluation |
| Plain keyword grep over markdown files | Zero deps, dead simple | No semantic understanding, misses related concepts |

## Decision

**ChromaDB** in embedded/persistent mode with `all-MiniLM-L6-v2` for embeddings.

Why:
- `chromadb.PersistentClient(path=…)` stores everything in a single SQLite file — no server, no config
- `SentenceTransformer("all-MiniLM-L6-v2")` is 80MB, runs offline, good enough for Slovak + English
- `hnsw:cosine` space gives meaningful semantic similarity
- API is clean: `collection.upsert()`, `collection.query()`, `collection.get()`
- Lazy init keeps cold-start fast (no model load until first RAG call)

## Consequences

**Good:**
- Semantic search works across Slovak and English queries
- Zero config — works immediately after `pip install chromadb sentence-transformers`
- `chroma.sqlite3` survives restarts, can be backed up

**Watch out for:**
- `sentence-transformers` adds ~3s to first RAG call (model load). Mitigated by lazy init.
- ChromaDB version upgrades can break the on-disk format. Keep `chromadb` pinned in requirements.txt.
- Embedding model is generic, not fine-tuned on our data. If memory grows large (>1000 entries), consider re-ranking.
