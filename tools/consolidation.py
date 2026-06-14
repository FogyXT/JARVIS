"""
Consolidation Pipeline — spánkový replay a reorganizácia pamäte (medzi-tierová).

Inšpirované:
- Slow-wave sleep replay (McNaughton/Bazhenov 2025)
- CortexGraph multi-agent pipeline (prefrontal-systems 2026)
- Complementary Learning Systems theory

Režimy:
- quick: len deterministické operácie, žiadne LLM, <1s
         (decay, cluster, score, promote) — každých 5 minút
- full:  LLM-powered merging a relationship discovery
         (používa Haiku pre lacné volania) — počas idle alebo manuálne

7 stupňov pipeline:
  1. DecayAnalyzer      — aplikuj Ebbinghaus decay, označ na zabudnutie
  2. ClusterDetector    — nájdi podobné spomienky podľa embeddingu
  3. SemanticMerger     — zlúč duplicitné/podobné spomienky (LLM)
  4. ImportanceScorer   — pre-skóruj podľa prístupových vzorov
  5. Promoter           — povýš vysoké skóre do semantic store
  6. RelationshipFinder — objav nové vzťahy medzi spomienkami (LLM)
  7. Archiver           — presuň staré nízko-dôležité do cold archive

Použitie:
    from tools.consolidation import consolidate_quick, consolidate_full, is_idle
    consolidate_quick()  # volať periodicky
    if is_idle(900):     # 15 minút nečinnosti
        consolidate_full()
"""

import os
import sys
import json
import time
import math
from typing import Optional, Any

import numpy as np

from tools.jarvis_logging import log


# ── Config ────────────────────────────────────────────────────────────────

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCHIVE_DIR = os.path.join(PROJECT_ROOT, "archive", "memories")

# How long since last user interaction before "idle" (seconds)
IDLE_THRESHOLD = 900  # 15 minutes

# Min cluster similarity for SemanticMerger
MERGE_SIMILARITY_THRESHOLD = 0.85

# Age threshold for Archiver (seconds) — memories older than this get archived
ARCHIVE_AGE_THRESHOLD = 90 * 24 * 3600  # 90 days

# ── Idle Detection ───────────────────────────────────────────────────────

_last_interaction = time.time()


def touch():
    """Zaznač používateľskú interakciu — resetuje idle timer."""
    global _last_interaction
    _last_interaction = time.time()


def is_idle(threshold: float = IDLE_THRESHOLD) -> bool:
    """Je systém nečinný dlhšie ako threshold sekúnd?"""
    return (time.time() - _last_interaction) > threshold


def idle_seconds() -> float:
    """Koľko sekúnd od poslednej interakcie."""
    return time.time() - _last_interaction


# ── Helpers ───────────────────────────────────────────────────────────────

def _get_buf():
    try:
        from tools.episodic_memory import get_buffer
        return get_buffer()
    except ImportError:
        return None


def _get_kg():
    try:
        from tools.knowledge_graph import get_graph
        return get_graph()
    except ImportError:
        return None


def _get_json_mem():
    try:
        from tools.memory import _load_memory
        return _load_memory()
    except ImportError:
        return {}


def _get_embed_fn():
    try:
        from tools.episodic_memory import _embed_text
        return _embed_text
    except ImportError:
        return None


# ── Stage 1: DecayAnalyzer ───────────────────────────────────────────────

def _stage_decay(buf) -> dict:
    """Aplikuj Ebbinghaus decay na všetky položky. Vráť štatistiky."""
    if buf is None:
        return {"decayed": 0, "forgotten": 0}

    before = buf.size()
    buf.decay(target="both")
    after = buf.size()

    result = {
        "decayed": before["total"],
        "forgotten": before["total"] - after["total"],
        "working_before": before["working"],
        "working_after": after["working"],
        "episodic_before": before["episodic"],
        "episodic_after": after["episodic"],
    }
    log.debug(f"Decay: {result['forgotten']} forgotten", module="consolidation", data=result)
    return result


# ── Stage 2: ClusterDetector ─────────────────────────────────────────────

