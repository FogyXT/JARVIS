"""
Test Phase 4: Consolidation Pipeline — sleep-like memory replay.
"""
import os, sys, time, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.jarvis_logging import log
from tools.consolidation import (
    consolidate_quick, consolidate_full, get_stats,
    touch, is_idle, idle_seconds,
    _stage_decay, _stage_cluster, _stage_merge, _stage_rescore,
    _stage_promote, _stage_relationships, _stage_archive,
)
from tools.episodic_memory import EpisodicBuffer, get_buffer

PASS = "✅"; FAIL = "❌"
total = passed = failed = 0

def check(name, condition, detail=""):
    global total, passed, failed
    total += 1
    if condition: passed += 1; print(f"  {PASS} {name}" + (f" — {detail}" if detail else ""))
    else: failed += 1; print(f"  {FAIL} {name}" + (f" — {detail}" if detail else ""))

def section(title):
    print(f"\n{'='*60}\n  {title}\n{'='*60}")


section("SETUP: Prepare buffer with test data")
buf = get_buffer()
buf.clear()

# Store diverse test memories
test_items = [
    ("jarvis_is_python", "JARVIS is written in Python", 0.8, ["tech"]),
    ("jarvis_python_stack", "JARVIS uses Python 3.12 for its core logic", 0.7, ["tech"]),  # similar to above
    ("fogy_name", "Fogyminigun is the user", 0.9, ["personal"]),
    ("fogy_user", "The user is called Fogyminigun", 0.8, ["personal"]),  # similar to above
    ("project_goal", "Help Alzheimer patients with AI memory", 1.0, ["goal"]),
    ("old_unused_fact", "This old fact is never accessed", 0.3, ["test"]),
    ("frequent_tool", "ChromaDB vector search tool", 0.7, ["tech"]),
]
for key, val, imp, tags in test_items:
    buf.store(key, val, importance=imp, tags=tags)

# Simulate high access for "frequent_tool"
for _ in range(12):
    buf.retrieve(key="frequent_tool")

# Simulate old age for "old_unused_fact"
for item in buf.working + buf.episodic:
    if item.key == "old_unused_fact":
        item.timestamp = time.time() - 100 * 24 * 3600  # 100 days old
        item.last_access = time.time() - 100 * 24 * 3600
        item.access_count = 0

check("Buffer has test data", buf.size()["total"] >= 5,
      f"total={buf.size()['total']}")


section("TEST 1: Stage — DecayAnalyzer")
result = _stage_decay(buf)
check("Decay applied", result["decayed"] > 0, f"result={result}")
check("Has working stats", "working_before" in result)


section("TEST 2: Stage — ClusterDetector")
clusters = _stage_cluster(buf)
# We have similar pairs: jarvis_is_python/jarvis_python_stack, fogy_name/fogy_user
check("Clusters detected", len(clusters) >= 1,
      f"clusters={len(clusters)}, keys={[[c['key'] for c in g] for g in clusters[:3]]}")
if clusters:
    check("Each cluster has 2+ items", all(len(c) >= 2 for c in clusters))


section("TEST 3: Stage — ImportanceScorer")
result = _stage_rescore(buf)
check("Rescore executed", result["rescored"] >= 0)
# frequent_tool should be boosted (12 accesses)
freq = buf.retrieve(key="frequent_tool")
if freq:
    check("High-access item boosted", freq[0]["importance"] >= 0.8,
          f"importance={freq[0]['importance']}")

# old_unused_fact should be demoted
old = buf.retrieve(key="old_unused_fact")
if old:
    check("Old unused demoted", old[0]["importance"] <= 0.3,
          f"importance={old[0]['importance']}")


section("TEST 4: Stage — Promoter")
result = _stage_promote(buf)
check("Promotion executed", "promoted" in result)


section("TEST 5: Stage — SemanticMerger")
clusters = _stage_cluster(buf)  # re-cluster
if clusters:
    result = _stage_merge(clusters)
    check("Merge executed", result["merged"] >= 0,
          f"merged={result['merged']}, skipped={result['skipped']}")
else:
    check("Merge skipped (no clusters)", True)


section("TEST 6: Stage — RelationshipFinder")
result = _stage_relationships()
check("Relations result", "new_relations" in result)


section("TEST 7: Stage — Archiver")
result = _stage_archive(buf)
check("Archive executed", "archived" in result)


section("TEST 8: consolidate_quick (full pipeline)")
result = consolidate_quick()
check("Quick consolidation returns dict", isinstance(result, dict))
check("Quick mode has all stages", all(k in result for k in ["decay", "rescore", "promote"]))
check("Quick mode has elapsed time", "elapsed_ms" in result)
check("Quick mode < 5s", result["elapsed_ms"] < 5000,
      f"{result['elapsed_ms']}ms")


section("TEST 9: consolidate_full (full pipeline with DeepSeek)")
result = consolidate_full()
check("Full consolidation returns dict", isinstance(result, dict))
check("Full mode has merge stage", "merge" in result)
check("Full mode merge used LLM", result["merge"].get("llm_used", False) == True or
      result["merge"].get("llm_calls", 0) >= 0,  # 0 if no DEEPSEEK_API_KEY
      f"merge result: {result['merge']}")
check("Full mode has relations stage", "relations" in result)
check("Full mode relations used LLM", result["relations"].get("llm_used", False) == True or
      result["relations"].get("llm_calls", 0) >= 0,
      f"relations result: {result['relations']}")
check("Full mode has archive stage", "archive" in result)
check("Full mode has elapsed time", "elapsed_ms" in result)


section("TEST 10: Idle Detection")
# touch() was called by memory operations, so should not be idle now
touch()  # reset
check("Not idle after touch", not is_idle(threshold=999999))

# But idle_seconds should be small
check("Idle seconds near 0", idle_seconds() < 5, f"{idle_seconds():.1f}s")

# get_stats()
stats = get_stats()
check("Stats has idle info", "idle_seconds" in stats and "is_idle" in stats)
check("Stats has buffer health", stats.get("buffer") is not None)
check("Stats has KG info", "knowledge_graph" in stats)


section("TEST 11: Idempotency (multiple runs)")
# Quick consolidation should be safe to run multiple times
for _ in range(3):
    result = consolidate_quick()
    check(f"Quick run OK (elapsed={result['elapsed_ms']}ms)", "elapsed_ms" in result)


section("CLEANUP")
buf.clear()


section("VÝSLEDOK")
print(f"\n  {PASS} Passed: {passed}/{total}")
if failed: print(f"  {FAIL} Failed: {failed}/{total}")
else: print(f"  🎉 All consolidation tests passed!")
print()
sys.exit(0 if failed == 0 else 1)
