"""
Knowledge Graph — entitno-relačná vrstva pamäte (Tier 4).

Umožňuje:
- Extrakciu entít z textu (spaCy EN NER + keyword fallback)
- Budovanie grafu entít a vzťahov (NetworkX + SQLite)
- Multi-hop reasoning — nájdi všetky spomienky spojené s entitou do N skokov
- Find path medzi dvomi entitami
- Graph context pre sémantické vyhľadávanie

Integrácia:
- memory("save") → extract entities → add to graph
- rag_search() → enrich results with graph context
- Konsolidácia → discover new relations between existing entities

Použitie:
    from tools.knowledge_graph import get_graph
    kg = get_graph()
    kg.add_memory("jarvis_tools", "JARVIS používa Python a ChromaDB")
    entities = kg.extract_entities("JARVIS používa Python a ChromaDB")
    context = kg.get_context("JARVIS memory")
"""

import os
import re
import json
import sqlite3
import time
from typing import Optional, Any

import networkx as nx

from tools.jarvis_logging import log


# ── Config ────────────────────────────────────────────────────────────────

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KG_DB_PATH = os.path.join(PROJECT_ROOT, "knowledge_graph.db")

# Entity types
ENTITY_TYPES = ["PERSON", "ORG", "TECH", "PROJECT", "DATE", "LOCATION", "CONCEPT"]

# Regex patterns for keyword-based entity extraction (EN + SK)
KEYWORD_PATTERNS = {
    "TECH": [
        r"\b(Python|JavaScript|TypeScript|Rust|Go|Java|HTML|CSS|React|Vue|Node\.js|Docker|Git|Linux|Windows|macOS)\b",
        r"(?<!\w)(C\+\+|C#|SQL)(?!\w)",
        r"\b(ChromaDB|Qdrant|Pinecone|Neo4j|FalkorDB|PostgreSQL|SQLite|Redis|MongoDB)\b",
        r"\b(API|REST|GraphQL|JSON|XML|HTTP|HTTPS|WebSocket|SSE)\b",
        r"\b(JARVIS|Claude|GPT|DeepSeek|Anthropic|OpenAI|AI|LLM|RAG|embedding|token)\b",
        r"\b(numpy|pandas|spaCy|spacy|NetworkX|PyTorch|TensorFlow|sentence.transformers|Transformers)\b",
        r"\b(Google|Microsoft|Apple|Amazon|Meta|Anthropic)\b",
    ],
    "PROJECT": [
        r"\b(JARVIS|Jarvis)\b",
        r"\b(project[: ]?\w+)\b",
        r"\b(tool[: ]?\w+)\b",
    ],
    "CONCEPT": [
        r"\b(memory|pamäť|forgetting|zabúdanie|consolidation|konsolidácia)\b",
        r"\b(embedding|vector|vektor|semantic|sémantick[ýé]|graph|graf)\b",
        r"\b(decay|reinforcement|posilnenie|threshold|retrieval)\b",
        r"\b(Alzheimer|alzheimer|dementia|memory loss|strata pamäte)\b",
    ],
}

# Common English words to NOT extract as entities
STOP_ENTITIES = {"the", "a", "an", "is", "was", "are", "were", "be", "been",
                 "have", "has", "had", "do", "does", "did", "will", "would",
                 "can", "could", "may", "might", "shall", "should", "this",
                 "that", "these", "those", "it", "its", "he", "she", "they",
                 "we", "you", "i", "me", "him", "her", "us", "them", "my",
                 "your", "his", "our", "their", "no", "not", "yes", "or",
                 "and", "but", "if", "then", "else", "when", "where", "why",
                 "how", "what", "who", "which", "all", "each", "every", "both",
                 "few", "more", "most", "some", "any", "one", "two", "three"}


# ── spaCy loader (lazy singleton) ─────────────────────────────────────────

_nlp = None


def _get_nlp():
    """Lazy load spaCy model (ťažký import)."""
    global _nlp
    if _nlp is None:
        try:
            import spacy
            _nlp = spacy.load("en_core_web_sm")
            log.info("spaCy model loaded", module="kg", data={"model": "en_core_web_sm"})
        except ImportError:
            log.warn("spaCy not available, using keyword extraction only", module="kg")
            _nlp = False
        except Exception as e:
            log.warn(f"spaCy model load failed: {e}", module="kg")
            _nlp = False
    return _nlp if _nlp is not False else None


