# AI Memory & Context Management: Research Patterns for JARVIS

> Compiled: 2026-06-11 — Web research across Anthropic docs, arXiv, production systems, and open-source libraries.

---

## AREA 1: Prompt Caching & Context Management

### Anthropic Prompt Caching — How It Works

Prompt caching avoids re-encoding static portions of the prompt on every API call. On Claude Sonnet 4.6 the minimum cacheable block is **2048 tokens**; for Opus models it is **4096 tokens**. A maximum of **4 explicit cache breakpoints** per request is allowed. Cached content incurs a small write penalty (1.25x for 5-minute TTL, 2x for 1-hour TTL) and delivers reads at **0.1x cost**. The `ephemeral` type defaults to a 5-minute TTL; `"ttl": "1h"` extends it.

### Where to Place Breakpoints

The single most important rule: **put the `cache_control` breakpoint at the end of the last *static* block**. If you place it on a block that changes per-request (timestamp, user message), every call becomes a cache write and you never see cache-read savings. The recommended pattern is:

- **System prompt** — prime candidate, nearly static across turns.
- **Tool definitions** — keep stable and place a breakpoint on the last tool block so the entire tools section is cached alongside the system prompt.
- **History** — for multi-turn conversations, use automatic caching (single top-level flag) so the API manages breakpoints as the conversation grows.

### Cache Invalidation Hierarchy

Changing any element invalidates differently:

1. **Tool schema change** — invalidates everything (system + messages).
2. **System prompt change** — invalidates system + messages cache.
3. **Messages change** — only invalidates the message cache.
4. **Images / thinking blocks** — only affect their own message block.

### Context Window Strategies

Three core techniques, used in combination:

| Strategy | Cost | Quality | Use Case |
|---|---|---|---|
| **Sliding Window** | Free | Low | Baseline — keep last N turns, drop the rest |
| **Summarization** | ~1 extra LLM call | High | Compress old turns into a summary item |
| **Truncation (compact)** | Free | Medium | Rule-based: clip large tool outputs, replace tool-results with stubs |

### Token Budget Allocation (mengram / AFM patterns)

Modern context managers allocate a **token budget across named sections** rather than a single cap:

```
system_prompt  |  summary  |  recent_history  |  retrieved_memories  |  tool_outputs
```

Each section gets a reserved `max_tokens` with overflow spilling to truncation or summarization. Adaptive Focus Memory (AFM, 2025) goes further: it assigns every past message a **fidelity tier** — FULL, COMPRESSED, or PLACEHOLDER — based on a composite score of semantic similarity, recency decay, and importance classification, achieving 66% token reduction over naive replay.

### Key Takeaways for JARVIS

- JARVIS's current single breakpoint on the last tool block is correct. Avoid embedding session-mutating data (memory content, timestamps) in the system prompt — that would invalidate the cache every turn. The auto-load of memory at first user message (prepended, not in system prompt) is exactly the right pattern.
- If context grows beyond ~15 turns, add a second breakpoint to stay within the 20-block lookback window.
- Consider explicit token budgets for history vs. retrieved memories vs. tool results once the project scales beyond simple turn-by-turn.

---

## AREA 2: Long-Term Memory for AI Assistants

### Hybrid Architecture — The 2025 Consensus

No single storage paradigm suffices. Production-grade systems (AutoMem, MemoriesDB, OpenMemory, MongoDB AI Memory) converge on a **three-pillar hybrid**:

1. **Vector store** (Qdrant, pgvector, ChromaDB) — semantic similarity retrieval.
2. **Graph store** (FalkorDB, Neo4j, in-memory adjacency) — relational structure, typed edges, causal/temporal links.
3. **JSON key-value** (SQLite, MongoDB, local file) — flexible metadata, provenance tracking, importance scores.

ChromaDB (which JARVIS uses) fills the vector role well. Adding a lightweight graph layer (even an in-memory adjacency list) and retaining the JSON memory file covers the full spectrum.

### Memory Consolidation — Merging, Deduping, Resolving

The research community is moving toward **hybrid deterministic + LLM-assisted consolidation**:

