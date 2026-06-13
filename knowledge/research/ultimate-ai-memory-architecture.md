# Ultimate AI Memory Architecture — Deep Research

**Date:** 2026-06-13
**Status:** Research complete, moving to implementation
**Related:** [[standby-neuron-agents]] [[five-tier-memory-for-jarvis]]

---

## Source Quality

- **24 sources fetched**, 120 claims extracted, 25 verified (14 confirmed, 11 killed)
- **106 research agents** used across 5 angles
- Sources include: bioRxiv preprints, arXiv papers, GitHub repos (CortexGraph, Cognitive Memory, GraphRAG), Anthropic official docs, Qdrant tech blog

---

## 1. Biological Foundation (HIGH CONFIDENCE)

### Complementary Learning Systems (CLS) Theory

Three converging 2025-2026 studies validate the hippocampus↔neocortex split as an architectural template for AI memory:

**Zhou & Schapiro (bioRxiv 2025, CCN 2024):** When ANNs meta-learn layer-wise plasticity and sparsity, higher layers spontaneously develop faster plasticity and sparser representations — mirroring the biological gradient. This organization emerges from optimization, NOT explicit engineering. Lower layers peak in plasticity early and stabilize; higher layers remain plastic longer (matching primate developmental data).

**Fontaine & Alexandre (IJCNN 2025, arXiv:2509.01987):** Predictive coding neocortical model shows dense overlapping representations can encode individual examples gradually, but only in limited numbers. This **capacity constraint** directly motivates a separate hippocampus-like episodic buffer with sparse, pattern-separated representations.

**McNaughton, Bazhenov et al. (bioRxiv 2025, PMID:40667278):** During slow-wave sleep, the brain interleaves novel (hippocampal) and familiar (cortical) memory traces within individual slow waves. Novel traces replay near Down-to-Up and Up-to-Down transitions; familiar traces in the middle of the Up state. This is a **biological blueprint for consolidation scheduling**.

### Key Architectural Insight

The five-tier model maps directly to validated neuroscience:

| AI Tier | Brain Analog | Mechanism |
|----------|-------------|-----------|
| Working memory | Prefrontal cortex | Active processing, attention-gated |
| Episodic buffer | Hippocampus | Fast learning, sparse pattern-separated |
| Semantic store | Neocortex | Slow consolidation, dense overlapping |
| Knowledge graph | Association cortex | Relational binding, multi-hop |
| Cold archive | Distributed cortex | Full fidelity, slow retrieval |

---

## 2. Existing Implementations

### CortexGraph (prefrontal-systems, v1.2.1, Jan 2026)

```
score(t) = (n_use)^beta × exp(-lambda × delta_t) × strength
```

- **3 decay models:** power-law (default, most human-like), exponential, two-component
- **Forget threshold:** 0.05 (below = deleted)
- **Promote threshold:** 0.65 OR 5+ accesses within 14 days
- **5-agent consolidation pipeline:** DecayAnalyzer, ClusterDetector, SemanticMerge, LTMPromoter, RelationshipDiscovery
- **Critical caveat:** These "agents" are deterministic Python classes — ZERO LLM calls

### Cognitive Memory (petertilsen, PyPI 0.5.1)

```
relevance = relevance × exp(-decay_rate × time_diff)
```

- 3-tier hierarchy: working buffer (64 items) → episodic buffer (256 items) → ChromaDB (∞)
- Access-based reinforcement on read
- numpy-based cosine similarity for buffer search (sub-ms)

### GraphRAG (Microsoft, v3.1.0 — May 2026)

- Entity extraction → Leiden community detection → hierarchical summaries
- Enables multi-hop reasoning and global summarization
- Trade-offs: $0.12-0.18/doc (60-90× vector-only), 2.3× latency, worse on single-hop

### EcphoryRAG (Tsinghua, arXiv:2510.08958, Oct 2025)

- Stores only core entities + metadata during indexing
- Dynamically infers implicit relations at retrieval time
- **94% token reduction** vs LightRAG (2M vs 36.4M indexing tokens)
- Exact Match improvement: 0.392 → 0.474 over HippoRAG

### D-MEM (arXiv:2603.14597, March 2026)

- Critic Router + selective memory evolution
- **80% token reduction** (319K vs 1.64M) under 75% noise
- Actually **outperforms** sync baseline A-MEM on multi-hop F1 (0.412 vs 0.365)
- Breaks the assumed efficiency-accuracy trade-off

