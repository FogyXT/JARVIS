"""
Dlhodobá pamäť JARVIS — 3-vrstvová architektúra.

Vrstvy:
1. EpisodicBuffer — rýchly, s Ebbinghaus decay (working 64 + episodic 256)
2. JSON — trvalý key-value store (jarvis_memory.json)
3. ChromaDB — sémantické vyhľadávanie (cez tools.rag_memory)

Flow:
- save → EpisodicBuffer.store() + JSON + ChromaDB index
- read  → EpisodicBuffer.retrieve() first → ChromaDB fallback → JSON fallback
- delete → remove from all 3 layers
"""

import os
import json
import time

from tools.jarvis_logging import log

MEMORY_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "jarvis_memory.json")


def _load_memory():
    """Načíta JSON pamäť z disku."""
    if not os.path.exists(MEMORY_FILE):
        return {}
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_memory(mem: dict):
    """Uloží JSON pamäť na disk."""
    os.makedirs(os.path.dirname(MEMORY_FILE), exist_ok=True)
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(mem, f, indent=2, ensure_ascii=False)


def _get_buffer():
    """Získa singleton EpisodicBuffer (lenivá inicializácia)."""
    try:
        from tools.episodic_memory import get_buffer
        return get_buffer()
    except ImportError as e:
        log.warn(f"EpisodicBuffer not available: {e}", module="memory")
        return None


def _decay_if_needed():
    """Aplikuje decay na EpisodicBuffer raz za 5 minút."""
    try:
        from tools.episodic_memory import get_buffer, _decay_timer
        now = time.time()
        if now - _decay_timer.get("last", 0) > 300:  # 5 minút
            buf = get_buffer()
            if buf:
                buf.decay(target="both")
                _decay_timer["last"] = now
    except Exception:
        pass


_decay_timer = {"last": 0}


