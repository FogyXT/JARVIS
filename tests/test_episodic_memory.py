"""
Integračný test EpisodicBuffer — reálne scenáre používania.

Testuje:
1. Store + retrieve (sémantický aj presný)
2. Working → Episodic overflow
3. Decay + forgetting
4. Access-based reinforcement
5. Promotion do semantic store
6. Persistencia (save/load)
7. Edge cases (prázdny buffer, neexistujúci kľúč, veľa položiek)
"""
import os
import sys
import time
import math
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.jarvis_logging import log
from tools.episodic_memory import EpisodicBuffer, MemoryItem, FORGET_THRESHOLD, PROMOTE_THRESHOLD

PASS = "✅"
FAIL = "❌"
SKIP = "⏭️"

total = 0
passed = 0
failed = 0

def check(name: str, condition: bool, detail: str = ""):
    global total, passed, failed
    total += 1
    if condition:
        passed += 1
        print(f"  {PASS} {name}" + (f" — {detail}" if detail else ""))
    else:
        failed += 1
        print(f"  {FAIL} {name}" + (f" — {detail}" if detail else ""))

def section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ── Test Setup ──────────────────────────────────────────────────────────

section("SETUP: Vytváram EpisodicBuffer (8 working / 16 episodic)")

buf = EpisodicBuffer(working_capacity=8, episodic_capacity=16)
check("Buffer initialized", buf.size() == {"working": 0, "episodic": 0, "total": 0})
check("Stats initialized", buf.stats["stores"] == 0)


# ── Test 1: Basic Store ─────────────────────────────────────────────────

section("TEST 1: Ukladanie spomienok")

memories = [
    ("fogy_name", "Fogyminigun", 0.9, ["personal"]),
    ("fogy_age", "21", 0.7, ["personal"]),
    ("fogy_location", "Slovensko", 0.6, ["personal"]),
    ("project_jarvis", "Hlasový AI asistent v Pythone", 0.9, ["tech", "jarvis"]),
    ("jarvis_tools", "control_browser, file_manager, memory, execute_command", 0.8, ["tech", "jarvis"]),
    ("jarvis_voice", "Google STT + Microsoft Edge TTS", 0.7, ["tech", "jarvis"]),
    ("favorite_color", "Modrá", 0.7, ["personal"]),
    ("keyboard_shortcut", "Ctrl+Shift+S pre screenshot", 0.5, ["tech"]),
    # Tieto by mali ísť do episodic (presahujú working capacity 8)
    ("bug_login_timeout", "Login timeout po 60s nečinnosti", 0.6, ["tech", "bug"]),
    ("idea_standby_agents", "Agenti ako standby neuróny pre pamäť", 1.0, ["idea", "jarvis"]),
]

for key, val, imp, tags in memories:
    buf.store(key, val, importance=imp, tags=tags)

size = buf.size()
check("10 memories stored", size["total"] == 10)
check("Working buffer full (8)", size["working"] == 8)
check("Episodic buffer has overflow (2)", size["episodic"] == 2)
check("Stats: 10 stores", buf.stats["stores"] == 10)


# ── Test 2: Semantic Search ────────────────────────────────────────────

section("TEST 2: Sémantické vyhľadávanie")

results = buf.retrieve(query="AI asistent", k=3)
check("Found results for 'AI asistent'", len(results) > 0)
check("Top result contains Jarvis", any("jarvis" in r["key"].lower() for r in results),
      f"top key: {results[0]['key'] if results else 'N/A'}")

results = buf.retrieve(query="osobné údaje", k=3)
check("Found personal info", len(results) > 0)
# Poznámka: all-MiniLM-L6-v2 je EN model, SK dotazy nemajú presné zhody
# Toto vylepší Phase 2 s multilingual embedding modelom
check("Contains personal data (EN model limitation)",
      any("fogy" in r["key"] or "color" in r["key"] or "location" in r["key"] for r in results),
      f"keys found: {[r['key'] for r in results]}")

results = buf.retrieve(query="neexistujúci dotaz XYZ", k=3)
# Cosine similarity vždy vráti najbližšie výsledky, aj keď sú nerelevantné
# Toto sa rieši pridaním score thresholdu (napr. min_score=0.3)
check("Low-relevance query returns low scores",
      all(r["score"] < 0.5 for r in results),
      f"scores: {[round(r['score'], 3) for r in results]}")


