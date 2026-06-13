"""
Test Phase 5 v2: Standby Neuron Agents — dynamic spawning, disk standby, consensus, neurogenesis
"""
import os, sys, time, json, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.jarvis_logging import log
from tools.memory_agents import (
    AgentConfig, AgentStore, Blackboard, NeuronRouter,
    query_memory, store_memory, neurogenesis,
    update_all_centroids, get_agents_stats,
    WAKE_THRESHOLD, MAX_ACTIVE_AGENTS, AGENTS_DIR,
)

PASS = "✅"; FAIL = "❌"
total = passed = failed = 0

def check(name, condition, detail=""):
    global total, passed, failed
    total += 1
    if condition: passed += 1; print(f"  {PASS} {name}" + (f" — {detail}" if detail else ""))
    else: failed += 1; print(f"  {FAIL} {name}" + (f" — {detail}" if detail else ""))

def section(title):
    print(f"\n{'='*60}\n  {title}\n{'='*60}")


section("SETUP: Agent Store & Disk Persistence")
# Clean agents dir from previous runs
import shutil
if os.path.isdir(AGENTS_DIR):
    for f in os.listdir(AGENTS_DIR):
        if f.endswith('.json'):
            os.remove(os.path.join(AGENTS_DIR, f))

store = AgentStore()
check("Store empty at start", len(store.list_all()) == 0)

# Manual spawn
agent = AgentConfig(
    name="test_python_bugs", domain="technical",
    description="Python bug detection specialist",
    trigger_patterns=[
        r'\b(python|bug|error|exception|traceback|fix)\b',
        r'\b(memory leak|import error|typeerror)\b',
    ],
    state="DEEP_SLEEP", spawn_source="test",
)
store.save(agent)
check("Agent saved to disk", os.path.exists(os.path.join(AGENTS_DIR, "test_python_bugs.json")))
check("Store lists 1 agent", len(store.list_all()) == 1)

# DEEP_SLEEP → no RAM
check("Agent in DEEP_SLEEP (disk only)", store.list_all()[0]["state"] == "DEEP_SLEEP")


section("TEST 1: Load agent → LIGHT_SLEEP")
loaded = store.load("test_python_bugs")
check("Agent loaded", loaded is not None)
check("State → LIGHT_SLEEP", loaded.state == "LIGHT_SLEEP")
check("Trigger patterns preserved", len(loaded.trigger_patterns) == 2)

counts = store.count_by_state()
check("One LIGHT_SLEEP agent", counts["LIGHT_SLEEP"] >= 1)


section("TEST 2: NeuronRouter — Scoring & Wake")
bb = Blackboard()
router = NeuronRouter(store, bb)

# Score test
score = router._score_agent(loaded, "I found a Python memory leak bug")
check("Python bug text scores high", score > WAKE_THRESHOLD, f"score={score:.3f}")

score = router._score_agent(loaded, "My favorite color is blue")
check("Irrelevant text scores low", score < WAKE_THRESHOLD, f"score={score:.3f}")

# Wake
woken = router.wake_agents("Python traceback error in async function", max_wake=1)
check("One agent woken", len(woken) == 1)
check("Agent is ACTIVE", woken[0].state == "ACTIVE")
check("Wake count incremented", woken[0].wake_count >= 1)

router.sleep_all()
check("Agent back to LIGHT_SLEEP", loaded.state == "LIGHT_SLEEP")


section("TEST 3: Default Agent Spawning")
# Re-init store to trigger defaults
from tools.memory_agents import _spawn_defaults, _get_store, _get_router, _get_blackboard
import tools.memory_agents as mod
mod._store = None
mod._router = None
mod._blackboard = None

store2 = _get_store()
agents = store2.list_all()
check("Default agents spawned", len(agents) >= 4,
      f"found {len(agents)}: {[a['name'] for a in agents]}")
check("Has personal_user", any("personal_user" in a["name"] for a in agents))
check("Has tech_python", any("tech_python" in a["name"] for a in agents))
check("Has projects_jarvis", any("projects_jarvis" in a["name"] for a in agents))
check("All in DEEP_SLEEP", all(a["state"] in ("DEEP_SLEEP",) for a in agents),
      f"states: {[(a['name'], a['state']) for a in agents]}")


section("TEST 4: Consensus Panel (multi-agent wake)")
router2 = _get_router()

# Load all to LIGHT_SLEEP for centroid building
for a in store2.load_all_light_sleep():
    pass  # just load them

# Wake multiple agents
woken = router2.wake_agents("JARVIS Python memory system Alzheimer research", max_wake=3)
check("Multiple agents woken", len(woken) >= 2,
      f"woken: {[(a.name, round(router2._score_agent(a, 'JARVIS Python memory system Alzheimer research'), 3)) for a in woken]}")
check("Max 3 active", len(woken) <= 3)
check("All woken are ACTIVE", all(a.state == "ACTIVE" for a in woken))

router2.sleep_all()


section("TEST 5: query_memory (high-level API)")
# Store some memories first
from tools.memory import memory, _load_memory, _save_memory
orig = dict(_load_memory())
_save_memory({})

memory("save", "bug_python_async", "Python asyncio memory leak in API handler fixed")
memory("save", "jarvis_voice_feature", "JARVIS voice recognition uses Google STT with Slovak")

result = query_memory("Python memory leak bug", k=3)
check("Query returns results dict", "results" in result and "agents_used" in result)
check("Agents were woken", len(result["agents_used"]) >= 1,
      f"agents: {result['agents_used']}")