# ── Entity Extraction ─────────────────────────────────────────────────────

def extract_entities(text: str) -> list[dict]:
    """Extrahuj entity z textu. Použije spaCy NER + keyword patterns.

    Returns:
        [{"name": "Python", "type": "TECH", "method": "keyword"}, ...]
    """
    entities = {}
    text_lower = text.lower()

    # 1. Keyword-based extraction (funguje pre EN aj SK)
    for etype, patterns in KEYWORD_PATTERNS.items():
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                name = match.group(1) if match.lastindex else match.group(0)
                # Skip stop words
                if name.lower() in STOP_ENTITIES:
                    continue
                # Normalize: capitalize first letter
                name = name[0].upper() + name[1:] if name else name
                key = (name.lower(), etype)
                if key not in entities or entities[key]["method"] != "spacy":
                    entities[key] = {"name": name, "type": etype, "method": "keyword"}

    # 2. spaCy NER (doplní PERSON, ORG, DATE, GPE → LOCATION)
    nlp = _get_nlp()
    if nlp:
        try:
            doc = nlp(text[:5000])  # truncate for performance
            for ent in doc.ents:
                name = ent.text.strip()
                if not name or len(name) < 2 or name.lower() in STOP_ENTITIES:
                    continue
                # Map spaCy labels to our types
                spacy_map = {
                    "PERSON": "PERSON", "PER": "PERSON",
                    "ORG": "ORG", "GPE": "LOCATION", "LOC": "LOCATION",
                    "DATE": "DATE", "TIME": "DATE",
                    "PRODUCT": "TECH", "WORK_OF_ART": "CONCEPT",
                }
                etype = spacy_map.get(ent.label_, "CONCEPT")
                key = (name.lower(), etype)
                if key not in entities:
                    entities[key] = {"name": name, "type": etype, "method": "spacy"}
        except Exception as e:
            log.debug(f"spaCy extraction error: {e}", module="kg")

    return sorted(entities.values(), key=lambda x: x["name"])


# ── Knowledge Graph ───────────────────────────────────────────────────────

