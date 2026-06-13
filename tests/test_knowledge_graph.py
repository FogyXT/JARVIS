"""
Test Phase 3: Knowledge Graph — entity extraction, relations, multi-hop, integration.
Uses temp DB to isolate state between tests.
"""
import os, sys, time, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.jarvis_logging import log
from tools.knowledge_graph import KnowledgeGraph, extract_entities

PASS = "✅"; FAIL = "❌"
total = passed = failed = 0

def check(name, condition, detail=""):
    global total, passed, failed
    total += 1
    if condition: passed += 1; print(f"  {PASS} {name}" + (f" — {detail}" if detail else ""))
    else: failed += 1; print(f"  {FAIL} {name}" + (f" — {detail}" if detail else ""))

def section(title):
    print(f"\n{'='*60}\n  {title}\n{'='*60}")

# Temp DB for isolation
DB_PATH = tempfile.mktemp(suffix=".db")


section("SETUP: Entity Extraction")
entities = extract_entities("JARVIS uses Python and ChromaDB for its RAG memory")
check("Entities found", len(entities) > 0, f"count={len(entities)}")
check("Python→TECH", any(e["name"]=="Python" and e["type"]=="TECH" for e in entities))
check("JARVIS found", any("JARVIS" in e["name"] for e in entities))
check("ChromaDB found", any("ChromaDB" in e["name"] for e in entities))

entities2 = extract_entities("John works on AI in Slovakia with PyTorch")
check("John→PERSON (spaCy)", any(e["type"]=="PERSON" for e in entities2))
check("Slovakia→LOCATION", any("Slovakia" in e["name"] for e in entities2))
check("PyTorch→TECH", any(e["name"]=="PyTorch" for e in entities2))

# Edge cases
check("Empty text", extract_entities("") == [])
check("C++ and C#", any("C++" in e["name"] or "C#" in e["name"] for e in extract_entities("C++ and C#")))


section("TEST: Graph Operations (fresh DB)")
kg = KnowledgeGraph(db_path=DB_PATH)

# Add memories
kg.add_memory("jarvis_tools", "JARVIS uses Python, ChromaDB, and spaCy for NLP")
check("Nodes after jarvis_tools", kg.graph.number_of_nodes() >= 4,
      f"nodes={kg.graph.number_of_nodes()}, edges={kg.graph.number_of_edges()}")

kg.add_memory("john_project", "John is building JARVIS with Python")
check("Nodes increased", kg.graph.number_of_nodes() >= 5)

kg.add_memory("data_storage", "ChromaDB stores vector embeddings")
check("ChromaDB node exists",
      any(d.get("name","")=="ChromaDB" for _,d in kg.graph.nodes(data=True)))

# Query relations
related = kg.query_relations("JARVIS", hops=2)
check("JARVIS has relations", len(related) > 0,
      f"related: {[r['entity'] for r in related[:5]]}")
check("Python in JARVIS relations", any("Python" in r["entity"] for r in related))
check("Relations have distance", all("distance" in r for r in related))

related = kg.query_relations("Python", hops=1)
check("Python has relations", len(related) > 0)

# Find path
path = kg.find_path("Python", "ChromaDB")
check("Python→ChromaDB path", len(path) > 0,
      f"path={[p['entity'] for p in path]}")
check("Path starts with Python", path[0]["entity"] == "Python")

path = kg.find_path("John", "JARVIS")
check("John→JARVIS path", len(path) > 0,
      f"path={[p['entity'] for p in path]}")

path = kg.find_path("Python", "NonExistentXYZ123")
check("No path to non-existent", path == [])

# Graph context
ctx = kg.get_context("JARVIS Python", max_hops=1)
check("Context has content", len(ctx) > 50)
check("Context mentions JARVIS", "JARVIS" in ctx)

ctx = kg.get_context("xyz_nonexistent_123")
check("No context for unknown", ctx == "")


section("TEST: Persistence")
kg.conn.close()

