"""
RAG (Retrieval-Augmented Generation) Memory v2 pre JARVIS.

Vylepšenia oproti v1:
- Embedding model: all-mpnet-base-v2 (768-dim, vyššia kvalita ako MiniLM)
- Hybrid search: dense (embeddings) + sparse (BM25) → reciprocal rank fusion
- Score threshold: min_score parameter pre filtrovanie nerelevantných výsledkov
- Metadata filtering: podľa timestampu, tagov, zdroja
- Nová kolekcia: jarvis_memory_v2 (auto-migrácia zo starej)

API:
    rag_search(query, k=5, min_score=0.3, filters=None)  → sémantické vyhľadávanie
    rag_save(key, value, tags=None)                       → uloží fakt
    rag_read(key=None)                                    → číta všetky/podľa kľúča
    rag_delete(key)                                       → vymaže fakt
"""

import os
import sys
import json
import time
import math
from typing import Optional, Any

from tools.jarvis_logging import log

# ── Paths ─────────────────────────────────────────────────────────────────

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROMA_DIR = os.path.join(PROJECT_ROOT, "chroma_db")
MEMORY_FILE = os.path.join(PROJECT_ROOT, "jarvis_memory.json")
KNOWLEDGE_DIR = os.path.join(PROJECT_ROOT, "knowledge")

# New collection for v2 embeddings (768-dim, incompatible with old 384-dim)
COLLECTION_NAME = "jarvis_memory_v2"

# ── Lazy-loaded globals ───────────────────────────────────────────────────

_chroma_client = None
_collection = None
_embed_fn = None           # SentenceTransformer encode function
_bm25_cache = {}           # {doc_id: tokens} pre BM25 sparse search
_init_done = False

EMBED_DIM = 768
EMBED_MODEL = "all-mpnet-base-v2"


# ── Init ──────────────────────────────────────────────────────────────────

def _ensure_init():
    """Lazy init — model + ChromaDB len keď treba."""
    global _chroma_client, _collection, _embed_fn, _init_done
    if _init_done:
        return

    import chromadb
    from sentence_transformers import SentenceTransformer

    os.makedirs(CHROMA_DIR, exist_ok=True)
    _chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)

    # Get or create v2 collection
    try:
        _collection = _chroma_client.get_collection(COLLECTION_NAME)
        log.info(f"ChromaDB collection '{COLLECTION_NAME}' loaded", module="rag")
    except Exception:
        _collection = _chroma_client.create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"}
        )
        log.info(f"ChromaDB collection '{COLLECTION_NAME}' created", module="rag")

    # Load embedding model
    log.info(f"Loading embedding model: {EMBED_MODEL}", module="rag")
    _embed_fn = SentenceTransformer(EMBED_MODEL)
    _init_done = True

    # Auto-migrate old data
    _migrate_old_collection()
    _migrate_json_to_chroma()
    _index_knowledge_files()
    _index_codebase()

    # Rebuild BM25 cache after migrations
    _rebuild_bm25_cache()


# ── BM25 Sparse Search ───────────────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    """Jednoduchá tokenizácia pre BM25 (lowercase, split na slová)."""
    import re
    return re.findall(r'\w+', text.lower())


def _rebuild_bm25_cache():
    """Rebuild BM25 token cache zo všetkých dokumentov v kolekcii."""
    _bm25_cache.clear()
    if _collection is None:
        return
    try:
        all_docs = _collection.get()
        if all_docs and all_docs.get("ids") and all_docs.get("documents"):
            for doc_id, doc_text in zip(all_docs["ids"], all_docs["documents"]):
                if doc_text:
                    _bm25_cache[doc_id] = _tokenize(doc_text)
        log.debug(f"BM25 cache rebuilt: {len(_bm25_cache)} docs", module="rag")
    except Exception as e:
        log.warn(f"BM25 cache rebuild failed: {e}", module="rag")


