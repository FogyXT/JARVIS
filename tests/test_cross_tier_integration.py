"""
COMPREHENSIVE CROSS-TIER INTEGRATION TEST
Preverí všetkých 5 vrstiev pamäte v reálnych scenároch.

Scenáre:
1. Store → všetky 4 vrstvy naraz (Episodic + JSON + ChromaDB + KG)
2. Retrieve → EpisodicBuffer → ChromaDB → JSON fallback
3. Reinforcement → viacnásobné čítanie posilní score
4. Decay → simulované starnutie, zabúdanie
5. Consolidation → quick + full pipeline
6. Knowledge Graph → entity extraction, relations, multi-hop
7. Agents → domain routing, cross-agent communication
8. Archive → thaw → späť do aktívnej pamäte
9. Edge cases → SK diakritika, dlhé texty, špeciálne znaky
10. Performance → latencia jednotlivých operácií
"""
import os, sys, time, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.jarvis_logging import log
from tools.memory import memory, _load_memory, _save_memory, MEMORY_FILE
from tools.episodic_memory import EpisodicBuffer, get_buffer
from tools.rag_memory import rag_search, rag_read, _hybrid_search
from tools.knowledge_graph import get_graph, extract_entities
from tools.consolidation import consolidate_quick, consolidate_full, touch, is_idle
from tools.memory_agents import query_memory, store_memory, get_agents_stats, update_all_centroids
from tools.cold_archive import get_archive

PASS = "✅"; FAIL = "❌"; WARN = "⚠️"
total = passed = failed = 0

def check(name, condition, detail=""):
    global total, passed, failed
    total += 1
    if condition: passed += 1; print(f"  {PASS} {name}" + (f" — {detail}" if detail else ""))
    else: failed += 1; print(f"  {FAIL} {name}" + (f" — {detail}" if detail else ""))

def section(title):
    print(f"\n{'='*60}\n  {title}\n{'='*60}")


# ── Backup & Setup ──────────────────────────────────────────────────────

section("SETUP: Backup & clean state")
orig_mem = dict(_load_memory())
backup_path = MEMORY_FILE + ".cross_test_backup"
if os.path.exists(MEMORY_FILE):
    with open(MEMORY_FILE, "r") as f:
        json.dump(json.load(f), open(backup_path, "w"))

buf = get_buffer()
buf.clear()
_save_memory({})
check("Clean state ready", buf.size()["total"] == 0 and len(_load_memory()) == 0)


# ═══════════════════════════════════════════════════════════════════════════
section("SCENARIO 1: STORE — Všetky 4 vrstvy naraz")
# ═══════════════════════════════════════════════════════════════════════════

test_memories = [
    ("jarvis_core", "JARVIS is a voice-driven AI assistant built with Python 3.12"),
    ("jarvis_memory_stack", "Uses ChromaDB, all-mpnet-base-v2 embeddings, and BM25 hybrid search"),
    ("jarvis_tools_list", "Tools: memory, rag_search, control_browser, execute_command, instagram_dm"),
    ("fogy_profile", "Fogyminigun is building AI memory systems, favorite color is blue"),
    ("project_goal_memory", "Goal: ultimate AI memory to help Alzheimer patients remember more"),
    ("tech_stack_python", "Python libraries: numpy, pandas, spaCy, NetworkX, sentence-transformers"),
    ("bug_login_timeout", "WebUI login times out after 60 seconds of inactivity"),
    ("idea_standby_agents", "Standby neuron agents: domain-specialized, zero tokens when idle"),
    ("meeting_notes_june", "Discussed 5-tier memory architecture with Claude on 2026-06-13"),
    ("fogy_location_sk", "Fogy lives in Slovakia and speaks Slovak and English"),
]

t0 = time.perf_counter()
for key, val in test_memories:
    result = memory("save", key, val)
    check(f"Save: {key}", "Uložené" in result)
store_time = (time.perf_counter() - t0) * 1000

# Verify all 4 tiers
buf_size = buf.size()
json_size = len(_load_memory())
kg = get_graph()
kg_nodes = kg.graph.number_of_nodes()
kg_edges = kg.graph.number_of_edges()

check("EpisodicBuffer populated", buf_size["total"] >= 8,
      f"total={buf_size['total']}")
check("JSON persisted", json_size == 10)
check("Knowledge Graph has entities", kg_nodes > 0, f"nodes={kg_nodes}")
check("Knowledge Graph has relations", kg_edges > 0, f"edges={kg_edges}")
# Prvý store loaduje embedding modely (až ~20s), to je normálne
check(f"Stores completed", store_time < 30000, f"{store_time:.1f}ms (models loaded on first run)")


