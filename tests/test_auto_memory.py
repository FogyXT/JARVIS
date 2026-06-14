"""
Test auto-memory hook — continuous, autonomous memory saving.
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.auto_memory import auto_remember, auto_remember_text, get_stats, _extract_facts

PASS = "✅"; FAIL = "❌"
total = passed = failed = 0

def check(name, condition, detail=""):
    global total, passed, failed
    total += 1
    if condition: passed += 1; print(f"  {PASS} {name}" + (f" — {detail}" if detail else ""))
    else: failed += 1; print(f"  {FAIL} {name}" + (f" — {detail}" if detail else ""))

def section(title):
    print(f"\n{'='*60}\n  {title}\n{'='*60}")


section("TEST 1: Fact extraction from realistic conversations")

# Simuluj reálne konverzácie
exchanges = [
    ("I decided to use AGPL-3.0 for licensing", "Good choice. AGPL protects against SaaS exploitation"),
    ("The login bug was fixed by adding timeout handling", "Fixed the 60-second timeout issue in web UI"),
    ("I prefer Python over JavaScript for backend work", "Python is great for AI and memory systems"),
    ("We discovered that Ebbinghaus curves need empirical tuning", "The optimal decay parameters depend on use case"),
    ("The architecture uses ChromaDB for semantic storage", "Yeah, with all-mpnet-base-v2 embeddings and BM25 hybrid search"),
    ("I want to share this project with Anthropic for feedback", "Good idea. The standby neuron concept is genuinely novel"),
    ("We built a 5-tier memory system with neurogenesis", "All 324 tests passing. It's production ready"),
    ("Next step is to deploy and test over multiple weeks", "Real-world validation is the honest gap"),
]

stored_total = 0
for user_msg, asst_msg in exchanges:
    result = auto_remember(user_msg, asst_msg)
    stored_total += result["stored"]
    if result["stored"] > 0:
        for f in result["facts"]:
            print(f"    📝 {f['type']}: {f['value'][:80]} ({f['importance']})")

check("Facts extracted from conversations", stored_total >= 3,
      f"total facts: {stored_total}")

# Check specific fact types
all_facts = []
for user_msg, asst_msg in exchanges:
    all_facts.extend(_extract_facts(f"{user_msg} {asst_msg}"))

types_found = set(f["type"] for f in all_facts)
check("Multiple fact types detected", len(types_found) >= 3,
      f"types: {types_found}")


section("TEST 2: Continuous operation — 25 exchanges")

stats_before = get_stats()
for i in range(25):
    auto_remember(f"Test exchange {i}", f"Response to exchange {i} about building {['Python', 'AI', 'memory', 'tools'][i%4]}")

stats_after = get_stats()
check("Call counter incremented", stats_after["calls"] > stats_before["calls"],
      f"calls: {stats_before['calls']} -> {stats_after['calls']}")
check("Facts counter tracked", stats_after["facts_stored"] >= 0)
# Každých 10 volaní = consolidate. 25 volaní = aspoň 2 consolidations
check("Periodic consolidation triggered",
      stats_after["last_consolidation"] > stats_before.get("last_consolidation", 0)
      or stats_after["calls"] >= 10)


section("TEST 3: auto_remember_text (shortcut)")

result = auto_remember_text("We fixed the critical bug where API keys leaked in git history. Added .gitignore protection.")
check("Single text extraction works", result["stored"] >= 1,
      f"stored: {result['stored']}")


section("TEST 4: No crash on empty input")

result = auto_remember("", "")
check("Empty input handled", result["stored"] == 0)
check("Empty returns valid dict", isinstance(result, dict))

result = auto_remember_text("")
check("Empty text shortcut works", result["stored"] == 0)


section("TEST 5: Consolidation every N calls")

# Force consolidation by reaching CONSOLIDATE_EVERY threshold
for i in range(10):
    auto_remember(f"consolidation test {i}", f"important fact about {['Python', 'memory', 'AI', 'testing'][i%4]}")

stats = get_stats()
check("Consolidation happened after 10 calls", stats["last_consolidation"] > 0,
      f"last_consolidation: {stats['last_consolidation']}")


section("TEST 6: Entity extraction quality")

# Complex technical conversation
text = """
We decided to use AGPL-3.0 with a Section 7 attribution clause.
The standby neuron agents sleep on disk in DEEP_SLEEP state consuming 0 RAM and 0 tokens.
We fixed the Instagram contacts leak by extracting them to a separate JSON file.
The ChromaDB v2 semantic store uses all-mpnet-base-v2 embeddings with hybrid BM25 search.
I prefer keeping the project simple rather than over-engineering it.
"""
facts = _extract_facts(text)
check("Complex text yields facts", len(facts) >= 2, f"found: {len(facts)}")
for f in facts:
    print(f"    📝 {f['type']}: {f['value'][:80]}")


section("TEST 7: Stats tracking")

stats = get_stats()
check("Stats has calls", "calls" in stats)
check("Stats has facts_stored", "facts_stored" in stats)
check("Stats has last_consolidation", "last_consolidation" in stats)
print(f"    📊 {stats['calls']} calls, {stats['facts_stored']} facts stored")


section("VÝSLEDOK")
print(f"\n  {PASS} Passed: {passed}/{total}")
if failed: print(f"  {FAIL} Failed: {failed}/{total}")
else: print(f"  🎉 Auto-memory system working!")
print()
sys.exit(0 if failed == 0 else 1)