def _bm25_search(query: str, doc_ids: list[str], k: int = 20) -> list[tuple[str, float]]:
    """BM25 sparse search cez doc_ids. Vráti [(doc_id, score), ...]."""
    if not _bm25_cache or not doc_ids:
        return []

    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    # BM25 parameters
    k1 = 1.5
    b = 0.75
    N = len(doc_ids)

    # Compute avg doc length
    doc_lengths = {did: len(_bm25_cache.get(did, [])) for did in doc_ids}
    avgdl = sum(doc_lengths.values()) / max(N, 1)

    # IDF pre query tokens
    results = []
    for did in doc_ids:
        doc_tokens = _bm25_cache.get(did, [])
        if not doc_tokens:
            continue
        dl = len(doc_tokens)
        score = 0.0
        for qt in query_tokens:
            # IDF
            n_qt = sum(1 for tks in _bm25_cache.values() if qt in tks)
            idf = max(0, math.log((N - n_qt + 0.5) / (n_qt + 0.5) + 1))
            # TF
            tf = doc_tokens.count(qt)
            numerator = tf * (k1 + 1)
            denominator = tf + k1 * (1 - b + b * dl / avgdl)
            score += idf * (numerator / denominator) if denominator > 0 else 0
        if score > 0:
            results.append((did, score))

    results.sort(key=lambda x: x[1], reverse=True)
    return results[:k]


# ── Hybrid Search ────────────────────────────────────────────────────────

def _hybrid_search(query: str, k: int = 5, min_score: float = 0.0,
                   filters: dict = None) -> list[dict]:
    """Dense + Sparse hybrid search s reciprocal rank fusion."""
    # Guard against empty/whitespace queries
    if not query or not query.strip():
        return []

    if _collection is None:
        return []

    all_docs = _collection.get()
    if not all_docs or not all_docs.get("ids"):
        return []

    total_docs = len(all_docs["ids"])

    # 1. Dense search (embedding-based)
    try:
        dense_results = _collection.query(query_texts=[query], n_results=min(total_docs, 50))
    except Exception as e:
        log.warn(f"Dense search failed: {e}", module="rag")
        dense_results = None

    # 2. Sparse search (BM25)
    sparse_results = _bm25_search(query, list(all_docs["ids"]), k=50)

    # 3. Reciprocal Rank Fusion
    scores = {}  # doc_id → fused_score

    # Dense ranks
    if dense_results and dense_results.get("ids") and dense_results["ids"][0]:
        for rank, doc_id in enumerate(dense_results["ids"][0]):
            similarity = 1.0 - float(dense_results["distances"][0][rank]) if dense_results.get("distances") else (1.0 / (rank + 1))
            scores[doc_id] = scores.get(doc_id, 0) + (1.0 / (rank + 60))  # RRF formula

    # Sparse ranks
    for rank, (doc_id, bm25_score) in enumerate(sparse_results):
        scores[doc_id] = scores.get(doc_id, 0) + (1.0 / (rank + 60))

    # Zoraď podľa fused score
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    # Fixed-scale normalization: use theoretical max RRF score (rank-0 in both
    # dense and sparse = 2/60 ≈ 0.0333) instead of empirical max. This means
    # nonsense queries get appropriately low scores instead of 100%.
    THEORETICAL_MAX_RRF = 2.0 / 60.0  # ≈0.0333 — perfect rank-0 in both dense+sparse

    if not ranked:
        return []

    # Formátuj výsledky
    results = []
    for doc_id, fused_score in ranked[:k]:
        # Zisti index v all_docs
        try:
            idx = all_docs["ids"].index(doc_id)
        except ValueError:
            continue
        doc_text = all_docs["documents"][idx] if all_docs.get("documents") else ""
        meta = all_docs["metadatas"][idx] if all_docs.get("metadatas") else {}
        # Fixed-scale normalization: score relative to theoretical max RRF
        similarity = round((fused_score / THEORETICAL_MAX_RRF) * 100)
        similarity = min(100, similarity)  # cap at 100

        # Score threshold
        if similarity < min_score * 100:
            continue

        # Metadata filter
        if filters:
            if "source" in filters and meta.get("source") != filters["source"]:
                continue
            if "tag" in filters and filters["tag"] not in meta.get("tags", []):
                continue
            if "since" in filters and meta.get("timestamp", 0) < filters["since"]:
                continue

        results.append({
            "id": doc_id,
            "text": doc_text[:200] if doc_text else "",
            "score": similarity,
            "metadata": meta,
        })

    return results


# ── Migrations ────────────────────────────────────────────────────────────