def memory(action, key=None, value=None):
    """Dlhodobá pamäť pre ukladanie faktov o používateľovi (Fogy).

    Actions:
        save   — uloží fakt do všetkých 3 vrstiev
        read   — číta: EpisodicBuffer → ChromaDB → JSON
        delete — vymaže zo všetkých vrstiev

    Pre RAG/sémantické vyhľadávanie použi rag_search z tools.rag_memory.
    """
    log.debug(f"memory({action}, key={key})", module="memory",
             data={"value_len": len(str(value)) if value else 0})

    # Mark user interaction for idle detection
    try:
        from tools.consolidation import touch
        touch()
    except ImportError:
        pass

    mem = _load_memory()
    buf = _get_buffer()
    _decay_if_needed()

    # ── SAVE ──────────────────────────────────────────────────────────
    if action == "save":
        if not key:
            return "Chyba: 'key' je povinný pre save."
        val_str = value if value is not None else ""

        # Vrstva 1: EpisodicBuffer (rýchla, s decay)
        if buf:
            importance = 0.7 if len(val_str) > 20 else 0.5
            buf.store(key, val_str, importance=importance)
            log.debug(f"Stored in EpisodicBuffer: {key}", module="memory")

        # Vrstva 2: JSON (trvalý)
        mem[key] = val_str
        _save_memory(mem)

        # Vrstva 3: ChromaDB (sémantický)
        try:
            from tools.rag_memory import _ensure_init, _collection
            _ensure_init()
            if _collection is not None:
                doc_id = f"json:{key}"
                doc_text = f"{key}: {val_str}"
                _collection.upsert(
                    ids=[doc_id],
                    documents=[doc_text],
                    metadatas=[{"key": key, "source": "json", "timestamp": time.time()}],
                )
        except ImportError:
            pass
        except Exception as e:
            log.warn(f"ChromaDB upsert failed: {e}", module="memory")

        # Vrstva 4: Knowledge Graph (entity extraction + relations)
        try:
            from tools.knowledge_graph import get_graph
            kg = get_graph()
            kg.add_memory(key, val_str)
        except Exception as e:
            log.debug(f"KG extraction skipped: {e}", module="memory")

        return f"Uložené: {key} = {val_str}"

    # ── READ ──────────────────────────────────────────────────────────
    if action == "read":
        # Presný kľúč
        if key:
            # 1. EpisodicBuffer (najrýchlejší)
            if buf:
                results = buf.retrieve(key=key)
                if results:
                    r = results[0]
                    return f"{r['key']}: {r['value']} (score: {r['score']:.3f}, source: {r['source']})"

            # 2. ChromaDB
            try:
                from tools.rag_memory import rag_read as _rag_read
                rag_result = _rag_read(key)
                if rag_result and "(neuložené)" not in rag_result:
                    # Re-store v EpisodicBuffer pre budúce rýchle čítania
                    if buf and key in mem:
                        buf.store(key, mem[key], importance=0.5)
                        log.debug(f"Re-stored in buffer from ChromaDB: {key}", module="memory")
                    return rag_result
            except ImportError:
                pass

            # 3. JSON (posledná záchrana)
            if key in mem:
                val = mem[key]
                # Re-store v EpisodicBuffer pre budúce rýchle čítania + reinforcement
                if buf:
                    buf.store(key, val, importance=0.5)
                    log.debug(f"Re-stored in buffer from JSON: {key}", module="memory")
                return f"{key}: {val}"

            # 4. Cold Archive (Tier 5) — thaw from long-term filesystem storage
            try:
                from tools.cold_archive import get_archive
                archive = get_archive()
                thawed = archive.thaw(key=key)
                if thawed:
                    val = thawed[0].get("value", "")
                    # Re-store in upper tiers for faster future access
                    if val:
                        if buf:
                            buf.store(key, val, importance=0.4)
                        _save_memory(mem)
                        return f"{key}: {val} (source: cold_archive)"
            except Exception as e:
                log.debug(f"Cold archive thaw failed: {e}", module="memory")

            return f"{key}: (neuložené)"

        # Celá pamäť
        base = json.dumps(mem, ensure_ascii=False, indent=2) if mem else "(pamäť prázdna)"

        # Pridaj EpisodicBuffer info
        if buf:
            size = buf.size()
            health = buf.health()
            base += f"\n\n⚡ Episodic Buffer: {size['working']}w + {size['episodic']}e"
            base += f"\n   Avg score: w={health['avg_score_working']:.3f}, e={health['avg_score_episodic']:.3f}"
            base += f"\n   Stats: {health['stats']['stores']} stores, {health['stats']['retrievals']} retrievals, "
            base += f"{health['stats']['forgets']} forgotten, {health['stats']['promotions']} promoted"

        # Pridaj ChromaDB info
        try:
            from tools.rag_memory import rag_read as _rag_read
            rag_full = _rag_read()
            if "ChromaDB" in rag_full:
                # Extrahuj len ChromaDB riadok
                for line in rag_full.split("\n"):
                    if "ChromaDB:" in line:
                        base += f"\n📊 {line.strip()}"
                        break
        except ImportError:
            pass

        # Pridaj Knowledge Graph context (Tier 4 — was write-only, now queried during retrieval)
        try:
            from tools.knowledge_graph import get_graph
            kg = get_graph()
            kg_ctx = kg.get_context("general memory overview", max_hops=2)
            if kg_ctx and kg_ctx != "(no graph context found)":
                base += f"\n\n🧠 Knowledge Graph:\n{kg_ctx}"
        except Exception:
            pass

        return base

    # ── DELETE ────────────────────────────────────────────────────────
    if action == "delete":
        if key and key in mem:
            del mem[key]
            _save_memory(mem)

            # Odstráň aj z EpisodicBuffer (ak tam je)
            if buf:
                for lst in [buf.working, buf.episodic]:
                    for item in list(lst):
                        if item.key == key:
                            lst.remove(item)
                            log.debug(f"Deleted from EpisodicBuffer: {key}", module="memory")

            # Odstráň z ChromaDB
            try:
                from tools.rag_memory import _ensure_init, _collection
                _ensure_init()
                if _collection is not None:
                    _collection.delete(ids=[f"json:{key}"])
            except ImportError:
                pass
            except Exception as e:
                log.warn(f"ChromaDB delete failed: {e}", module="memory")

            return f"Vymazané: {key}"
        return f"Kľúč '{key}' v pamäti nie je."

    return f"Neznáma akcia pamäte: {action}"


