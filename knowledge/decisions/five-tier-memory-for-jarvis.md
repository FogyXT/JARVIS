# Five-Tier AI Memory — Implementation Plan for JARVIS

**Date:** 2026-06-13
**Status:** Plan Phase — ready for prototyping
**Related:** [[ultimate-ai-memory-architecture]] [[standby-neuron-agents]]

---

## Architecture Overview

```
┌────────────────────────────────────────────────────────────┐
│                    JARVIS MAIN LOOP                         │
│  jarvis.py / web_ui/app.py  →  process_with_claude()       │
└──────────────────────────┬─────────────────────────────────┘
                           │
                    ┌──────▼──────┐
                    │  MEMORY API │  ← unified interface
                    └──────┬──────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
   ┌────▼────┐      ┌──────▼──────┐    ┌─────▼─────┐
   │ Tier 1+2│      │   Tier 3    │    │  Tier 4   │
   │ Working │      │  Semantic   │    │ Knowledge │
   │+Episodic│      │   Store     │    │  Graph    │
   └────┬────┘      └──────┬──────┘    └─────┬─────┘
        │                  │                  │
        └──────────────────┼──────────────────┘
                           │
                    ┌──────▼──────┐
                    │   Tier 5    │
                    │Cold Archive │
                    └─────────────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
        ┌─────▼────┐ ┌────▼────┐ ┌────▼────┐
        │ Personal │ │  Tech   │ │Project  │  ← Standby Agents
        │  Agent   │ │  Agent  │ │ Agent   │     (consolidation)
        │  (idle)  │ │ (idle)  │ │ (idle)  │
        └──────────┘ └─────────┘ └─────────┘
```

---

## Phase 0: Logging Foundation (EST: 1 session)

### Goal
Centralized, structured logging for all JARVIS modules — every function entry/exit, errors, and state changes are traceable.

### Files to create
```
tools/logging.py          ← LogManager class (singleton)
```

### Features
- `log.debug("message", module="memory", data={...})` — detailed trace
- `log.info("message")` — normal operations  
- `log.warn("message")` — recoverable issues
- `log.error("message", exc_info=True)` — exceptions with stack trace
- Log levels configurable via `LOG_LEVEL` env var
- Rotating file handler (max 10MB, keep 3 backups)
- Console output with color-coded modules
- Optional JSON output for machine parsing
- `@log.trace()` decorator — auto-log function entry/exit/args/return

### Integration
- Replace all `print()` calls in `jarvis.py`, `web_ui/app.py`, `tools/*.py`
- Add `@trace` to all tool functions so every tool invocation is logged
- Add to `_execute_tool()` dispatch to log every tool call with timing

---

## Phase 1: Enhanced Episodic Buffer (EST: 1-2 sessions)

### Goal
Replace flat key-value memory with timestamped, decaying episodic storage.

### Files to create/modify
```
tools/episodic_memory.py  ← NEW: EpisodicBuffer class
tools/memory.py           ← MODIFY: delegate episodic writes to EpisodicBuffer
```

### EpisodicBuffer API
```python
class EpisodicBuffer:
    """Fast, decaying, timestamped memory buffer."""
    
    def __init__(self, capacity=256):
        self.working = []       # 64 most recent items (numpy arrays for cosine sim)
        self.episodic = []      # 256 items with decay scores
        self.decay_rate = 0.001 # per-second decay (configurable)
        self.reinforcement = 0.1 # boost on access
        
    def store(self, key: str, value: str, importance: float = 0.5):
        """Store with timestamp, initial importance, and decay curve."""
        
    def retrieve(self, key: str = None, query: str = None, k: int = 5):
        """Retrieve by key, or semantic search across buffer."""
        
    def decay(self, now: float = None):
        """Apply Ebbinghaus decay to all items. Called periodically."""
        
    def promote(self, item) -> bool:
        """Check if item should be promoted to semantic store."""
        
    def stats(self) -> dict:
        """Buffer health: item count, avg decay, promotion queue."""
```