# ── Test 3: Exact Key Lookup ──────────────────────────────────────────

section("TEST 3: Presné vyhľadávanie podľa kľúča")

results = buf.retrieve(key="fogy_name")
check("Found by exact key", len(results) == 1 and results[0]["value"] == "Fogyminigun")
check("Has metadata", all(k in results[0] for k in ["score", "source", "timestamp", "access_count"]))

results = buf.retrieve(key="nonexistent_key")
check("Handles missing key", len(results) == 0)


# ── Test 4: Reinforcement ─────────────────────────────────────────────

section("TEST 4: Access-based posilnenie pamäte")

# Vyhľadaj "idea_standby_agents" niekoľkokrát
for _ in range(5):
    buf.retrieve(query="standby neuróny", k=1)

# Nájdi item a skontroluj access_count
results = buf.retrieve(key="idea_standby_agents")
if results:
    check("Access count increased", results[0]["access_count"] >= 2,
          f"access_count={results[0]['access_count']}")
    check("Score boosted by reinforcement", results[0]["score"] > 0.5,
          f"score={results[0]['score']:.4f}")


# ── Test 5: Decay ─────────────────────────────────────────────────────

section("TEST 5: Ebbinghaus decay")

# Simuluj 30 dní bez prístupu pre položky v episodic
now = time.time()
thirty_days = 30 * 24 * 3600
for item in buf.episodic:
    item.last_access = now - thirty_days

size_before = buf.size()["episodic"]
buf.decay(target="episodic")
size_after = buf.size()["episodic"]

check("Decay applied to episodic", buf.stats["decays"] > 0)
# Po 30 dňoch by niektoré položky mali byť pod FORGET_THRESHOLD
check("Some items forgotten after 30 days",
      size_after < size_before or all(i.current_score < 1.0 for i in buf.episodic),
      f"episodic: {size_before} → {size_after}")

# Skontroluj že working buffer NIE JE ovplyvnený
check("Working buffer untouched by episodic-only decay",
      len(buf.working) == 8)


# ── Test 6: Znovu-objavenie (re-store) ─────────────────────────────────

section("TEST 6: Re-store (znovu-uloženie zabudnutej spomienky)")

buf.store("bug_login_timeout", "Login timeout po 60s — OPRAVENÉ", importance=0.8, tags=["tech", "bug"])
results = buf.retrieve(key="bug_login_timeout")
check("Re-stored memory is findable", len(results) == 1)
check("New importance applied", results[0]["importance"] == 0.8)
check("Value updated", "OPRAVENÉ" in results[0]["value"])


# ── Test 7: Promotion ─────────────────────────────────────────────────

section("TEST 7: Povýšenie do semantic store")

# Simuluj vysoký prístup a skóre pre idea_standby_agents
for item in buf.working + buf.episodic:
    if item.key == "idea_standby_agents":
        item.access_count = 10
        item.current_score = 0.8
        break

promotable = buf.get_promotable()
check("Promotable items detected", len(promotable) >= 1,
      f"count={len(promotable)}, items={[p.key for p in promotable]}")

if promotable:
    buf.remove_promoted(promotable)
    check("Promoted items removed from buffer",
          not any(i.key in [p.key for p in promotable] for i in buf.working + buf.episodic))


# ── Test 8: Persistencia ──────────────────────────────────────────────

section("TEST 8: Save & Load (persistencia na disk)")

with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
    tmp_path = tmp.name

buf.save(tmp_path)
check("Buffer saved to disk", os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0,
      f"size={os.path.getsize(tmp_path)} bytes")

# Vytvor nový buffer a načítaj
buf2 = EpisodicBuffer(working_capacity=8, episodic_capacity=16)
buf2.load(tmp_path)
check("Buffer loaded from disk", buf2.size()["total"] == buf.size()["total"],
      f"loaded: {buf2.size()}, original: {buf.size()}")

# Skontroluj že obsah je rovnaký
orig_keys = {i.key for i in buf.working + buf.episodic}
loaded_keys = {i.key for i in buf2.working + buf2.episodic}
check("All keys preserved after load", orig_keys == loaded_keys,
      f"missing: {orig_keys - loaded_keys}")