def _migrate_old_collection():
    """Presuň data zo starej kolekcie 'jarvis_memory' do 'jarvis_memory_v2'."""
    if _chroma_client is None or _collection is None:
        return
    try:
        old_col = _chroma_client.get_collection("jarvis_memory")
        old_docs = old_col.get()
        if not old_docs or not old_docs.get("ids"):
            return

        # Check ktoré už sú zmigrované
        existing = set(_collection.get().get("ids", []))
        new_ids = []
        new_docs = []
        new_metas = []

        for i, doc_id in enumerate(old_docs["ids"]):
            if doc_id in existing:
                continue
            new_ids.append(doc_id)
            new_docs.append(old_docs["documents"][i] if old_docs.get("documents") else "")
            new_metas.append(old_docs["metadatas"][i] if old_docs.get("metadatas") else {})

        if new_ids:
            _collection.add(ids=new_ids, documents=new_docs, metadatas=new_metas)
            log.info(f"Migrated {len(new_ids)} docs from v1 → v2 collection", module="rag")
            _rebuild_bm25_cache()
    except Exception:
        pass  # old collection doesn't exist yet or is empty


def _migrate_json_to_chroma():
    """Naindexuje JSON pamäte do ChromaDB v2."""
    if not os.path.exists(MEMORY_FILE) or _collection is None:
        return
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            mem = json.load(f)
    except Exception:
        return
    if not mem:
        return

    existing = set(_collection.get().get("ids", []))
    new_ids, new_docs, new_metas = [], [], []
    for k, v in mem.items():
        doc_id = f"json:{k}"
        if doc_id not in existing:
            new_ids.append(doc_id)
            new_docs.append(f"{k}: {v}")
            new_metas.append({"key": k, "source": "json", "timestamp": time.time()})

    if new_ids:
        _collection.add(ids=new_ids, documents=new_docs, metadatas=new_metas)
        log.info(f"Indexed {len(new_ids)} JSON facts → ChromaDB v2", module="rag")
        _rebuild_bm25_cache()


def _index_knowledge_files():
    """Naindexuje knowledge/*.md súbory do ChromaDB v2 (len zmenené)."""
    if not os.path.isdir(KNOWLEDGE_DIR) or _collection is None:
        return

    existing = {}
    try:
        all_docs = _collection.get()
        if all_docs and all_docs.get("ids") and all_docs.get("metadatas"):
            for doc_id, meta in zip(all_docs["ids"], all_docs["metadatas"]):
                if doc_id.startswith("knowledge:") and meta and "mtime" in meta:
                    existing[doc_id] = meta["mtime"]
    except Exception:
        pass

    new_ids, new_docs, new_metas = [], [], []
    for root, dirs, files in os.walk(KNOWLEDGE_DIR):
        for fname in files:
            if not fname.endswith(".md"):
                continue
            # Skip template files — they contain generic placeholder text that pollutes search
            if fname.startswith("_") or "TEMPLATE" in fname.upper():
                continue
            fpath = os.path.join(root, fname)
            try:
                mtime = os.path.getmtime(fpath)
            except OSError:
                continue
            rel_path = os.path.relpath(fpath, KNOWLEDGE_DIR).replace("\\", "/")
            doc_id = f"knowledge:{rel_path}"
            if doc_id in existing and existing[doc_id] == mtime:
                continue
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception:
                continue
            if not content.strip():
                continue
            title = os.path.splitext(fname)[0].replace("-", " ").replace("_", " ")
            new_ids.append(doc_id)
            new_docs.append(f"# {title}\n\n{content}")
            new_metas.append({"source": "knowledge", "path": rel_path, "mtime": mtime})

    if new_ids:
        _collection.upsert(ids=new_ids, documents=new_docs, metadatas=new_metas)
        log.info(f"Indexed {len(new_ids)} knowledge files → ChromaDB v2", module="rag")
        _rebuild_bm25_cache()


# ── Codebase Indexing ────────────────────────────────────────────────────

# Directories/files to skip when indexing code
_CODBASE_SKIP_DIRS = {"__pycache__", ".git", ".claude", "chroma_db", "venv", "env",
                       "node_modules", "hud", ".mypy_cache", ".pytest_cache"}
_CODBASE_SKIP_FILES = {".env", ".gitignore", "episodic_buffer.json", "jarvis_memory.json",
                       "auto_memory_counter.json", "requirements.txt"}