### Ebbinghaus Decay Formula
```
score(t) = (n_accesses)^beta × exp(-lambda × delta_t) × initial_importance
```
- `beta = 0.3` (recency boost, human-validated)
- `lambda = 0.001` (decay rate per second)
- `forget_threshold = 0.05` (remove from buffer)
- `promote_threshold = 0.65 OR 5+ accesses in 14 days`

### Integration with existing memory tool
- `memory("save", key, value)` → writes to EpisodicBuffer + JSON + ChromaDB (3 layers)
- `memory("read", key)` → checks EpisodicBuffer first (fast), then ChromaDB (semantic), then JSON (fallback)
- Each read reinforces the item's decay score

---

## Phase 2: Enhanced Semantic Store (EST: 1 session)

### Goal
Upgrade ChromaDB from basic cosine similarity to production-grade hybrid search.

### Files to modify
```
tools/rag_memory.py        ← MODIFY: hybrid search, Matryoshka embeddings
```

### Changes
1. **Better embedding model:** Replace `all-MiniLM-L6-v2` (384-dim, 2021) with `all-mpnet-base-v2` (768-dim, 2023) or `gte-small` (384-dim but 2024 SOTA)
2. **Hybrid search:** dense (embeddings) + sparse (BM25 via `rank_bm25`) → reciprocal rank fusion
3. **Reranker:** Optional cross-encoder reranker for top-K results (e.g., `ms-marco-MiniLM-L-6-v2`)
4. **Metadata filtering:** Support filtering by timestamp range, memory type, tags
5. **Chunk linking:** Store parent-child relationships between memory items (cluster related facts)

### API additions
```python
def rag_search_hybrid(query, k=5, filters=None):
    """Dense + sparse hybrid search with optional metadata filters."""

def rag_cluster_memories(k_clusters=10):
    """Cluster memories by semantic similarity. Used by consolidation."""
```

---

## Phase 3: Knowledge Graph Layer (EST: 2-3 sessions)

### Goal
Build an entity-relationship graph from stored memories to enable multi-hop reasoning.

### Files to create
```
tools/knowledge_graph.py   ← NEW: KnowledgeGraph class
```

### Technology choice: **NetworkX + SQLite**
- Start simple: in-memory graph persisted to SQLite
- No external database needed (Neo4j/FalkorDB are overkill for single-user)
- Can upgrade later if needed

### KnowledgeGraph API
```python
class KnowledgeGraph:
    """Entity-relationship graph for multi-hop memory reasoning."""
    
    def __init__(self, db_path: str):
        self.graph = nx.DiGraph()
        self.db = sqlite3.connect(db_path)
        self._init_schema()
    
    def extract_entities(self, text: str) -> list[dict]:
        """Extract entities from memory text using lightweight NLP."""
        # Strategy: use spaCy NER (en_core_web_sm) + keyword patterns
        # Entities: Person, Organization, Technology, Project, Date, Location
        
    def add_memory(self, key: str, value: str, entities: list = None):
        """Add memory node + entity nodes + relationship edges."""
        
    def query_relations(self, entity: str, hops: int = 2) -> list:
        """Multi-hop query: find all memories related to entity within N hops."""
        
    def find_path(self, entity_a: str, entity_b: str) -> list:
        """Find shortest path between two entities in memory graph."""
        
    def get_context(self, query: str, max_hops: int = 2) -> str:
        """Get graph context for a query: relevant entities + their relations."""
```