def _stage_cluster(buf) -> list[list[dict]]:
    """Nájdi skupiny podobných spomienok (embedding similarity)."""
    if buf is None or buf.size()["total"] < 2:
        return []

    embed_fn = _get_embed_fn()
    if embed_fn is None:
        return []

    # Combine all items
    all_items = [(i, "working") for i in buf.working] + [(i, "episodic") for i in buf.episodic]
    if len(all_items) < 2:
        return []

    # Get or compute embeddings
    texts = [f"{item.key}: {item.value}" for item, _ in all_items]
    try:
        embeddings = np.array([embed_fn(t) for t in texts])
    except Exception as e:
        log.warn(f"Embedding failed in cluster: {e}", module="consolidation")
        return []

    # Normalize
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True) + 1e-8
    embeddings = embeddings / norms

    # Cosine similarity matrix
    sim_matrix = np.dot(embeddings, embeddings.T)

    # Find pairs above threshold (upper triangle only, exclude diagonal)
    clusters = []
    used = set()
    n = len(all_items)

    for i in range(n):
        if i in used:
            continue
        cluster = [{"key": all_items[i][0].key, "value": all_items[i][0].value,
                     "source": all_items[i][1]}]
        used.add(i)
        for j in range(i + 1, n):
            if j in used:
                continue
            if sim_matrix[i][j] >= MERGE_SIMILARITY_THRESHOLD:
                cluster.append({"key": all_items[j][0].key, "value": all_items[j][0].value,
                                "source": all_items[j][1]})
                used.add(j)
        if len(cluster) >= 2:
            clusters.append(cluster)

    if clusters:
        log.info(f"Clusters found: {len(clusters)} groups",
                module="consolidation",
                data={"groups": [[c["key"] for c in g] for g in clusters[:5]]})

    return clusters


# ── LLM Helper (DeepSeek V4 Flash) ────────────────────────────────────────

def _deepseek_quick(prompt: str, max_tokens: int = 300) -> str:
    """Zavolá DeepSeek V4 Flash pre rýchlu, lacnú odpoveď."""
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        log.warn("DEEPSEEK_API_KEY not set — using deterministic fallback", module="consolidation")
        return ""

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=0.1,  # low temp = konzistentné
            stream=False,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        log.warn(f"DeepSeek call failed: {e}", module="consolidation")
        return ""


# ── Stage 3: SemanticMerger ──────────────────────────────────────────────

def _stage_merge(clusters: list[list[dict]], use_llm: bool = False) -> dict:
    """Zlúč podobné spomienky.

    Quick mode: deterministicky — vezme najdlhšiu hodnotu.
    Full mode:  DeepSeek rozhodne či a ako zlúčiť.
    """
    if not clusters:
        return {"merged": 0, "skipped": 0, "llm_used": use_llm}

    merged = 0
    skipped = 0
    llm_calls = 0

    for cluster in clusters:
        if len(cluster) < 2:
            skipped += 1
            continue

        if use_llm:
            # LLM-powered merge: DeepSeek rozhodne čo si nechať
            items_text = "\n".join(
                f"{i+1}. [{c['key']}] {c['value']}"
                for i, c in enumerate(cluster)
            )
            prompt = f"""Merge these similar memories into ONE concise, complete memory.
Keep ALL unique information. Remove only exact duplicates.

{items_text}

Return ONLY the merged text, nothing else. No markdown, no explanation."""

            merged_value = _deepseek_quick(prompt, max_tokens=200)
            if merged_value:
                llm_calls += 1
            else:
                # Fallback: deterministic
                merged_value = max(cluster, key=lambda x: len(x["value"]))["value"]
        else:
            # Deterministic merge
            merged_value = max(cluster, key=lambda x: len(x["value"]))["value"]

        best = max(cluster, key=lambda x: len(x["value"]))
        merged_key = f"merged:{best['key']}"

        try:
            from tools.memory import memory
            for item in cluster:
                if item["key"] != best["key"]:
                    memory("delete", key=item["key"])
            memory("save", merged_key,
                   f"[Merged {len(cluster)} memories] {merged_value}")
            merged += 1
            log.debug(f"Merged: {merged_key}", module="consolidation",
                     data={"sources": [c["key"] for c in cluster], "llm": use_llm})
        except Exception as e:
            log.warn(f"Merge failed: {e}", module="consolidation")
            skipped += 1

    return {"merged": merged, "skipped": skipped, "llm_calls": llm_calls}