_CODBASE_EXTENSIONS = {".py", ".js", ".html", ".css", ".md", ".json"}


def _chunk_source_file(filepath: str, content: str) -> list[dict]:
    """Chunk a source file by function/class definitions or by logical blocks."""
    chunks = []
    lines = content.split("\n")
    rel_path = os.path.relpath(filepath, PROJECT_ROOT).replace("\\", "/")

    # Try to chunk by Python function/class definitions
    import re
    func_pattern = re.compile(r'^\s*(?:async\s+)?def\s+(\w+)|^\s*class\s+(\w+)')
    block_starts = []
    for i, line in enumerate(lines):
        m = func_pattern.match(line)
        if m:
            name = m.group(1) or m.group(2)
            block_starts.append((i, name))

    if block_starts and len(block_starts) >= 2:
        # Chunk by function/class boundaries (include line number for uniqueness)
        for j, (start_line, name) in enumerate(block_starts):
            end_line = block_starts[j + 1][0] if j + 1 < len(block_starts) else len(lines)
            chunk_lines = lines[start_line:end_line]
            chunk_text = "\n".join(chunk_lines).strip()
            if len(chunk_text) > 30:
                chunks.append({
                    "text": f"# {rel_path} → {name}() (line {start_line + 1})\n{chunk_text}",
                    "name": f"{rel_path}:{name}:L{start_line + 1}",
                })
    else:
        # No function boundaries found — chunk by ~50-line blocks
        block_size = 50
        for i in range(0, len(lines), block_size):
            chunk_lines = lines[i:i + block_size]
            chunk_text = "\n".join(chunk_lines).strip()
            if len(chunk_text) > 20:
                start_ln = i + 1
                end_ln = min(i + block_size, len(lines))
                chunks.append({
                    "text": f"# {rel_path} (lines {start_ln}-{end_ln})\n{chunk_text}",
                    "name": f"{rel_path}:L{start_ln}",
                })

    return chunks


def _index_codebase():
    """Index all project source files into ChromaDB for semantic code search."""
    if _collection is None:
        return

    existing = {}
    try:
        all_docs = _collection.get()
        if all_docs and all_docs.get("ids") and all_docs.get("metadatas"):
            for doc_id, meta in zip(all_docs["ids"], all_docs["metadatas"]):
                if doc_id.startswith("code:") and meta and "mtime" in meta:
                    existing[doc_id] = meta["mtime"]
    except Exception:
        pass

    new_ids, new_docs, new_metas = [], [], []
    files_scanned = 0

    for root, dirs, files in os.walk(PROJECT_ROOT):
        # Skip excluded directories
        dirs[:] = [d for d in dirs if d not in _CODBASE_SKIP_DIRS and not d.startswith(".")]

        for fname in files:
            if fname in _CODBASE_SKIP_FILES:
                continue
            ext = os.path.splitext(fname)[1].lower()
            if ext not in _CODBASE_EXTENSIONS:
                continue

            fpath = os.path.join(root, fname)
            try:
                mtime = os.path.getmtime(fpath)
            except OSError:
                continue

            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception:
                continue

            if not content.strip():
                continue

            rel_path = os.path.relpath(fpath, PROJECT_ROOT).replace("\\", "/")
            files_scanned += 1

            # Chunk the file
            chunks = _chunk_source_file(fpath, content)
            if not chunks:
                # Fallback: store the whole file
                doc_id = f"code:{rel_path}"
                if doc_id in existing and existing[doc_id] == mtime:
                    continue
                new_ids.append(doc_id)
                new_docs.append(f"# {rel_path}\n\n{content[:8000]}")
                new_metas.append({"source": "codebase", "path": rel_path, "mtime": mtime})
            else:
                for chunk in chunks:
                    doc_id = f"code:{chunk['name']}"
                    if doc_id in existing and existing[doc_id] == mtime:
                        continue
                    new_ids.append(doc_id)
                    new_docs.append(chunk["text"][:8000])
                    new_metas.append({"source": "codebase", "path": rel_path, "mtime": mtime})

    if new_ids:
        _collection.upsert(ids=new_ids, documents=new_docs, metadatas=new_metas)
        log.info(f"Indexed {len(new_ids)} code chunks from {files_scanned} files → ChromaDB v2", module="rag")
        _rebuild_bm25_cache()
    else:
        log.info(f"Codebase index up-to-date ({files_scanned} files)", module="rag")


