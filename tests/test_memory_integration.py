"""
End-to-end test: tools/memory.py s EpisodicBuffer integráciou.

Testuje reálny flow JARVIS memory systému:
- memory("save") → 3 vrstvy naraz
- memory("read") → EpisodicBuffer first, fallbacky
- EpisodicBuffer decay + reinforcement
- memory("delete") → vyčistenie všetkých vrstiev
- Persistencia medzi reštartami
"""

import os
import sys
import time
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.jarvis_logging import log
from tools.memory import memory, _load_memory, _save_memory, MEMORY_FILE
from tools.episodic_memory import get_buffer, EpisodicBuffer

PASS = "✅"
FAIL = "❌"
total = passed = failed = 0

def check(name, condition, detail=""):
    global total, passed, failed
    total += 1
    if condition:
        passed += 1
        print(f"  {PASS} {name}" + (f" — {detail}" if detail else ""))
    else:
        failed += 1
        print(f"  {FAIL} {name}" + (f" — {detail}" if detail else ""))

def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ── Setup: Backup existing memory ─────────────────────────────────────

section("SETUP")

original_mem = _load_memory()
backup_path = MEMORY_FILE + ".test_backup"
if os.path.exists(MEMORY_FILE):
    with open(MEMORY_FILE, "r") as f:
        backup_data = f.read()
    with open(backup_path, "w") as f:
        f.write(backup_data)
    check("Memory backup created", os.path.exists(backup_path))

# Clear test memory
buf = get_buffer()
buf.clear()
_save_memory({})
check("Test memory cleared", len(_load_memory()) == 0 and buf.size()["total"] == 0)


# ── Test 1: Save → Read cycle ───────────────────────────────────────

section("TEST 1: Save & Read (basic)")

result = memory("save", "test_jarvis_version", "JARVIS 2.0 s 5-tier memory")
check("Save returns confirmation", "Uložené" in result)
check("JSON persisted", _load_memory().get("test_jarvis_version") == "JARVIS 2.0 s 5-tier memory")
check("EpisodicBuffer has item", buf.size()["total"] >= 1, f"size={buf.size()}")

result = memory("read", key="test_jarvis_version")
check("Read finds item in EpisodicBuffer", "JARVIS 2.0" in result and "score:" in result,
      f"result: {result[:80]}")

# Save more items
test_data = [
    ("jarvis_model", "claude-sonnet-4-6", "tech"),
    ("jarvis_stt", "Google Speech Recognition", "tech"),
    ("jarvis_tts", "Microsoft Edge TTS", "tech"),
    ("fogy_favorite_ide", "VS Code", "personal"),
    ("project_goal", "Build ultimate AI memory, help Alzheimer's patients", "goal"),
]
for key, val, tag in test_data:
    memory("save", key, val)

check("5 more items saved", buf.stats["stores"] >= 6)


# ── Test 2: 3-vrstvové čítanie ──────────────────────────────────────

section("TEST 2: 3-Layer Read (EpisodicBuffer → ChromaDB → JSON)")

# EpisodicBuffer hit (fastest)
result = memory("read", key="jarvis_model")
check("EpisodicBuffer hit", "score:" in result and "source:" in result)

# Ak EpisodicBuffer nemá položku (vyčistíme buffer), mal by fallbacknúť na JSON
buf.clear()
result = memory("read", key="jarvis_stt")
check("JSON fallback after buffer cleared", "Google Speech Recognition" in result,
      f"result: {result[:80]}")

# Re-store to refill buffer
memory("save", "jarvis_stt", "Google Speech Recognition v2")
result = memory("read", key="jarvis_stt")
check("EpisodicBuffer hit after re-store", "source:" in result)


# ── Test 3: Reinforcement ──────────────────────────────────────────

section("TEST 3: Access-based Reinforcement")

# Čítaj "project_goal" 5-krát
for _ in range(5):
    memory("read", key="project_goal")

results = buf.retrieve(key="project_goal")
check("project_goal reinforced", len(results) == 1 and results[0]["access_count"] >= 2,
      f"access_count={results[0]['access_count'] if results else 0}, score={results[0]['score'] if results else 0}")


# ── Test 4: Decay ──────────────────────────────────────────────────