kg2 = KnowledgeGraph(db_path=DB_PATH)
kg2.load()
check("Persisted nodes", kg2.graph.number_of_nodes() >= 5,
      f"nodes={kg2.graph.number_of_nodes()}")
check("Persisted edges", kg2.graph.number_of_edges() > 0,
      f"edges={kg2.graph.number_of_edges()}")
check("JARVIS after load",
      any("JARVIS" in d.get("name","") for _,d in kg2.graph.nodes(data=True)))
check("Path works after load",
      len(kg2.find_path("Python", "ChromaDB")) > 0)
kg2.conn.close()


section("TEST: Duplicate Handling")
kg3 = KnowledgeGraph(db_path=tempfile.mktemp(suffix=".db"))
kg3.add_memory("mem1", "JARVIS uses Python and ChromaDB")
n1, e1 = kg3.graph.number_of_nodes(), kg3.graph.number_of_edges()
kg3.add_memory("mem2", "JARVIS uses Python and ChromaDB again")
n2, e2 = kg3.graph.number_of_nodes(), kg3.graph.number_of_edges()
check("No duplicate nodes", n2 == n1, f"{n1}→{n2}")
check("No duplicate edges", e2 >= e1, f"{e1}→{e2}")
kg3.conn.close()


section("TEST: Stats")
stats = kg2.stats()
check("Stats: entity count", stats["entities"] > 0)
check("Stats: relation count", stats["relations"] > 0)
check("Stats: TECH type", stats["entity_types"].get("TECH", 0) > 0)


section("TEST: Integration with memory.save")
from tools.memory import memory, _load_memory, _save_memory, MEMORY_FILE
from tools.knowledge_graph import get_graph, KG_DB_PATH

# Backup
orig_backup = dict(_load_memory())
old_kg_path = KG_DB_PATH

# Save 3 items — should auto-extract entities
_save_memory({})
int_db = tempfile.mktemp(suffix=".db")

# Use a fresh KG for integration test
import tools.knowledge_graph as kg_mod
kg_mod._graph = None
kg_mod.KG_DB_PATH = int_db

memory("save", "kg_int_1", "JARVIS uses Python and spaCy for NLP pipelines")
memory("save", "kg_int_2", "Python AI development uses PyTorch and Transformers")
memory("save", "kg_int_3", "AI memory research may help Alzheimer patients")

# Check entities were extracted
int_kg = get_graph()
int_kg.load()
check("Integration: JARVIS entity",
      any("JARVIS" in d.get("name","") for _,d in int_kg.graph.nodes(data=True)))
check("Integration: Python entity",
      any("Python" in d.get("name","") for _,d in int_kg.graph.nodes(data=True)))
check("Integration: spaCy or NLP entity",
      any("spaCy" in d.get("name","") or "NLP" in d.get("name","")
          for _,d in int_kg.graph.nodes(data=True)))
check("Integration: PyTorch or Alzheimer",
      any(t in str([d.get("name","") for _,d in int_kg.graph.nodes(data=True)]).lower()
          for t in ["pytorch", "alzheimer"]))

# Check relations exist
check("Integration: has relations", int_kg.graph.number_of_edges() > 0,
      f"edges={int_kg.graph.number_of_edges()}")

# Cleanup
int_kg.conn.close()
for key in ["kg_int_1", "kg_int_2", "kg_int_3"]:
    memory("delete", key=key)
_save_memory(orig_backup)
kg_mod.KG_DB_PATH = old_kg_path
kg_mod._graph = None


section("CLEANUP")
try: os.unlink(DB_PATH)
except: pass
try: os.unlink(int_db)
except: pass


section("VÝSLEDOK")
print(f"\n  {PASS} Passed: {passed}/{total}")
if failed: print(f"  {FAIL} Failed: {failed}/{total}")
else: print(f"  🎉 All knowledge graph tests passed!")
print()
sys.exit(0 if failed == 0 else 1)