| Sub-task | Technique | Best Practice |
|---|---|---|
| **Near-duplicate detection** | Cosine similarity cluster (threshold ~0.80–0.92) + union-find | Cluster first, merge batch-wise |
| **Fact merging** | LLM synthesis of cluster into one entry | Episodic + summarizer dual-agent (OmniMemory) |
| **Contradiction resolution** | Three strategies: recency-wins, source-priority, or LLM-adjudicated | Prefer deterministic rules (version IDs, timestamps) over pure LLM judgment — arXiv 2606.01435 showed +10.8 points using `max(serial)` over LLM pipeline |
| **UPDATE / DELETE / SKIP** | OmniMemory's three operations | DELETE contradicts, UPDATE merges fragments, SKIP drops redundancies |

### Memory Decay & Importance Scoring

Multi-factor scoring is standard. The dominant formula (Xu, 2025):

```
S(M_i) = alpha * Recency + beta * Relevance + gamma * UserUtility
```

Where:
- **Recency** = exponential decay `e^(-lambda * delta-t)`
- **Relevance** = cosine similarity to current task embedding
- **UserUtility** = human pin/forget override (0 to N)

Biologically-inspired decay models (YourMemory's Ebbinghaus curve, Dory's 3-zone active/archived/expired, Kore's importance-tiered half-lives) add nuance — e.g., strategic facts decay slower than trivial ones. **Nothing is truly deleted** in most systems; dampening/archiving is preferred over hard removal.

### When to Promote Short-Term to Long-Term

Promotion triggers found across systems:
- **Access frequency**: A fact retrieved N+ times across sessions.
- **Explicit user signal**: A pinned or starred memory.
- **Contradiction resolution**: A consensus fact surviving a merge cycle.
- **Offline consolidation**: Periodic (nightly) "sleep cycle" that runs a multi-step pipeline (River Algorithm's 12-step purify phase).

### User Profile Construction

The 2025 literature (RGMem, BUMP, PersonaX, UserGPT) converges on:

- **Implicit, self-supervised profiles** — inferred from conversation history, not manually curated.
- **Multi-scale**: Micro-level interactions coarse-grained into high-level traits (RGMem's renormalization group approach).
- **Offline extraction, online retrieval**: PersonaX decouples profiling from inference — build profiles offline, retrieve at query time.
- **Struggles**: Current frontier models achieve only ~50% accuracy on dynamic profiling benchmarks (PERSONAMEM). Ontology-augmented approaches (PLOS ONE 2026) outperform pure LLM extraction by 17+ points in low-resource contexts.

### Key Takeaways for JARVIS

- The existing `jarvis_memory.json` key-value store is a solid foundation. Add semantic chunking + ChromaDB vector retrieval for long-term search capacity.
- For consolidation: implement a periodic (every N turns or daily) LLM pass that clusters similar facts, resolves contradictions (recency-wins as default), and merges duplicates.
- For user profiling: a single "about Fogy" memory key that gets refined over time is simple and effective. Upgrade to an implicit profile that extracts preferences from conversation history once the memory store grows substantially.

---

## AREA 3: Knowledge Retrieval Patterns

### Proactive vs. Reactive Search

| Mode | When | Mechanism |
|---|---|---|
| **Reactive** (default) | Model detects a knowledge gap mid-turn | Tool call → search → inject results |
| **Proactive** | Session start, topic shift | Pre-fetch relevant memories before the user speaks |
| **Background** | Idle periods | Index new data, consolidate, prefetch likely next topics |

JARVIS already auto-loads memory on first input. Extending this to proactive retrieval on every turn — searching memory + web in parallel before the Claude call — would reduce latency and improve response quality.

### Multi-Stage Retrieval Pipeline

The 2025 production standard is a **3-stage pipeline** with separate TopK controls per stage:

```
Stage 1: BM25 + ANN vector search  → top 100–500 candidates (wide recall)
Stage 2: Dense embedding scoring    → top 50–200 (semantic filter)
Stage 3: Cross-encoder reranker     → top 5–10 (precision, feeds LLM)
```

**Reciprocal Rank Fusion (RRF)** is the standard method for combining BM25 and dense scores without calibration. A cross-encoder reranker on the final stage typically improves relevance by 10%+ over dense-only retrieval.

For a project like JARVIS where the memory store is small-to-medium (<10k entries), stages 2 and 3 can be collapsed: ChromaDB's built-in ANN search serves as both semantic filter and final ranker.

### Query Expansion

Before searching, expand the user's query:
- **Synonym expansion** — map terms to canonical forms.
- **Sub-queries** — break compound requests into atomic searches.
- **Hypothetical document embedding** — generate a synthetic ideal answer first, then search by it.

### Personalization Patterns

- **User-specific collections** (partition ChromaDB by user ID) — mandatory for multi-user but overkill for single-user JARVIS.
- **Weighted retrieval** — boost memories tagged with the current user's ID or preference labels.
- **Evidence quorum** — for high-stakes facts, require confirmation across multiple retrievers before presenting as truth.

### Key Takeaways for JARVIS

- As a single-user system, JARVIS can skip user partitioning and keep a flat memory namespace.
- Implement a simple 2-stage pipeline: ChromaDB (stand-in for stage 1–2) + lightweight reranking (cross-encoder if latency permits, or just TopK cap if not).
- Add query expansion at the retrieval call site — rewrite the user message into a search query before hitting the store. The model is already good at this; a system instruction to generate search queries before tool calls would suffice.
- For web search (Anthropic server-side tool), consider supplementing with local fallback search when the built-in tool is unavailable, using the existing `tools/image_search.py` pattern.

---

## Synthesis: What JARVIS Should Borrow

| Pattern | Priority | Effort | Notes |
|---|---|---|---|
| Cache breakpoint on last tool block (already done) | Keep | None | Verified correct |
| No session data in system prompt (already done) | Keep | None | Critical for cache stability |
| Token budget allocation across sections | Medium | Low | Simple: cap history at N turns, cache hits handle the rest |
| ChromaDB for vector memory (in progress) | High | Medium | Natural evolution from JSON-only |
| Periodic consolidation pass | Medium | Medium | Every ~50 turns or OOC (out-of-context) trigger |
| Recency + importance scoring | Medium | Low | Add `last_accessed` and `access_count` fields to memory |
| Proactive memory pre-fetch on each turn | Low | Low | Search ChromaDB in parallel with the API call |
| Query expansion before memory search | Low | Low | Model-generated search terms from user message |
| Implicit user profile extraction | Future | High | Worth when memory store exceeds hundreds of entries |

---

## Sources

- Anthropic Prompt Caching docs: https://platform.claude.com/docs/en/build-with-claude/prompt-caching
- MemoriesDB (Ward, 2025): https://arxiv.org/html/2511.06179
- AutoMem: https://railway.com/deploy/automem-ai-memory-service
- MongoDB AI Memory: https://www.mongodb.com/company/blog/technical/build-ai-memory-systems-mongodb-atlas-aws-claude
- OmniMemory (dual-agent synthesis): https://pypi.org/project/omnimemory/
- Deterministic conflict resolution (arXiv 2606.01435): https://arxiv.org/abs/2606.01435
- Memory consolidation Colab pipeline: https://colab.research.google.com/github/NirDiamant/Agent_Memory_Techniques
- OntoMem: https://pypi.org/project/ontomem/0.1.4/
- Knowledge Conflicts Taxonomy (EMNLP 2024): https://aclanthology.org/2024.emnlp-main.486.pdf
- The River Algorithm: https://zenodo.org/records/18779778
- Adaptive Focus Memory (Cruz, 2025): https://arxiv.org/pdf/2511.12712
- mengram token budget engine: https://pypi.org/project/mengram/
- ctx-opt context middleware: https://www.npmjs.com/package/ctx-opt
- Vespa multi-phase ranking: https://blog.vespa.ai/eliminating-the-precision-latency-trade-off-in-large-scale-rag/
- DataStax reranker guide: https://preview.datastax.com/blog/two-stage-retrieval-enterprise-search-rerankers
- RGMem user profiling: https://arxiv.org/abs/2510.16392
- BUMP self-supervised profiles: https://arxiv.org/abs/2606.05336
- PERSONAMEM benchmark: https://arxiv.org/abs/2504.14225
- Mem0 memory decay: https://mem0.ai/blog/memory-decay-for-long-running-agents
- YourMemory (Ebbinghaus decay): https://github.com/sachitrafa/YourMemory
- "Intelligent Decay" (Xu, 2025): https://arxiv.org/abs/2509.25250
- UserGPT profile compression: https://arxiv.org/abs/2605.08766