### Claude Managed Agents (Anthropic, April 2026)

- Filesystem-mounted memory at `/mnt/memory/{store-name}/`
- Optimistic concurrency via `content_sha256` preconditions
- Immutable versioning (`memver_...` IDs) with full audit trail
- Shareable across agents (org-wide read-only, per-user read-write)
- **Gap:** Agents use file tools, not API directly — concurrent writes without preconditions = last-write-wins

---

## 3. Production Vector DB & Hybrid Search

### Key Technologies

- **TurboQuant (Qdrant):** 16× compression, codebook from standard normal distribution
- **miniCOIL:** Self-supervised per-word training, beats BM25 on 4/5 BEIR datasets, 200× smaller than embeddings
- **Binary Quantization:** 32× compression but quality loss; TurboQuant is superior at same budget
- **Hybrid search (dense + sparse):** Now standard; miniCOIL as sparse component + dense embeddings = strongest combo

### Latency Budget (Target)

| Tier | Target Latency | Storage |
|------|---------------|---------|
| Working memory | instant (cache hit) | API prompt cache |
| Episodic buffer | sub-ms | numpy arrays in RAM |
| Semantic store | 5-50ms | Qdrant/ChromaDB |
| Knowledge graph | 100-500ms | Neo4j/FalkorDB |
| Cold archive | async/batch | Filesystem/object storage |

---

## 4. Key Gaps (What Nobody Has Solved)

1. **Consolidation scheduling for AI that never sleeps** — biological sleep is regulated by circadian rhythms and adenosine. What's the computational equivalent? Time-based? Event-count-based? Idle-detection?

2. **Timescale invariance of replay** — biological replay happens in 200-500ms oscillations. LLM consolidation is orders of magnitude slower. Does temporal precision matter, or is functional interleaving sufficient?

3. **Optimal forgetting curve for AI** — humans follow power-law (Wixted 1991). AI has bursty usage, task-driven access, artificial rehearsal. No empirical study has derived the correct decay function for agentic AI memory.

4. **LLM-powered consolidation agents** — CortexGraph has 5 deterministic agents. No existing system uses actual AI agents for memory consolidation. This is the gap our "standby neuron agents" fill.

5. **Multi-agent memory with zero idle token consumption** — Claude Managed Agents mount memory stores, but agents are always-on. The sparse-activation pattern (agents wake only on relevant triggers) is unimplemented anywhere.

---

## 5. Refuted Claims

These claims failed 3-vote adversarial verification:

- ❌ Hippocampal index signals cannot simply be applied to cortical slow oscillations
- ❌ Temporal sleep segregation doesn't directly map to catastrophic forgetting prevention in ANNs
- ❌ Predictive coding neocortex CANNOT do episodic recall on many examples (capacity limits confirmed)
- ❌ Cognitive Memory 15-40% reuse rate and 25× speed claims — not replicable
- ❌ EcphoryRAG "state-of-the-art on multi-hop QA" — benchmark-specific, doesn't generalize
- ❌ TurboQuant "no per-dataset training needed" — codebook still needs to match distribution

---

## 6. Most Promising Papers

| Paper | Key Insight | URL |
|-------|------------|-----|
| Zhou & Schapiro 2025 | Meta-learned CLS gradients | https://www.biorxiv.org/content/10.1101/2025.07.10.664201v1.full |
| Fontaine & Alexandre 2025 | Predictive coding capacity limits | https://web3.arxiv.org/abs/2509.01987 |
| McNaughton et al. 2025 | Sleep replay interleaving | https://www.biorxiv.org/content/biorxiv/early/2025/08/19/2025.06.25.661579.source.xml |
| EcphoryRAG (Liao 2025) | Dynamic relation inference | https://arxiv.org/abs/2510.08958 |
| D-MEM (2026) | Selective memory evolution | https://huggingface.co/papers/2603.14597 |
| CortexGraph | Forgetting curves in practice | https://github.com/prefrontal-systems/cortexgraph |
| Anthropic Managed Agents | Multi-agent memory stores | https://claude.com/de/blog/claude-managed-agents-memory |

---

## 7. From Research to Implementation

The next step is [[five-tier-memory-for-jarvis]] — a concrete implementation plan for JARVIS.

The most novel contribution is [[standby-neuron-agents]] — LLM agents that wake on demand, manage memory domains, communicate sparsely, and consume zero tokens when idle.