# ── Stage 4: ImportanceScorer ────────────────────────────────────────────

def _stage_rescore(buf) -> dict:
    """Prehodnoť importance scores na základe access patternov."""
    if buf is None:
        return {"rescored": 0, "boosted": 0, "demoted": 0}

    boosted = 0
    demoted = 0

    for item in buf.episodic + buf.working:
        old_score = item.importance

        # Boost: často prístupované položky
        if item.access_count >= 10:
            item.importance = min(1.0, item.importance + 0.2)
            boosted += 1
        elif item.access_count >= 5:
            item.importance = min(1.0, item.importance + 0.1)
            boosted += 1

        # Demote: nízky prístup + staré
        age_seconds = time.time() - item.timestamp
        if item.access_count <= 1 and age_seconds > 7 * 24 * 3600:  # 7 days
            item.importance = max(0.1, item.importance - 0.2)
            demoted += 1

        if abs(item.importance - old_score) > 0.01:
            item.embedding = None  # invalidate cached embedding

    if boosted or demoted:
        log.info(f"Rescore: +{boosted} boosted, -{demoted} demoted", module="consolidation")

    return {"rescored": boosted + demoted, "boosted": boosted, "demoted": demoted}


# ── Stage 5: Promoter ────────────────────────────────────────────────────

def _stage_promote(buf) -> dict:
    """Povýš vysoko-skórované spomienky z episodic do semantic store."""
    if buf is None:
        return {"promoted": 0}

    # Get promotable items
    promotable = buf.get_promotable()
    if not promotable:
        return {"promoted": 0}

    # Promote each to semantic store (ChromaDB)
    for item in promotable:
        try:
            from tools.rag_memory import rag_save
            rag_save(item.key, item.value)
            log.info(f"Promoted to semantic: {item.key} (score={item.current_score:.3f})",
                    module="consolidation")
        except Exception as e:
            log.warn(f"Promotion failed for {item.key}: {e}", module="consolidation")

    # Remove from episodic buffer
    buf.remove_promoted(promotable)

    return {"promoted": len(promotable)}


# ── Stage 6: RelationshipFinder ──────────────────────────────────────────