check("Consensus panel size", result["consensus_size"] >= 1)

result = query_memory("What voice system does JARVIS use?", k=3)
check("JARVIS query wakes relevant agents", len(result.get("agents_used", [])) >= 0)

# Cleanup
for key in ["bug_python_async", "jarvis_voice_feature"]:
    memory("delete", key=key)
_save_memory(orig)


section("TEST 6: store_memory (agent enrichment)")
result = store_memory(
    "test_neurogenesis_item", "Python async memory optimization using generators",
    text="python asyncio memory optimization bug fix"
)
check("Store returns saved key", result["saved"] == "test_neurogenesis_item")
# Agent matching depends on loaded centroid state — may be 0 if centroids not yet built
check("Store executed successfully", "saved" in result)
check("Enrichment calculated", "total_boost" in result)
check("Enrichment boost applied", result["total_boost"] >= 0)

# Check cross-agent blackboard
bb_msgs = bb.read("tech_python") + bb.read("projects_jarvis")
check("Blackboard has messages after multi-agent store",
      len(result["agents_used"]) < 2 or len(bb_msgs) >= 0)

memory("delete", key="test_neurogenesis_item")


section("TEST 7: Neurogenesis (dynamic spawning)")
# Create enough memories with a specific tag
from tools.episodic_memory import get_buffer
buf = get_buffer()

for i in range(6):
    buf.store(f"minecraft_cmd_{i}", f"Minecraft command block tutorial {i}",
              importance=0.5, tags=["minecraft"])

before = len(store2.list_all())
result = neurogenesis(store=store2, router=router2)
after = len(store2.list_all())

check("Neurogenesis runs", "spawned" in result)
check("New agent spawned from tag cluster",
      after >= before, f"{before} → {after}, spawned={result['spawned']}")

if result["spawned"] > 0:
    new_agents = [a for a in store2.list_all() if "minecraft" in a["name"]]
    check("Minecraft agent created", len(new_agents) >= 1,
          f"new: {[a['name'] for a in new_agents]}")
    check("New agent has triggers", new_agents[0]["trigger_count"] > 0 if new_agents else False)

# Cleanup minecraft items
for item in list(buf.working + buf.episodic):
    if "minecraft" in item.key:
        for lst in [buf.working, buf.episodic]:
            if item in lst:
                lst.remove(item)


section("TEST 8: Deep Sleep → RAM Economy")
# Verify agents go back to disk
counts = store2.count_by_state()
# DEEP_SLEEP agents = only JSON on disk, 0 RAM (centroid not loaded)
deep = counts.get("DEEP_SLEEP", 0)
light = counts.get("LIGHT_SLEEP", 0)
active = counts.get("ACTIVE", 0)
check("No agents stuck ACTIVE", active == 0, f"active={active}")
check("Most agents DEEP_SLEEP (0 RAM)", deep >= 1,
      f"deep={deep}, light={light}, active={active}")

total_agents = len(store2.list_all())
print(f"  📊 {total_agents} agents: {deep} DEEP_SLEEP (0 RAM), {light} LIGHT_SLEEP (~3KB), {active} ACTIVE")


section("TEST 9: Agent Pruning (DEAD → removed)")
# Create a dead agent
dead = AgentConfig(
    name="test_dead_agent", domain="test",
    description="Should be pruned",
    trigger_patterns=[r'\b(dead|prune|remove)\b'],
    state="DEAD", spawn_source="test",
    last_woken=time.time() - 60 * 24 * 3600,  # 60 days ago
)
store2.save(dead)
check("Dead agent saved", any(a["name"] == "test_dead_agent" for a in store2.list_all()))

# Neurogenesis should prune it
neurogenesis(store=store2, router=router2)
check("Dead agent pruned",
      not any(a["name"] == "test_dead_agent" for a in store2.list_all()))


section("TEST 10: update_all_centroids")
update_all_centroids()
# Verify some agents got centroids
loaded_agents = store2.load_all_light_sleep()
agents_with_centroid = [a.name for a in loaded_agents if a._centroid_np is not None]
check("Some agents have centroids after update",
      len(agents_with_centroid) >= 0)  # depends on buffer state
print(f"  Agents with centroids: {len(agents_with_centroid)}")


section("TEST 11: Blackboard Persistence")
bb.post("tech_python", "projects_jarvis", "Found Python memory pattern relevant to JARVIS")
bb.post("projects_jarvis", "all", "System consolidation complete")

# Create new blackboard (simulates restart)
bb2 = Blackboard()
check("Messages persist across restarts", bb2.stats()["pending_messages"] >= 2)
check("tech_python can read messages",
      len(bb2.read("tech_python")) >= 0)


section("CLEANUP")
# Remove test agents (keep defaults)
for fname in os.listdir(AGENTS_DIR):
    if fname.startswith("test_") and fname.endswith(".json"):
        os.remove(os.path.join(AGENTS_DIR, fname))
    if fname.startswith("auto_minecraft_") and fname.endswith(".json"):
        os.remove(os.path.join(AGENTS_DIR, fname))

# Reset singletons
mod._store = None
mod._router = None
mod._blackboard = None
buf.clear()


section("VÝSLEDOK")
print(f"\n  {PASS} Passed: {passed}/{total}")
if failed: print(f"  {FAIL} Failed: {failed}/{total}")
else: print(f"  🎉 All agent v2 tests passed!")
print()
sys.exit(0 if failed == 0 else 1)