### Entity Extraction Pipeline
```
Memory text → spaCy NER → keyword extraction → entity linking → relation extraction
```
- Use lightweight spaCy model (`en_core_web_sm` ~12MB) for English
- Fallback: regex-based extraction for Slovak (spaCy doesn't have Slovak NER)

### Integration
- On `memory("save")`, also run entity extraction and add to graph
- On `rag_search()`, enrich results with graph context (related entities + multi-hop paths)
- On consolidation, detect new relations across memories

---

## Phase 4: Consolidation Pipeline (EST: 2-3 sessions)

### Goal
Implement sleep-like memory consolidation: decay old, promote important, merge similar, discover relations.

### Files to create
```
tools/consolidation.py     ← NEW: ConsolidationPipeline
```

### ConsolidationPipeline
```python
class ConsolidationPipeline:
    """Sleep-like memory consolidation. Runs during system idle."""
    
    def __init__(self, episodic: EpisodicBuffer, semantic: ChromaDB, graph: KnowledgeGraph):
        self.stages = [
            DecayAnalyzer(),      # Apply Ebbinghaus decay, mark forgotten
            ClusterDetector(),     # Find similar memories by embedding
            SemanticMerger(),      # Merge duplicate/similar memories
            ImportanceScorer(),    # Re-score based on access patterns
            Promoter(),           # Promote high-score episodic → semantic
            RelationshipFinder(), # Find cross-memory relations → graph
            Archiver(),           # Move old low-importance to cold archive
        ]
    
    def run(self, mode: str = "quick"):
        """Run consolidation. 'quick' = decay only, 'full' = all stages."""
        # Quick: <1s, no LLM calls, runs every 5 minutes
        # Full: ~5-30s, uses LLM agents, runs during idle or manual trigger
        
    def schedule(self):
        """Start background scheduler for periodic consolidation."""
        # Quick consolidation every 5 minutes
        # Full consolidation after 15+ minutes of idle
```

### Consolidation Stages

| Stage | LLM Calls? | Duration | Frequency |
|-------|-----------|----------|-----------|
| DecayAnalyzer | No | <100ms | Every 5 min |
| ClusterDetector | No (embedding sim) | <500ms | Every 30 min |
| SemanticMerger | Yes (Haiku, cheap) | ~1-3s | Hourly or idle |
| ImportanceScorer | No | <200ms | Every 30 min |
| Promoter | No | <200ms | Hourly |
| RelationshipFinder | Yes (Haiku) | ~2-5s | Idle only |
| Archiver | No | <500ms | Daily |

---

## Phase 5: Standby Neuron Agents (EST: 3-4 sessions)

### Goal
Domain-specialized LLM agents that wake on demand, manage memory partitions, and communicate sparsely.

### Files to create
```
tools/memory_agents.py     ← NEW: MemoryAgent, AgentRouter, AgentBlackboard
```

### Architecture

```python
class MemoryAgent:
    """Domain-specialized memory agent. Zero tokens when idle."""
    
    state: "idle" | "woken" | "active" | "consolidating"
    domain: str              # e.g., "personal", "technical", "projects"
    domain_keywords: set     # keywords that trigger this agent
    domain_embedding: ndarray # centroid of domain memories
    
    def wake_condition(self, query_or_memory: str) -> float:
        """Return relevance score 0-1. Wake if > threshold."""
        # Check keyword overlap + embedding similarity to domain centroid
        
    async def handle_query(self, query: str, context: dict) -> str:
        """Retrieve memories relevant to query within this domain."""
        
    async def handle_store(self, key: str, value: str) -> dict:
        """Validate and enrich memory before storage."""
        
    async def consolidate(self, other_agents: list["MemoryAgent"]):
        """Run domain-specific consolidation + cross-agent communication."""

class AgentRouter:
    """Lightweight always-on classifier. Decides which agents to wake."""
    
    def route(self, input_text: str) -> list[MemoryAgent]:
        """Return list of agents whose wake_condition > threshold."""
        # Embedding similarity: input vs each agent's domain centroid
        # Keyword overlap: fast filter before embedding comparison
        # Returns only agents above relevance threshold

class AgentBlackboard:
    """Shared message board for inter-agent sparse communication."""
    
    def post(self, from_agent: str, message: dict):
        """Post a message visible to specific agents or all."""
        
    def read(self, agent_name: str) -> list[dict]:
        """Read messages addressed to this agent."""
        
    def cleanup(self, max_age_seconds: int = 3600):
        """Remove old messages."""
```

### Domain Agents (Initial Set)

| Agent | Domain | Triggers |
|-------|--------|----------|
| PersonalAgent | Osobné fakty, vzťahy, zdravie | Mená ľudí, osobné zámená, emócie |
| TechAgent | Programovanie, nástroje, kód | Technické termíny, kód, chyby |
| ProjectAgent | JARVIS development, plány | Súbory projektu, architektúra, tasky |

### Token Economy

| Operation | Without Agents | With Standby Agents | Savings |
|-----------|---------------|---------------------|---------|
| Store memory | Monolithic ChromaDB upsert | Domain agent validates + enriches | -10% (richer) |
| Retrieve memory | Search all memories (N items) | Search only relevant domain (~N/3 items) | -66% retrieval tokens |
| Consolidation | Process all memories | Only active domain agents run | -50-80% tokens |
| Idle | Background pipeline always runs | Zero tokens (all agents idle) | -100% idle tokens |

---

## Phase 6: Cold Archive (EST: 1 session)

### Goal
Long-term compressed storage for memories that are rarely accessed.

### Files to create/modify
```
tools/cold_archive.py      ← NEW: ColdArchive class
```

### ColdArchive
- Stores memories as compressed JSON with full metadata
- Organizes by year/month for easy browsing
- Supports "thawing" (restoring to episodic/semantic) on access
- Auto-compacts: merges very old similar memories into summaries
- Path: `D:/JARVIS/archive/memories/YYYY/MM/`

---

## Implementation Order

```
Phase 0: Logging          (today)          ← FOUNDATION
Phase 1: Episodic Buffer  (today/tomorrow) ← Fast tier
Phase 2: Semantic Store   (1 session)      ← Upgrade existing
Phase 3: Knowledge Graph  (2-3 sessions)   ← Relational layer
Phase 4: Consolidation    (2-3 sessions)   ← Sleep analog
Phase 5: Standby Agents   (3-4 sessions)   ← Novel contribution
Phase 6: Cold Archive     (1 session)      ← Final tier
```

**Total EST: 10-14 sessions**

---

## Testing Strategy

### Per-phase tests
- `tests/test_episodic.py` — decay math, buffer overflow, promotion logic
- `tests/test_semantic.py` — hybrid search quality, embedding comparison
- `tests/test_knowledge_graph.py` — entity extraction, multi-hop queries
- `tests/test_consolidation.py` — pipeline stages, merge correctness
- `tests/test_agents.py` — wake conditions, routing accuracy, token counting

### Integration tests
- Store → retrieve → decay → consolidate → retrieve again
- Multi-agent: two agents share overlapping memory → verify cross-communication
- Scale test: 10,000 memories → query latency under 200ms

### Quality metrics
- **Retention rate:** What % of important memories survive 30 days of decay?
- **Retrieval precision:** For a known memory, does it appear in top-3 results?
- **Token efficiency:** Tokens consumed per memory operation (target: <50 tokens for simple retrieval)
- **Consolidation quality:** After consolidation, are duplicate memories merged? Are relations discovered?

---

## Files Summary

| File | Status | Purpose |
|------|--------|---------|
| `tools/logging.py` | NEW | Structured logging for all modules |
| `tools/episodic_memory.py` | NEW | Ebbinghaus-decaying buffer (tiers 1+2) |
| `tools/memory.py` | MODIFY | Delegate to episodic + semantic + graph |
| `tools/rag_memory.py` | MODIFY | Hybrid search, better embeddings (tier 3) |
| `tools/knowledge_graph.py` | NEW | Entity-relation graph (tier 4) |
| `tools/consolidation.py` | NEW | Sleep-like consolidation pipeline |
| `tools/memory_agents.py` | NEW | Standby neuron agents |
| `tools/cold_archive.py` | NEW | Long-term compressed storage (tier 5) |
| `tests/*.py` | NEW | Per-phase unit + integration tests |