class KnowledgeGraph:
    """Entity-relationship graph for multi-hop memory reasoning."""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or KG_DB_PATH
        self.graph = nx.DiGraph()
        self._init_db()

    def _init_db(self):
        """Initialize SQLite schema."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS entities (
                id TEXT PRIMARY KEY,     -- "name|type"
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                first_seen REAL NOT NULL,
                last_seen REAL NOT NULL,
                access_count INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS relations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                relation_type TEXT NOT NULL DEFAULT 'related_to',
                memory_key TEXT,
                created REAL NOT NULL,
                FOREIGN KEY (source_id) REFERENCES entities(id),
                FOREIGN KEY (target_id) REFERENCES entities(id)
            );
            CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(type);
            CREATE INDEX IF NOT EXISTS idx_relations_source ON relations(source_id);
            CREATE INDEX IF NOT EXISTS idx_relations_target ON relations(target_id);
        """)
        self.conn.commit()

    # ── Entity Management ──────────────────────────────────────────

    def _entity_id(self, name: str, etype: str) -> str:
        return f"{name.lower()}|{etype}"

    def _upsert_entity(self, name: str, etype: str) -> str:
        """Insert or update entity. Returns entity_id."""
        eid = self._entity_id(name, etype)
        now = time.time()
        self.conn.execute("""
            INSERT INTO entities (id, name, type, first_seen, last_seen, access_count)
            VALUES (?, ?, ?, ?, ?, 1)
            ON CONFLICT(id) DO UPDATE SET
                last_seen = excluded.last_seen,
                access_count = access_count + 1
        """, (eid, name, etype, now, now))
        self.conn.commit()

        # Sync to NetworkX
        if eid not in self.graph:
            self.graph.add_node(eid, name=name, type=etype)
        return eid

    def _add_relation(self, source_id: str, target_id: str,
                      relation_type: str = "related_to", memory_key: str = None):
        """Add edge between two entities."""
        if source_id == target_id:
            return
        # Check if relation already exists
        existing = self.conn.execute(
            "SELECT id FROM relations WHERE source_id=? AND target_id=? AND relation_type=?",
            (source_id, target_id, relation_type)
        ).fetchone()
        if existing:
            return  # already exists

        self.conn.execute("""
            INSERT INTO relations (source_id, target_id, relation_type, memory_key, created)
            VALUES (?, ?, ?, ?, ?)
        """, (source_id, target_id, relation_type, memory_key, time.time()))
        self.conn.commit()

        # Sync to NetworkX
        self.graph.add_edge(source_id, target_id, relation=relation_type, memory_key=memory_key)

    # ── Memory Integration ──────────────────────────────────────────

    def add_memory(self, key: str, value: str):
        """Extract entities from memory and add to graph.

        Called automatically from memory("save").
        """
        text = f"{key}: {value}"
        entities = extract_entities(text)
        if not entities:
            log.debug(f"No entities found in: {key}", module="kg")
            return

        entity_ids = []
        for ent in entities:
            eid = self._upsert_entity(ent["name"], ent["type"])
            entity_ids.append(eid)

        # Create relations between co-occurring entities
        for i in range(len(entity_ids)):
            for j in range(i + 1, len(entity_ids)):
                # Determine relation type based on entity types
                src_type = self.graph.nodes[entity_ids[i]]["type"]
                tgt_type = self.graph.nodes[entity_ids[j]]["type"]
                rel_type = self._infer_relation(src_type, tgt_type)

                # Bidirectional
                self._add_relation(entity_ids[i], entity_ids[j], rel_type, key)
                self._add_relation(entity_ids[j], entity_ids[i], rel_type, key)

        log.debug(f"KG: {len(entities)} entities, {len(entity_ids)} nodes added from '{key}'",
                 module="kg", data={"entities": [e["name"] for e in entities[:5]]})

    def _infer_relation(self, type_a: str, type_b: str) -> str:
        """Infer relation type between entity types."""
        if type_a == type_b:
            return "related_to"
        if "PERSON" in (type_a, type_b) and "PROJECT" in (type_a, type_b):
            return "works_on"
        if "TECH" in (type_a, type_b) and "PROJECT" in (type_a, type_b):
            return "uses"
        if "PERSON" in (type_a, type_b) and "TECH" in (type_a, type_b):
            return "uses"
        return "related_to"

    # ── Query ─────────────────────────────────────────────────────────

    def query_relations(self, entity_name: str, hops: int = 2) -> list[dict]:
        """Find all entities and relations connected to entity_name within N hops.

        Returns:
            [{"entity": "Python", "type": "TECH", "distance": 1, "paths": [...]}, ...]
        """
        # Find entity by name (fuzzy match)
        matching = []
        for node_id, data in self.graph.nodes(data=True):
            if entity_name.lower() in data.get("name", "").lower():
                matching.append(node_id)

        if not matching:
            # Try exact match with type
            log.debug(f"Entity '{entity_name}' not found in graph", module="kg")
            return []

        results = []
        seen = set()
        for start_node in matching:
            try:
                # BFS with depth limit
                paths = nx.single_source_shortest_path_length(
                    self.graph, start_node, cutoff=hops
                )
                for node_id, distance in paths.items():
                    if node_id == start_node:
                        continue
                    if node_id in seen:
                        continue
                    seen.add(node_id)
                    data = self.graph.nodes[node_id]
                    # Find edge data
                    edges = list(self.graph.in_edges(node_id)) + list(self.graph.out_edges(node_id))
                    edge_data = [self.graph.edges[e].get("relation", "related_to") for e in edges[:3]]

                    results.append({
                        "entity": data.get("name", node_id),
                        "type": data.get("type", "?"),
                        "distance": distance,
                        "relations": edge_data[:3],
                    })
            except nx.NetworkXError:
                pass

        # Sort by distance
        results.sort(key=lambda x: x["distance"])
        return results

    def find_path(self, entity_a: str, entity_b: str) -> list[dict]:
        """Find shortest path between two entities in the graph."""
        # Find node IDs
        nodes_a = [n for n, d in self.graph.nodes(data=True)
                   if entity_a.lower() in d.get("name", "").lower()]
        nodes_b = [n for n, d in self.graph.nodes(data=True)
                   if entity_b.lower() in d.get("name", "").lower()]

        if not nodes_a or not nodes_b:
            return []

        # Try all combinations
        best_path = None
        best_len = float("inf")
        for na in nodes_a:
            for nb in nodes_b:
                try:
                    path = nx.shortest_path(self.graph, na, nb)
                    if len(path) < best_len:
                        best_len = len(path)
                        best_path = path
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    continue

        if not best_path:
            return []

        result = []
        for node_id in best_path:
            data = self.graph.nodes[node_id]
            result.append({"entity": data.get("name", node_id), "type": data.get("type", "?")})
        return result

    def get_context(self, query: str, max_hops: int = 2) -> str:
        """Get graph context for a query — relevant entities and their relations.

        Returns formatted string for inclusion in retrieval results.
        """
        # Extract entities from query
        query_entities = extract_entities(query)
        if not query_entities:
            log.debug("No entities extracted from query for graph context", module="kg")
            return ""

        lines = ["\n🕸️ Knowledge Graph context:"]
        seen = set()

        for q_ent in query_entities[:3]:  # max 3 query entities
            related = self.query_relations(q_ent["name"], hops=max_hops)

            # Show direct relations
            direct = [r for r in related if r["distance"] == 1][:5]
            if direct:
                ent_names = [f"{r['entity']}({r['type']})" for r in direct[:5]]
                lines.append(f"  {q_ent['name']} → {', '.join(ent_names)}")
                seen.update(r["entity"] for r in direct)

            # Show 2-hop relations (only new ones)
            two_hop = [r for r in related if r["distance"] == 2 and r["entity"] not in seen][:3]
            if two_hop:
                ent_names = [f"{r['entity']}({r['type']})" for r in two_hop]
                lines.append(f"  {q_ent['name']} → ... → {', '.join(ent_names)}")

        if len(lines) == 1:
            return ""  # no related entities found
        return "\n".join(lines)

    # ── Persistence ───────────────────────────────────────────────────

    def load(self):
        """Load graph from SQLite into NetworkX."""
        self.graph.clear()

        # Load entities
        for row in self.conn.execute("SELECT id, name, type FROM entities"):
            eid, name, etype = row
            self.graph.add_node(eid, name=name, type=etype)

        # Load relations
        for row in self.conn.execute(
            "SELECT source_id, target_id, relation_type, memory_key FROM relations"
        ):
            source_id, target_id, rel_type, mem_key = row
            if source_id in self.graph and target_id in self.graph:
                self.graph.add_edge(source_id, target_id, relation=rel_type, memory_key=mem_key)

        node_count = self.graph.number_of_nodes()
        edge_count = self.graph.number_of_edges()
        if node_count > 0:
            log.info(f"KG loaded: {node_count} entities, {edge_count} relations", module="kg")

    # ── Stats ─────────────────────────────────────────────────────────

    def stats(self) -> dict:
        """Graph statistics."""
        degrees = dict(self.graph.degree()) if self.graph.number_of_nodes() > 0 else {}
        top_entities = sorted(degrees.items(), key=lambda x: x[1], reverse=True)[:10]
        return {
            "entities": self.graph.number_of_nodes(),
            "relations": self.graph.number_of_edges(),
            "entity_types": {t: sum(1 for _, d in self.graph.nodes(data=True)
                                    if d.get("type") == t)
                             for t in ENTITY_TYPES},
            "top_connected": [{"entity": self.graph.nodes[eid].get("name", eid),
                               "connections": deg}
                              for eid, deg in top_entities],
        }

    def close(self):
        """Close DB connection."""
        self.conn.close()


# ── Singleton ─────────────────────────────────────────────────────────────

_graph: Optional[KnowledgeGraph] = None


def get_graph() -> KnowledgeGraph:
    """Získaj singleton KnowledgeGraph (lazy init)."""
    global _graph
    if _graph is None:
        _graph = KnowledgeGraph(db_path=KG_DB_PATH)
        _graph.load()
    return _graph