def memory_diagnose(query: str) -> str:
    """Diagnostic trace: show the full retrieval path for a query across all 5 tiers.

    Returns a formatted report showing which tier found what, scores, and timing.
    Use this to debug why a query returned or didn't return expected results.
    """
    import time as _time
    lines = [f'🔍 MEMORY DIAGNOSE: "{query}"', "=" * 50]

    # Tier 1+2: EpisodicBuffer
    try:
        from tools.episodic_memory import get_buffer
        buf = get_buffer()
        t0 = _time.perf_counter()
        epi_results = buf.retrieve(query=query, k=3) if buf else []
        epi_ms = (_time.perf_counter() - t0) * 1000
        lines.append(f"\n📦 TIER 1+2 (Episodic, {epi_ms:.1f}ms):")
        lines.append(f"   Buffer state: {buf.size() if buf else 'N/A'}")
        if epi_results:
            for r in epi_results:
                lines.append(f"   ✅ [{r['score']:.3f}] [{r['source']}] {r['value'][:80]}")
        else:
            lines.append(f"   ❌ No results (buffer empty or no match)")
    except Exception as e:
        lines.append(f"\n📦 TIER 1+2: ERROR — {e}")

    # Tier 3: ChromaDB hybrid search
    try:
        import tools.rag_memory as rm
        rm._ensure_init()
        t0 = _time.perf_counter()
        sem_results = rm._hybrid_search(query, k=3, min_score=0.0)
        sem_ms = (_time.perf_counter() - t0) * 1000
        lines.append(f"\n🧬 TIER 3 (ChromaDB hybrid, {sem_ms:.1f}ms):")
        if sem_results:
            for r in sem_results:
                lines.append(f"   ✅ [{r['score']}%] [{r['metadata'].get('source','?')}] {r['text'][:100]}")
        else:
            lines.append(f"   ❌ No results")
    except Exception as e:
        lines.append(f"\n🧬 TIER 3: ERROR — {e}")

    # Tier 4: Knowledge Graph
    try:
        from tools.knowledge_graph import get_graph
        kg = get_graph()
        t0 = _time.perf_counter()
        kg_ctx = kg.get_context(query, max_hops=2)
        kg_ms = (_time.perf_counter() - t0) * 1000
        lines.append(f"\n🔗 TIER 4 (Knowledge Graph, {kg_ms:.1f}ms):")
        lines.append(f"   Entities: {kg.graph.number_of_nodes()}, Relations: {kg.graph.number_of_edges()}")
        if kg_ctx and len(kg_ctx) > 20:
            for line in kg_ctx.split('\n')[:5]:
                clean = line.strip()
                if clean and not clean.startswith('🕸'):
                    lines.append(f"   ✅ {clean[:100]}")
        else:
            lines.append(f"   ❌ No graph context found")
    except Exception as e:
        lines.append(f"\n🔗 TIER 4: ERROR — {e}")

    # Tier 5: Cold Archive
    try:
        from tools.cold_archive import get_archive
        archive = get_archive()
        t0 = _time.perf_counter()
        arch_results = archive.search(query, max_results=3)
        arch_ms = (_time.perf_counter() - t0) * 1000
        lines.append(f"\n💾 TIER 5 (Cold Archive, {arch_ms:.1f}ms):")
        lines.append(f"   Indexed keys: {len(archive._index)}")
        if arch_results:
            for r in arch_results:
                lines.append(f"   ✅ {r.get('key','?')}: {r.get('value','')[:100]}")
        else:
            lines.append(f"   ❌ No archived results")
    except Exception as e:
        lines.append(f"\n💾 TIER 5: ERROR — {e}")

    return "\n".join(lines)