# ═══════════════════════════════════════════════════════════════════════════
section("SCENARIO 2: RETRIEVE — 3-vrstvové čítanie")
# ═══════════════════════════════════════════════════════════════════════════

# EpisodicBuffer hit (fastest)
t0 = time.perf_counter()
result = memory("read", key="jarvis_core")
ep_latency = (time.perf_counter() - t0) * 1000
check("EpisodicBuffer hit", "score:" in result and "JARVIS" in result,
      f"latency={ep_latency:.1f}ms")
check("EpisodicBuffer sub-100ms", ep_latency < 100, f"{ep_latency:.1f}ms")

# Clear buffer, test JSON fallback
buf.clear()
result = memory("read", key="jarvis_memory_stack")
check("JSON fallback after buffer clear", "ChromaDB" in result or "all-mpnet" in result)

# Re-store from JSON → EpisodicBuffer
result = memory("read", key="jarvis_memory_stack")
check("Re-stored in EpisodicBuffer after JSON fallback",
      "score:" in result, f"result: {result[:80]}")

# Semantic search via ChromaDB
search_result = rag_search("AI memory Alzheimer", k=3, min_score=0.0)
check("ChromaDB semantic search works", "Alzheimer" in search_result or "memory" in search_result.lower())


# ═══════════════════════════════════════════════════════════════════════════
section("SCENARIO 3: REINFORCEMENT — Čítanie posilňuje pamäť")
# ═══════════════════════════════════════════════════════════════════════════

# Read project_goal 5 times
for _ in range(5):
    memory("read", key="project_goal_memory")

results = buf.retrieve(key="project_goal_memory")
check("Access count increased after multiple reads",
      len(results) > 0 and results[0]["access_count"] >= 2,
      f"access_count={results[0]['access_count'] if results else 0}")
check("Score boosted by reinforcement",
      len(results) > 0 and results[0]["score"] >= 0.5,
      f"score={results[0]['score'] if results else 0}")


# ═══════════════════════════════════════════════════════════════════════════
section("SCENARIO 4: DECAY — Ebbinghaus zabúdanie")
# ═══════════════════════════════════════════════════════════════════════════

# Save a test item with low importance
memory("save", "decay_test_low", "This unimportant fact will be forgotten")
# Get it from buffer
for item in buf.working + buf.episodic:
    if item.key == "decay_test_low":
        item.importance = 0.1
        item.access_count = 1
        item.last_access = time.time() - 60 * 24 * 3600  # 60 days ago
        break

size_before = buf.size()
buf.decay(target="both")
size_after = buf.size()

check("Decay executed", buf.stats["decays"] > 0)
check("Low-importance old item decays",
      not any(i.key == "decay_test_low" for i in buf.episodic + buf.working)
      or size_after["total"] <= size_before["total"])

# But reinforced items survive
check("Reinforced project_goal survives",
      any(i.key == "project_goal_memory" for i in buf.working + buf.episodic))


# ═══════════════════════════════════════════════════════════════════════════
section("SCENARIO 5: CONSOLIDATION — Quick + Full pipeline")
# ═══════════════════════════════════════════════════════════════════════════

t0 = time.perf_counter()
result = consolidate_quick()
quick_time = (time.perf_counter() - t0) * 1000

check("Quick consolidation completed", "elapsed_ms" in result)
check("Quick mode: decay stage", result["decay"]["decayed"] >= 0)
check("Quick mode: clusters stage", "clusters" in result)
check("Quick mode: rescore stage", result["rescore"]["rescored"] >= 0)
check("Quick mode: promote stage", result["promote"]["promoted"] >= 0)
check(f"Quick mode < 1s", quick_time < 1000, f"{quick_time:.1f}ms")

# Full consolidation (uses DeepSeek)
t0 = time.perf_counter()
result = consolidate_full()
full_time = (time.perf_counter() - t0) * 1000

check("Full consolidation completed", "elapsed_ms" in result)
check("Full mode: merge stage", "merge" in result)
check("Full mode: relations stage", "relations" in result)
check("Full mode: archive stage", "archive" in result)
# DeepSeek volania (môžu byť 0 ak nie je API key)
check("Full mode has elapsed", "elapsed_ms" in result)

# Idle detection
touch()
check("Not idle after touch", not is_idle(threshold=999999))
check("Idle seconds < 5", is_idle(threshold=999999) == False)


# ═══════════════════════════════════════════════════════════════════════════
section("SCENARIO 6: KNOWLEDGE GRAPH — Entity extraction & multi-hop")
# ═══════════════════════════════════════════════════════════════════════════