def _stage_relationships(use_llm: bool = False) -> dict:
    """Objav nové vzťahy medzi entitami v knowledge grafe.

    Quick mode: count-based — 3+ shared neighbors → inferred relation.
    Full mode:  DeepSeek navrhne vzťahy medzi často sa vyskytujúcimi entitami.
    """
    kg = _get_kg()
    if kg is None or kg.graph.number_of_nodes() < 3:
        return {"new_relations": 0, "llm_used": use_llm}

    new_edges = 0
    llm_calls = 0

    if use_llm:
        # Get top entities by degree for LLM analysis
        degrees = dict(kg.graph.degree())
        top_entities = sorted(degrees.items(), key=lambda x: x[1], reverse=True)[:20]
        top_names = [kg.graph.nodes[eid].get("name", eid) for eid, _ in top_entities]

        if len(top_names) >= 3:
            prompt = f"""These entities appear in a user's AI memory system:

{', '.join(top_names)}

Suggest up to 5 meaningful relationships between pairs of these entities.
Use relation types: uses, builds, depends_on, inspired_by, part_of, works_on.

Return ONLY lines in format: EntityA → EntityB (relation_type)
No markdown, no explanation, one per line."""

            response = _deepseek_quick(prompt, max_tokens=200)
            if response:
                llm_calls += 1
                # Parse response and add edges
                for line in response.strip().split("\n"):
                    line = line.strip()
                    if "→" in line:
                        try:
                            parts = line.split("→")
                            a_name = parts[0].strip()
                            rest = parts[1].strip()
                            b_name = rest.split("(")[0].strip()
                            rel_type = rest.split("(")[1].rstrip(")") if "(" in rest else "related_to"

                            # Find node IDs
                            nodes_a = [n for n, d in kg.graph.nodes(data=True)
                                       if d.get("name", "").lower() == a_name.lower()]
                            nodes_b = [n for n, d in kg.graph.nodes(data=True)
                                       if d.get("name", "").lower() == b_name.lower()]

                            if nodes_a and nodes_b and not kg.graph.has_edge(nodes_a[0], nodes_b[0]):
                                kg.graph.add_edge(nodes_a[0], nodes_b[0], relation=rel_type)
                                kg.graph.add_edge(nodes_b[0], nodes_a[0], relation=rel_type)
                                new_edges += 1
                        except (IndexError, ValueError):
                            pass

    # Always run deterministic fallback too (catches what LLM might miss)
    nodes = list(kg.graph.nodes(data=True))
    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            nid_a, data_a = nodes[i]
            nid_b, data_b = nodes[j]
            if kg.graph.has_edge(nid_a, nid_b):
                continue
            neighbors_a = set(kg.graph.neighbors(nid_a))
            neighbors_b = set(kg.graph.neighbors(nid_b))
            if len(neighbors_a & neighbors_b) >= 3:
                kg.graph.add_edge(nid_a, nid_b, relation="inferred_related_to")
                kg.graph.add_edge(nid_b, nid_a, relation="inferred_related_to")
                new_edges += 1

    if new_edges:
        log.info(f"Discovered {new_edges} new relations (LLM: {llm_calls} calls)",
                module="consolidation")

    return {"new_relations": new_edges, "llm_calls": llm_calls}


# ── Stage 7: Archiver ────────────────────────────────────────────────────

def _stage_archive(buf) -> dict:
    """Presuň veľmi staré, nízko-dôležité spomienky do cold archive (Tier 5)."""
    if buf is None:
        return {"archived": 0}

    now = time.time()
    to_archive = []

    for lst in [buf.episodic, buf.working]:
        for item in list(lst):
            age = now - item.timestamp
            if (age > ARCHIVE_AGE_THRESHOLD and
                item.importance < 0.3 and
                item.access_count <= 2):
                to_archive.append({
                    "key": item.key, "value": item.value,
                    "timestamp": item.timestamp, "last_access": item.last_access,
                    "access_count": item.access_count, "importance": item.importance,
                    "current_score": item.current_score, "tags": item.tags,
                })
                # Remove from buffer
                for lst_remove in [buf.working, buf.episodic]:
                    if item in lst_remove:
                        lst_remove.remove(item)

    if not to_archive:
        return {"archived": 0}

    # Use ColdArchive (Tier 5) for proper long-term storage
    try:
        from tools.cold_archive import get_archive
        archive = get_archive()
        n = archive.archive(to_archive)
        log.info(f"Archived {n} memories to cold storage", module="consolidation")
        return {"archived": n}
    except Exception as e:
        log.error(f"Archive failed: {e}", module="consolidation")
        return {"archived": 0, "error": str(e)}


# ── Pipeline API ─────────────────────────────────────────────────────────

def consolidate_quick() -> dict:
    """Rýchla konsolidácia — žiadne LLM volania, <1s.

    Spúšťa sa automaticky každých 5 minút.
    """
    log.debug("Quick consolidation starting...", module="consolidation")
    t0 = time.perf_counter()

    buf = _get_buf()

    results = {
        "mode": "quick",
        "decay": _stage_decay(buf),
        "rescore": _stage_rescore(buf),
        "promote": _stage_promote(buf),
    }

    # Persist buffer state to disk (prevents loss on server restart)
    if buf:
        try:
            buf.save()
        except Exception:
            pass

    elapsed = (time.perf_counter() - t0) * 1000
    results["elapsed_ms"] = round(elapsed, 1)
    log.debug(f"Quick consolidation done ({elapsed:.1f}ms)", module="consolidation",
             data=results)
    return results


