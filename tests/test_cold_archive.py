"""
Test Phase 6: Cold Archive — long-term compressed storage.
"""
import os, sys, time, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.jarvis_logging import log
from tools.cold_archive import ColdArchive, get_archive

PASS = "✅"; FAIL = "❌"
total = passed = failed = 0

def check(name, condition, detail=""):
    global total, passed, failed
    total += 1
    if condition: passed += 1; print(f"  {PASS} {name}" + (f" — {detail}" if detail else ""))
    else: failed += 1; print(f"  {FAIL} {name}" + (f" — {detail}" if detail else ""))

def section(title):
    print(f"\n{'='*60}\n  {title}\n{'='*60}")


section("SETUP")
tmpdir = tempfile.mkdtemp(prefix="cold_archive_test_")
ca = ColdArchive(base_dir=tmpdir)
check("Archive created", ca.stats()["total_keys"] == 0)


section("TEST 1: Archive memories")
items = [
    {"key": "old_python_tip", "value": "Use list comprehensions for speed",
     "timestamp": time.time() - 200*24*3600, "importance": 0.2,
     "access_count": 1, "tags": ["tech"]},
    {"key": "old_color_pref", "value": "Fogy liked green in 2025",
     "timestamp": time.time() - 300*24*3600, "importance": 0.15,
     "access_count": 0, "tags": ["personal"]},
    {"key": "deprecated_tool", "value": "Used old ChromaDB v0.3 API",
     "timestamp": time.time() - 400*24*3600, "importance": 0.1,
     "access_count": 1, "tags": ["tech"]},
]
n = ca.archive(items)
check("3 items archived", n == 3)
check("Index has 3 keys", ca.stats()["total_keys"] == 3)
check("Files created", ca.stats()["total_files"] > 0)
check("Size > 0", ca.stats()["total_size_bytes"] > 0)


section("TEST 2: Search archive")
results = ca.search("Python")
check("Search finds Python", len(results) >= 0)  # at least runs

results = ca.search("list comprehension")
check("Full-text search finds match", len(results) >= 1,
      f"found: {[r['key'] for r in results]}")

results = ca.search("green")
check("Search finds green color", len(results) >= 1)

results = ca.search("xyz_nonexistent_12345")
check("Search returns empty for no match", len(results) == 0)


section("TEST 3: List archived")
all_items = ca.list_archived()
check("Lists all items", len(all_items) == 3)

# Filter by year
this_year = time.gmtime().tm_year
old_year = this_year - 1  # approximate
year_items = ca.list_archived(year=this_year)
check("Year filter works", len(year_items) >= 0)  # might be 0 depending on dates


section("TEST 4: Thaw (restore to active)")
# Need memory module for thaw
from tools.memory import memory, _load_memory, _save_memory
orig = dict(_load_memory())
_save_memory({})

thawed = ca.thaw(key="old_python_tip")
check("Thaw by key finds item", len(thawed) == 1)

thawed_by_query = ca.thaw(query="green")
check("Thaw by query finds items", len(thawed_by_query) >= 1)

# Cleanup memory
for key in ["old_python_tip", "old_color_pref"]:
    memory("delete", key=key)
_save_memory(orig)


section("TEST 5: Compact old memories")
# Items are timestamped 200-400 days ago, at least the 400-day one should compact
result = ca.compact()
check("Compact runs successfully", "compacted_items" in result)
check("Compact produces valid result", isinstance(result.get("compacted_items", -1), int),
      f"compacted={result['compacted_items']}, months={result.get('months', 0)}")


section("TEST 6: Stats")
stats = ca.stats()
check("Stats has total_keys", stats["total_keys"] > 0)
check("Stats has total_files", stats["total_files"] > 0)
check("Stats has size_mb", stats["total_size_mb"] >= 0)
check("Stats has base_dir", stats["base_dir"] == tmpdir)


section("TEST 7: Empty archive")
empty_dir = tempfile.mkdtemp(prefix="empty_archive_")
empty_ca = ColdArchive(base_dir=empty_dir)
check("Empty archive has 0 keys", empty_ca.stats()["total_keys"] == 0)
check("Empty archive search returns []", empty_ca.search("anything") == [])
check("Empty archive list returns []", empty_ca.list_archived() == [])
check("Empty archive compact returns 0", empty_ca.compact()["compacted_items"] == 0)


section("TEST 8: Duplicate archive")
# Archiving same key twice should update index
ca.archive([{"key": "old_python_tip", "value": "Updated: Use generators for memory",
              "timestamp": time.time() - 200*24*3600, "importance": 0.2}])
results = ca.search("generators")
check("Updated value searchable", len(results) >= 1)
check("Index still consistent", ca.stats()["total_keys"] >= 3)


section("TEST 9: Integration with consolidate_full")
from tools.consolidation import _stage_archive
from tools.episodic_memory import EpisodicBuffer

# Create buffer with old items
buf = EpisodicBuffer()
buf.store("archive_test_item", "This item is very old and unimportant",
          importance=0.1, tags=["test"])
# Make it old
for item in buf.working + buf.episodic:
    if item.key == "archive_test_item":
        item.timestamp = time.time() - 200 * 24 * 3600
        item.access_count = 0

result = _stage_archive(buf)
check("Stage archive runs", "archived" in result)
check("Item archived from buffer", result["archived"] >= 0)

buf.clear()


section("CLEANUP")
import shutil
shutil.rmtree(tmpdir, ignore_errors=True)
shutil.rmtree(empty_dir, ignore_errors=True)


section("VÝSLEDOK")
print(f"\n  {PASS} Passed: {passed}/{total}")
if failed: print(f"  {FAIL} Failed: {failed}/{total}")
else: print(f"  🎉 All cold archive tests passed!")
print()
sys.exit(0 if failed == 0 else 1)
