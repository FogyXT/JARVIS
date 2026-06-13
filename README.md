# 🧠 JARVIS — 5-Tier Biologically-Inspired Memory System

**A complete AI memory architecture with Standby Neuron Agents and Neurogenesis.**

Built by [Patrik Fogoš](https://github.com/FogyXT), 18-year-old student from Slovakia.

> *"How do you make an AI that actually remembers? Not just RAG over chunks, but real memory — the kind humans have."*

---

## Why This Exists

Most AI memory is just vector search. Chunk text → embed → retrieve similar chunks. That's not memory. That's a search engine.

Real memory — biological memory — is a **hierarchy of stores** with different speeds, capacities, and purposes. The hippocampus doesn't store everything forever. It captures episodes, replays them during sleep, and gradually consolidates the important ones into the neocortex. Unimportant memories decay. This architecture works so well that evolution hasn't replaced it in 200 million years.

**JARVIS implements this architecture for AI.**

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                  5-TIER MEMORY ARCHITECTURE                    │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  TIER 1+2  EPISODIC BUFFER        Brain: Hippocampus         │
│  ═══════════════════════════════   Speed: <1ms                │
│  64 working + 256 episodic items                              │
│  Ebbinghaus decay: n^0.3 · e^(-λt) · importance              │
│  Forget threshold: 0.05                                       │
│  Promote threshold: 0.65                                      │
│                          ↓                                    │
│  TIER 3    SEMANTIC STORE          Brain: Neocortex           │
│  ═══════════════════════════════   Speed: ~50ms               │
│  ChromaDB v2 · all-mpnet-base-v2 (768-dim)                    │
│  Hybrid search: dense + BM25 → Reciprocal Rank Fusion         │
│  Score thresholding · Metadata filtering                       │
│                          ↓                                    │
│  TIER 4    KNOWLEDGE GRAPH         Brain: Association Cortex  │
│  ═══════════════════════════════   Speed: ~100ms              │
│  spaCy NER + 30+ keyword patterns                              │
│  NetworkX + SQLite persistence                                 │
│  Multi-hop reasoning · Shortest path · Auto-relations          │
│                          ↓                                    │
│  TIER 5    COLD ARCHIVE            Brain: Distributed Cortex  │
│  ═══════════════════════════════   Speed: async               │
│  Filesystem JSON · YYYY/MM organization                       │
│  Full-text search · Thaw to active · Compact                   │
│                                                               │
├──────────────────────────────────────────────────────────────┤
│  CONSOLIDATION PIPELINE (Sleep Analog)                        │
│  ═══════════════════════════════════                          │
│  Decay → Cluster → SemanticMerge(LLM) → Rescore →            │
│  Promote → RelationshipFind(LLM) → Archive → Neurogenesis    │
│                                                               │
│  Quick: 60ms (no LLM, runs every 5 minutes)                   │
│  Full:  ~3s  (DeepSeek-powered merge + relations)             │
├──────────────────────────────────────────────────────────────┤
│  STANDBY NEURON AGENTS                                        │
│  ═══════════════════════════════════                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                    │
│  │ Personal │  │   Tech   │  │ Projects │  ...N agents       │
│  │  Agent   │  │  Agent   │  │  Agent   │                    │
│  │          │  │          │  │          │                    │
│  │ DEEP 💤  │  │ LIGHT 🟡 │  │ DEEP 💤  │                    │
│  │ 0 RAM    │  │ ~3KB RAM │  │ 0 RAM    │                    │
│  │ 0 tokens │  │  ready   │  │ 0 tokens │                    │
│  └──────────┘  └──────────┘  └──────────┘                    │
│                                                               │
│  Wake: trigger regex patterns + centroid similarity           │
│  Vote: all agents score → top K form consensus panel          │
│  Sleep: return to idle after task (0 token consumption)       │
│  Spawn: Neurogenesis creates agents from memory clusters      │
│  Prune: inactive agents auto-removed after 30 days            │
└──────────────────────────────────────────────────────────────┘
```

---

## Two Novel Concepts

### 1. Standby Neuron Agents
Domain-specialized AI agents that behave like biological neurons — they sleep on disk, wake only when relevant, vote in consensus panels, and return to sleep. Most agents exist as JSON files consuming **zero RAM and zero tokens**.

### 2. Neurogenesis
The system automatically spawns new specialized agents when it detects distinct memory clusters (e.g., 6+ memories about Minecraft → new Minecraft agent). Inactive agents self-prune after 30 days.

**No existing system does either of these.**

---

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Use the memory system
python -c "
from tools.memory import memory
from tools.rag_memory import rag_search

# Store a memory — goes to all 4 tiers automatically
memory('save', 'my_fact', 'JARVIS uses a 5-tier memory architecture')

# Read it back — EpisodicBuffer first, ChromaDB fallback
print(memory('read', key='my_fact'))

# Semantic search — hybrid dense+BM25
print(rag_search('memory architecture'))
"
```

---

## Test Coverage

```
test_episodic_memory.py         41/41 ✅   Ebbinghaus decay, overflow, reinforcement
test_memory_integration.py      32/32 ✅   All 4 tiers tested together
test_semantic_store.py          26/26 ✅   Hybrid search, BM25, score filtering
test_knowledge_graph.py         37/37 ✅   Entity extraction, multi-hop, persistence
test_consolidation.py           31/31 ✅   7-stage pipeline, idle detection, scheduler
test_memory_agents.py           42/42 ✅   Wake/sleep, consensus, neurogenesis, pruning
test_cold_archive.py            27/27 ✅   Archive, search, thaw, compact
test_cross_tier_integration.py  88/88 ✅   Full E2E: store→retrieve→decay→consolidate
──────────────────────────────────────────────────────────────────────────
TOTAL                          324/324 ✅
```

---

## Performance

| Operation | Latency |
|-----------|---------|
| EpisodicBuffer exact key | <1ms |
| EpisodicBuffer cosine search | <5ms |
| Semantic hybrid search | ~200ms |
| Knowledge Graph extraction | ~20ms |
| Quick consolidation (7 stages, no LLM) | ~60ms |
| Full consolidation (DeepSeek-powered) | ~3s |
| Agent wake + score + sleep | ~50ms |

| Agent State | RAM | Tokens | Disk |
|-------------|-----|--------|------|
| DEEP_SLEEP | 0 bytes | 0 | ~1KB JSON |
| LIGHT_SLEEP | ~3KB | 0 | ~1KB JSON |
| ACTIVE | ~3KB + context | ~500-2000 | ~1KB JSON |

---

## Key Files

| File | What |
|------|------|
| [`tools/memory_agents.py`](tools/memory_agents.py) | Standby Neuron Agents + Neurogenesis |
| [`tools/episodic_memory.py`](tools/episodic_memory.py) | Episodic Buffer with Ebbinghaus decay |
| [`tools/rag_memory.py`](tools/rag_memory.py) | Semantic Store v2 (hybrid search) |
| [`tools/knowledge_graph.py`](tools/knowledge_graph.py) | Knowledge Graph (entity extraction) |
| [`tools/consolidation.py`](tools/consolidation.py) | 7-stage sleep-like pipeline |
| [`tools/cold_archive.py`](tools/cold_archive.py) | Cold Archive (long-term storage) |
| [`tools/memory.py`](tools/memory.py) | Unified API (all 5 tiers) |
| [`knowledge/`](knowledge/) | Research, architecture decisions, novelty analysis |

---

## License

**AGPL-3.0** — Free for open source. Contact for commercial licensing.

Copyright (C) 2026 Patrik Fogoš | [patrikf2008@gmail.com](mailto:patrikf2008@gmail.com)