section("TEST 4: Decay (simulované starnutie)")

# Simuluj 60 dní bez prístupu
sixty_days = 60 * 24 * 3600
for item in buf.working + buf.episodic:
    if item.key not in ("project_goal",):  # project_goal bol práve posilnený
        item.last_access -= sixty_days

size_before = buf.size()
buf.decay(target="both")
size_after = buf.size()

check("Decay applied", buf.stats["decays"] > 0)
check("Old items forgotten", size_after["total"] < size_before["total"] or
      any(i.current_score < 0.1 for i in buf.episodic + buf.working),
      f"episodic before={size_before['episodic']}, after={size_after['episodic']}")
check("Reinforced item survived", any(i.key == "project_goal" for i in buf.working + buf.episodic))


# ── Test 5: Delete ──────────────────────────────────────────────────

section("TEST 5: Delete (all layers)")

memory("save", "temp_to_delete", "Temporary data")
check("Item saved for deletion", "temp_to_delete" in _load_memory())

result = memory("delete", key="temp_to_delete")
check("Delete confirmed", "Vymazané" in result)
check("Removed from JSON", "temp_to_delete" not in _load_memory())
check("Removed from EpisodicBuffer",
      not any(i.key == "temp_to_delete" for i in buf.working + buf.episodic))


# ── Test 6: Full memory dump ───────────────────────────────────────

section("TEST 6: Full Memory Dump")

result = memory("read")
check("Full dump contains JSON data", "jarvis_model" in result or "Claude" in result)
check("Full dump contains EpisodicBuffer stats", "Episodic Buffer" in result)
check("Full dump shows scores and sizes", "avg score" in result.lower() or "stores" in result.lower())


# ── Test 7: Edge Cases ─────────────────────────────────────────────

section("TEST 7: Edge Cases")

result = memory("save", "", "")
check("Rejects empty key", "Chyba" in result)

result = memory("save", "empty_value", "")
check("Accepts empty value", "Uložené" in result and _load_memory()["empty_value"] == "")

result = memory("read", key="__nonexistent_key_xyz_123__")
check("Returns (neuložené) for missing key", "(neuložené)" in result)

result = memory("delete", key="__nonexistent_key_xyz_123__")
check("Delete non-existent returns error", "nie je" in result or "Neznáma" in result)

# Slovak characters
memory("save", "kľúč_s_diakritikou", "ľščťžýáíé")
result = memory("read", key="kľúč_s_diakritikou")
check("Slovak diacritics round-trip", "ľščťžýáíé" in result)
memory("delete", key="kľúč_s_diakritikou")

# Very long value
long_val = "🚀" * 500
memory("save", "long_test", long_val)
result = memory("read", key="long_test")
check("Long value round-trip", len(result) > 500)


# ── Test 8: Raw Buffer API ─────────────────────────────────────────

section("TEST 8: Direct EpisodicBuffer API")

buf2 = EpisodicBuffer(working_capacity=4, episodic_capacity=8)
buf2.store("direct_key", "Direct buffer access", importance=0.9, tags=["test"])
results = buf2.retrieve(query="direct access", k=1)
check("Direct buffer query works", len(results) == 1)
check("Returns metadata", "score" in results[0] and "source" in results[0])

health = buf2.health()
check("Health check has size", "working" in health and "stats" in health)


# ── Cleanup ────────────────────────────────────────────────────────

section("CLEANUP")

# Restore original memory
if os.path.exists(backup_path):
    with open(backup_path, "r") as f:
        original_data = f.read()
    with open(MEMORY_FILE, "w") as f:
        f.write(original_data)
    os.remove(backup_path)
    check("Original memory restored", True)
else:
    check("No backup to restore (already clean)", True)

# Clear test buffers
buf.clear()
check("Test buffers cleared", buf.size()["total"] == 0)


# ── Summary ────────────────────────────────────────────────────────

section("VÝSLEDOK")
print(f"\n  {PASS} Passed: {passed}/{total}")
if failed:
    print(f"  {FAIL} Failed: {failed}/{total}")
else:
    print(f"  🎉 All integration tests passed!")
print()

sys.exit(0 if failed == 0 else 1)