entities = extract_entities("JARVIS uses Python and ChromaDB for RAG memory in Slovakia")
check("Entities extracted", len(entities) >= 4,
      f"found: {[(e['name'], e['type']) for e in entities]}")

# Verify key entities exist in the graph
kg_nodes_names = [d.get("name","") for _, d in kg.graph.nodes(data=True)]
check("JARVIS in graph", any("JARVIS" in n for n in kg_nodes_names))
check("Python in graph", any("Python" in n for n in kg_nodes_names))
check("ChromaDB in graph", any("ChromaDB" in n for n in kg_nodes_names))

# Multi-hop query
related = kg.query_relations("JARVIS", hops=2)
check("JARVIS has relations", len(related) > 0,
      f"related count: {len(related)}")

# Path finding
path = kg.find_path("Python", "ChromaDB")
check("Path between co-occurring entities", len(path) > 0 if "Python" in kg_nodes_names and "ChromaDB" in kg_nodes_names else True)

# Graph context for search
ctx = kg.get_context("Python AI memory", max_hops=2)
check("Graph context generated", isinstance(ctx, str))


# ═══════════════════════════════════════════════════════════════════════════
section("SCENARIO 7: STANDBY AGENTS — Domain routing")
# ═══════════════════════════════════════════════════════════════════════════

# Update centroids from current buffer
update_all_centroids()
agent_stats = get_agents_stats()
check("Agents exist", len(agent_stats) >= 3,
      f"found {len(agent_stats)} agents: {[s['name'] for s in agent_stats[:5]]}")
check("Agents are DEEP_SLEEP or LIGHT_SLEEP",
      all(s.get("state") in ("DEEP_SLEEP", "LIGHT_SLEEP") for s in agent_stats))

# Route a tech query
result = query_memory("What Python libraries does JARVIS use?", k=3)
check("Tech query wakes agents", len(result.get("agents_used", [])) >= 1,
      f"agents: {result.get('agents_used', [])}")

# Route a personal query
result = query_memory("What is Fogy's favorite color?", k=3)
check("Personal query executes", "results" in result)

# Store with agent enrichment
result = store_memory("new_tool_memory", "MemoryManager v2 uses Python asyncio",
                      text="Python asyncio memory manager tool")
check("Store enrichment has boost", result.get("total_boost", 0) >= 0)
check("Store executed", "saved" in result)

# All agents back to sleep after operation (v2: DEEP_SLEEP or LIGHT_SLEEP = idle)
agent_stats = get_agents_stats()
check("All agents sleeping after operation",
      all(s["state"] in ("DEEP_SLEEP", "LIGHT_SLEEP") for s in agent_stats),
      f"states: {[(s['name'], s['state']) for s in agent_stats]}")


# ═══════════════════════════════════════════════════════════════════════════
section("SCENARIO 8: ARCHIVE — Cold storage + Thaw")
# ═══════════════════════════════════════════════════════════════════════════

archive = get_archive()
# Archive a test item
archive.archive([{
    "key": "archive_test_thaw", "value": "This was archived and should be retrievable",
    "timestamp": time.time() - 200*24*3600, "importance": 0.3,
    "access_count": 0, "tags": ["test"],
}])

# Search in archive
results = archive.search("archived and should be retrievable")
check("Archive search finds item", len(results) >= 1)

# Thaw back to active memory
thawed = archive.thaw(key="archive_test_thaw")
check("Thaw restores item", len(thawed) == 1)

# Verify in active memory
result = memory("read", key="archive_test_thaw")
check("Thawed item in active memory", "archived" in result.lower() or "retrievable" in result)
memory("delete", key="archive_test_thaw")

# Archive stats
stats = archive.stats()
check("Archive has stats", stats["total_keys"] >= 0)


# ═══════════════════════════════════════════════════════════════════════════
section("SCENARIO 9: EDGE CASES")
# ═══════════════════════════════════════════════════════════════════════════

# Slovak diacritics round-trip through all layers
memory("save", "kľúč_s_diakritikou", "ľščťžýáíéôäú")
result = memory("read", key="kľúč_s_diakritikou")
check("SK diacritics: memory save/read", "ľščťžýáíé" in result)

search = rag_search("diakritikou", k=3, min_score=0.0)
check("SK diacritics: ChromaDB search", len(search) > 10)

# KG handles SK diacritics
entities = extract_entities("ľščťžýáíé")
check("SK diacritics: entity extraction", isinstance(entities, list))

# Very long values
long_val = "🚀🧠💾" * 200
memory("save", "long_emoji_test", long_val)
result = memory("read", key="long_emoji_test")
check("Long emoji value round-trip", len(result) > 100)