def consolidate_full() -> dict:
    """Plná konsolidácia — zahŕňa LLM-powered merging a relationship discovery.

    Spúšťa sa počas idle (15+ minút) alebo manuálne.
    """
    log.info("Full consolidation starting...", module="consolidation")
    t0 = time.perf_counter()

    buf = _get_buf()

    # Quick stages first
    decay = _stage_decay(buf)
    clusters = _stage_cluster(buf)

    # LLM-powered merge (DeepSeek V4 Flash)
    merge = _stage_merge(clusters, use_llm=True)

    # Scoring and promotion
    rescore = _stage_rescore(buf)
    promote = _stage_promote(buf)

    # Graph relationship discovery (LLM + deterministic)
    relations = _stage_relationships(use_llm=True)

    # Archive old memories
    archive = _stage_archive(buf)

    # Neurogenesis: spawn new agents from memory clusters
    neuro = {}
    try:
        from tools.memory_agents import neurogenesis
        neuro = neurogenesis()
    except Exception as e:
        log.debug(f"Neurogenesis skipped: {e}", module="consolidation")

    # Save buffer state
    if buf:
        buf.save()

    results = {
        "mode": "full",
        "decay": decay,
        "clusters_found": len(clusters),
        "merge": merge,
        "rescore": rescore,
        "promote": promote,
        "relations": relations,
        "archive": archive,
        "neurogenesis": neuro,
    }

    elapsed = (time.perf_counter() - t0) * 1000
    results["elapsed_ms"] = round(elapsed, 1)
    log.info(f"Full consolidation done ({elapsed:.1f}ms)", module="consolidation",
             data=results)
    return results


def get_stats() -> dict:
    """Vráť štatistiky o pipeline a idle stave."""
    buf = _get_buf()
    kg = _get_kg()

    return {
        "idle_seconds": idle_seconds(),
        "is_idle": is_idle(),
        "idle_threshold": IDLE_THRESHOLD,
        "buffer": buf.health() if buf else None,
        "knowledge_graph": kg.stats() if kg else None,
    }


# ── Auto-Scheduler ────────────────────────────────────────────────────────

_scheduler_running = False
_scheduler_thread = None
_QUICK_INTERVAL = 300  # 5 minút
_FULL_COOLDOWN = 3600  # 1 hodina medzi full konsolidáciami
_last_full_run = 0


def _scheduler_loop():
    """Beží v daemon threade. Spúšťa quick konsolidáciu každých 5 minút,
    full konsolidáciu keď je idle > 15 minút (max raz za hodinu)."""
    global _last_full_run
    log.info("Consolidation scheduler started", module="consolidation",
             data={"quick_interval_s": _QUICK_INTERVAL, "full_cooldown_s": _FULL_COOLDOWN})

    while _scheduler_running:
        time.sleep(_QUICK_INTERVAL)

        if not _scheduler_running:
            break

        try:
            # Quick consolidation always
            result = consolidate_quick()
            log.debug(f"Scheduled quick consolidation: {result['elapsed_ms']}ms",
                     module="consolidation")

            # Full consolidation if idle and cooldown passed
            if is_idle() and (time.time() - _last_full_run) > _FULL_COOLDOWN:
                result = consolidate_full()
                _last_full_run = time.time()
                log.info(f"Scheduled full consolidation: {result['elapsed_ms']}ms",
                        module="consolidation")
        except Exception as e:
            log.error(f"Scheduler error: {e}", module="consolidation", exc_info=True)


def start_scheduler():
    """Spusti konsolidačný scheduler ako daemon thread."""
    global _scheduler_running, _scheduler_thread
    if _scheduler_running:
        log.debug("Scheduler already running", module="consolidation")
        return

    import threading
    _scheduler_running = True
    _scheduler_thread = threading.Thread(target=_scheduler_loop, daemon=True,
                                         name="consolidation-scheduler")
    _scheduler_thread.start()
    log.info("Consolidation scheduler thread started", module="consolidation")


def stop_scheduler():
    """Zastav konsolidačný scheduler."""
    global _scheduler_running
    _scheduler_running = False
    log.info("Consolidation scheduler stopping", module="consolidation")
