"""
Test Phase 2: Semantic Store v2 — hybrid search, better embeddings.
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.jarvis_logging import log
import tools.rag_memory as rag
from tools.rag_memory import (
    rag_search, rag_save, rag_read, rag_delete,
    _ensure_init, _hybrid_search, _tokenize, EMBED_MODEL, COLLECTION_NAME,
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


section("SETUP: Init rag_memory v2")
_ensure_init()
check("Collection is v2", COLLECTION_NAME == "jarvis_memory_v2")
check("Embedding model loaded", EMBED_MODEL == "all-mpnet-base-v2")
# BM25 cache may be empty after init if old docs lacked text
# It fills up as saves happen (each save adds to cache)


section("TEST 1: Save & Search")
# Save test facts
for key, val in [
    ("jarvis_memory_v2_test", "Hybrid search s BM25 a dense embeddings funguje"),
    ("test_python_code", "Python používa knižnice numpy, pandas a chromadb"),
    ("test_jarvis_tools", "JARVIS má nástroje: memory, rag_search, execute_command, control_browser"),
    ("test_fogy_personal", "Fogy pracuje na AI pamäťovom systéme s 5 vrstvami"),
]:
    result = rag_save(key, val)
    check(f"Save {key}", "Uložené" in result)

check("BM25 cache populated after saves", len(rag._bm25_cache) >= 4,
      f"{len(rag._bm25_cache)} docs in cache")

# Search
results = rag_search("pamäťový systém", k=3, min_score=0.0)
check("Search finds memory system", "pamäť" in results.lower() or "memory" in results.lower(),
      f"result: {results[:80]}...")

results = rag_search("Python tools", k=3)
check("Search finds Python tools", "python" in results.lower() or "numpy" in results.lower(),
      f"result: {results[:80]}...")

results = rag_search("JARVIS nástroje", k=3)
check("Search finds JARVIS tools", "jarvis" in results.lower(),
      f"result: {results[:80]}...")


section("TEST 2: Hybrid Search (Dense + BM25)")
results = _hybrid_search("AI memory system", k=5)
check("Hybrid search returns results", len(results) > 0, f"count={len(results)}")
check("Results have scores", all("score" in r for r in results))
check("Results have metadata", all("metadata" in r for r in results))
check("Scores are reasonable", all(0 <= r["score"] <= 100 for r in results),
     f"scores: {[r['score'] for r in results[:3]]}")


section("TEST 3: Score Threshold")
results_all = _hybrid_search("AI memory", k=10, min_score=0.0)
results_filtered = _hybrid_search("AI memory", k=10, min_score=0.8)
check("min_score filters results", len(results_filtered) <= len(results_all),
      f"all={len(results_all)}, filtered={len(results_filtered)}")


section("TEST 4: Metadata Filtering")
results = _hybrid_search("test", k=10, filters={"source": "json"})
check("Source filter works", all(r["metadata"].get("source") == "json" for r in results) if results else True,
      f"count={len(results)}")

results = _hybrid_search("test", k=10, filters={"source": "knowledge"})
check("Knowledge filter returns only knowledge docs",
      all(r["metadata"].get("source") == "knowledge" for r in results) if results else True,
      f"count={len(results)}")


section("TEST 5: BM25 Tokenizer")
tokens = _tokenize("Python 3.12 + ChromaDB v2")
check("Tokenizer lowercase", all(t == t.lower() for t in tokens))
check("Tokenizer splits on non-word", "3" in tokens and "12" in tokens)


section("TEST 6: rag_read")
# Read specific key
result = rag_read("jarvis_memory_v2_test")
check("Read by key returns value", "Hybrid search" in result)

# Read all
result = rag_read()
check("Full dump contains ChromaDB info", "ChromaDB" in result)
check("Full dump contains BM25 info", "BM25" in result or "hybrid" in result.lower())
check("Full dump contains model name", EMBED_MODEL in result)


section("TEST 7: rag_delete")
rag_save("test_to_delete", "Temporary")
result = rag_delete("test_to_delete")
check("Delete confirms", "Vymazané" in result)
check("Deleted key not in cache", "json:test_to_delete" not in rag._bm25_cache)


section("TEST 8: Re-index stability")
# Save → delete → re-save
rag_save("test_reindex", "Value 1")
rag_delete("test_reindex")
rag_save("test_reindex", "Value 2")
result = rag_read("test_reindex")
check("Re-save after delete works", "Value 2" in result)
rag_delete("test_reindex")


section("VÝSLEDOK")
print(f"\n  {PASS} Passed: {passed}/{total}")
if failed:
    print(f"  {FAIL} Failed: {failed}/{total}")
else:
    print(f"  🎉 All semantic store tests passed!")
print()
sys.exit(0 if failed == 0 else 1)