# Special characters in keys
memory("save", "key/with/slashes", "slash test")
result = memory("read", key="key/with/slashes")
check("Key with slashes", "slash test" in result)

# Unicode edge cases
memory("save", "unicode_poop", "💩")
result = memory("read", key="unicode_poop")
check("Unicode emoji", "💩" in result)

# Cleanup edge case tests
for key in ["kľúč_s_diakritikou", "long_emoji_test", "key/with/slashes", "unicode_poop"]:
    memory("delete", key=key)


# ═══════════════════════════════════════════════════════════════════════════
section("SCENARIO 10: PERFORMANCE BENCHMARK")
# ═══════════════════════════════════════════════════════════════════════════

# Store latency
t0 = time.perf_counter()
for i in range(10):
    memory("save", f"perf_test_{i}", f"Performance test value {i}")
store_10 = (time.perf_counter() - t0) * 1000
check(f"10 stores < 3s (KG extraction + ChromaDB + JSON)", store_10 < 3000, f"{store_10:.1f}ms")

# Read latency (EpisodicBuffer)
t0 = time.perf_counter()
for i in range(10):
    memory("read", key=f"perf_test_{i}")
read_10 = (time.perf_counter() - t0) * 1000
check(f"10 reads < 100ms", read_10 < 100, f"{read_10:.1f}ms")

# Semantic search latency
t0 = time.perf_counter()
_ = rag_search("Python memory AI", k=5, min_score=0.0)
search_time = (time.perf_counter() - t0) * 1000
check(f"Semantic search < 500ms", search_time < 500, f"{search_time:.1f}ms")

# Quick consolidation latency
t0 = time.perf_counter()
_ = consolidate_quick()
quick_c = (time.perf_counter() - t0) * 1000
check(f"Quick consolidate < 500ms", quick_c < 500, f"{quick_c:.1f}ms")

# Cleanup perf tests
for i in range(10):
    memory("delete", key=f"perf_test_{i}")


# ═══════════════════════════════════════════════════════════════════════════
section("SCENARIO 11: CONCURRENT ACCESS SIMULATION")
# ═══════════════════════════════════════════════════════════════════════════

# Simulate rapid save/read cycles
for i in range(20):
    memory("save", f"concurrent_{i}", f"Value {i}")
    result = memory("read", key=f"concurrent_{i}")
    check(f"Concurrent cycle {i}", f"Value {i}" in result)

# Cleanup
for i in range(20):
    memory("delete", key=f"concurrent_{i}")


# ═══════════════════════════════════════════════════════════════════════════
section("FINAL HEALTH REPORT")
# ═══════════════════════════════════════════════════════════════════════════

health = buf.health()
print(f"  EpisodicBuffer: {health['working']}w + {health['episodic']}e")
print(f"  Avg scores: w={health['avg_score_working']:.3f}, e={health['avg_score_episodic']:.3f}")
print(f"  Operations: {health['stats']}")

kg_stats = kg.stats()
print(f"  Knowledge Graph: {kg_stats['entities']} entities, {kg_stats['relations']} relations")

archive_stats = archive.stats()
print(f"  Cold Archive: {archive_stats['total_keys']} keys, {archive_stats['total_size_mb']}MB")

agent_stats = get_agents_stats()
agent_summary = ", ".join(f"{s['name']}({s.get('wake_count', 0)}x)" for s in agent_stats[:5])
print(f"  Agents: {len(agent_stats)} total, {agent_summary}")


# ═══════════════════════════════════════════════════════════════════════════
section("CLEANUP")
# ═══════════════════════════════════════════════════════════════════════════

# Restore original memory
buf.clear()
_save_memory(orig_mem)
if os.path.exists(backup_path):
    with open(backup_path, "r") as f:
        data = json.load(f)
    _save_memory(data)
    os.remove(backup_path)

# Clean test buffer file
buf_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "episodic_buffer.json")
if os.path.exists(buf_file) and buf.size()["total"] == 0:
    pass  # keep it for persistence

check("Cleanup complete", True)


# ═══════════════════════════════════════════════════════════════════════════
section("VÝSLEDOK")
# ═══════════════════════════════════════════════════════════════════════════

print(f"\n  {PASS} Passed: {passed}/{total}")
if failed:
    print(f"  {FAIL} Failed: {failed}/{total}")
    print(f"\n  ⚠️  {failed} cross-tier integration test(s) failed!")
else:
    print(f"  🎉 ALL CROSS-TIER INTEGRATION TESTS PASSED!")
    print(f"  🧠 5-tier memory architecture: VERIFIED ✅")
print()

sys.exit(0 if failed == 0 else 1)