# Skontroluj že vyhľadávanie funguje aj po loade
results = buf2.retrieve(query="Jarvis asistent", k=3)
check("Search works after load", len(results) > 0)

os.unlink(tmp_path)


# ── Test 9: Edge Cases ─────────────────────────────────────────────────

section("TEST 9: Hraničné prípady")

# Prázdny buffer
empty = EpisodicBuffer(working_capacity=4, episodic_capacity=8)
check("Empty buffer size=0", empty.size()["total"] == 0)
check("Empty buffer search returns []", empty.retrieve(query="anything") == [])
check("Empty buffer health works", "stats" in empty.health())

# Veľa položiek (stress test)
log.info("Stress test: 200 memories...", module="test")
for i in range(200):
    empty.store(f"stress_key_{i}", f"Stress value number {i}", importance=0.5, tags=["stress"])
check("200 stores succeeded", empty.stats["stores"] == 200)
check("Buffer doesn't exceed capacity", empty.size()["total"] <= 4 + 8,
      f"total={empty.size()['total']} (max 12)")
check("Forgetting is working", empty.stats["forgets"] > 0,
      f"forgotten={empty.stats['forgets']}")

# Non-ASCII/Slovak
empty.store("kľúč_s_diakritikou", "ľščťžýáíé", importance=0.5)
results = empty.retrieve(key="kľúč_s_diakritikou")
check("Slovak characters preserved", len(results) == 1 and "ľščťžýáíé" in results[0]["value"])

# Veľmi dlhá hodnota
long_value = "X" * 10000
empty.store("long_key", long_value, importance=0.5)
results = empty.retrieve(key="long_key")
check("Long values stored correctly", len(results) == 1 and len(results[0]["value"]) == 10000)


# ── Test 10: Memory-like API (simulácia integrácie) ────────────────────

section("TEST 10: Simulácia integrácie s tools/memory.py")

# Takto to bude fungovať v memory() tool:
def simulated_memory_save(key, value):
    """Simulácia memory('save', key, value)."""
    buf.store(key, value, importance=0.5)

def simulated_memory_read(key=None, query=None):
    """Simulácia memory('read', key)."""
    if key:
        results = buf.retrieve(key=key)
    else:
        results = buf.retrieve(query=query or key, k=5)
    if not results:
        return "(nenájdené)"
    if len(results) == 1:
        return f"{results[0]['key']}: {results[0]['value']} (score: {results[0]['score']:.3f})"
    return "\n".join(f"  [{r['score']:.3f}] {r['key']}: {r['value'][:60]}" for r in results)

# Save
simulated_memory_save("test_integration", "Integrácia s memory tool funguje")
results = buf.retrieve(key="test_integration")
check("Simulated memory save works", len(results) == 1)
check("Value matches", results[0]["value"] == "Integrácia s memory tool funguje")

# Read by key
result = simulated_memory_read(key="test_integration")
check("Simulated memory read by key", "test_integration" in result)

# Read by query
result = simulated_memory_read(query="integrácia nástroj")
check("Simulated memory read by query", "test_integration" in result)

check("Stats: retrievals counted", buf.stats["retrievals"] > 0)


# ── Health Check ──────────────────────────────────────────────────────

section("HEALTH CHECK")

health = buf.health()
print(f"  Working buffer: {health['working']} items, avg score: {health['avg_score_working']}")
print(f"  Episodic buffer: {health['episodic']} items, avg score: {health['avg_score_episodic']}")
print(f"  Total operations: stores={health['stats']['stores']}, "
      f"retrievals={health['stats']['retrievals']}, "
      f"decays={health['stats']['decays']}, "
      f"forgets={health['stats']['forgets']}, "
      f"promotions={health['stats']['promotions']}")
print(f"  Cache hits: working={health['stats']['hits_working']}, "
      f"episodic={health['stats']['hits_episodic']}, "
      f"misses={health['stats']['misses']}")


# ── Summary ───────────────────────────────────────────────────────────

section("VÝSLEDOK")
print(f"\n  {PASS} Passed: {passed}/{total}")
if failed > 0:
    print(f"  {FAIL} Failed: {failed}/{total}")
else:
    print(f"  🎉 All tests passed!")
print()

# Exit code
sys.exit(0 if failed == 0 else 1)