# ── Public API ────────────────────────────────────────────────────────────

def rag_search(query: str, k: int = 5, min_score: float = 0.0,
               filters: dict = None) -> str:
    """Hybridné sémantické vyhľadávanie (dense + BM25 → RRF).

    Args:
        query: Vyhľadávací dopyt
        k: Počet výsledkov (max)
        min_score: Minimálne skóre 0-1 pre zaradenie výsledku
        filters: Voliteľné filtre {"source": "json", "tag": "personal", "since": timestamp}
    """
    if not query:
        return "(prázdny dotaz)"

    _ensure_init()

    try:
        results = _hybrid_search(query, k=k, min_score=min_score, filters=filters)
    except Exception as e:
        log.error(f"Search failed: {e}", module="rag", exc_info=True)
        return f"(Chyba vyhľadávania: {e})"

    if not results:
        return "(nič nenájdené)"

    lines = [f'🔍 Výsledky pre: "{query}"']
    for i, r in enumerate(results):
        doc_type = r["metadata"].get("source", "?")
        lines.append(f"  {i+1}. [{r['score']}%] {r['text'][:120]} ({doc_type})")
    return "\n".join(lines)


def rag_save(key: str, value: str, tags: list[str] = None) -> str:
    """Uloží fakt do ChromaDB v2 aj JSON pamäte."""
    if not key or value is None:
        return "Chyba: key a value sú povinné."

    _ensure_init()

    doc_id = f"json:{key}"
    doc_text = f"{key}: {value}"

    try:
        _collection.upsert(
            ids=[doc_id],
            documents=[doc_text],
            metadatas=[{"key": key, "source": "json", "timestamp": time.time(),
                        "tags": json.dumps(tags or [])}],
        )
        # Update BM25 cache
        _bm25_cache[doc_id] = _tokenize(doc_text)
    except Exception as e:
        log.error(f"ChromaDB upsert failed: {e}", module="rag")
        return f"Chyba: {e}"

    # JSON persist
    from tools.memory import _load_memory, _save_memory
    mem = _load_memory()
    mem[key] = str(value)
    _save_memory(mem)

    return f"Uložené: {key} = {value}"


def rag_read(key: str = None) -> str:
    """Číta z pamäte. key=None → kompletný dump + štatistiky."""
    _ensure_init()

    if key:
        try:
            results = _collection.get(ids=[f"json:{key}"])
            if results and results.get("documents"):
                return results["documents"][0]
        except Exception:
            pass
        from tools.memory import _load_memory
        mem = _load_memory()
        return f"{key}: {mem.get(key, '(neuložené)')}"

    # Full dump
    import json as _json
    from tools.memory import _load_memory
    mem = _load_memory()
    json_data = _json.dumps(mem, ensure_ascii=False, indent=2) if mem else "(pamäť prázdna)"

    try:
        all_docs = _collection.get()
        total = len(all_docs["ids"]) if all_docs and all_docs.get("ids") else 0
        k_count = sum(1 for did in (all_docs.get("ids") or []) if did.startswith("knowledge:"))
        j_count = total - k_count
        json_data += f"\n\n📊 ChromaDB v2 ({EMBED_MODEL}): {total} záznamov ({j_count} faktov, {k_count} knowledge)"
        json_data += f"\n🔀 Hybrid search: dense + BM25 ready ({len(_bm25_cache)} docs in BM25 cache)"
    except Exception:
        pass

    return json_data


def rag_delete(key: str) -> str:
    """Vymaže fakt z ChromaDB, BM25 cache, aj JSON."""
    if not key:
        return "Chyba: key je povinný."

    _ensure_init()

    doc_id = f"json:{key}"
    try:
        _collection.delete(ids=[doc_id])
        _bm25_cache.pop(doc_id, None)
    except Exception as e:
        log.warn(f"ChromaDB delete failed: {e}", module="rag")

    from tools.memory import _load_memory, _save_memory
    mem = _load_memory()
    if key in mem:
        del mem[key]
        _save_memory(mem)
        return f"Vymazané: {key}"
    return f"Kľúč '{key}' v pamäti nie je."
