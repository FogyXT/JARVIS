# Novelty Analysis — Standby Neuron Agents & Neurogenesis

**Date:** 2026-06-13
**Author:** Patrik Fogoš (FogyXT)
**Status:** Novel — no prior implementations found

---

## Method

Web search across 12 queries covering: standby/dormant AI agents, neurogenesis, zero-RAM sleep states, sparse activation, domain-specific wake triggers, disk-based agent persistence. Results analyzed across GitHub, ArXiv, Zenodo, Google AI blog, npm, PyPI.

---

## Key Findings

### 1. Standby Neuron Agents — NOVEL ✅

**Our concept:** Domain-specialized AI agents that sleep on disk (DEEP_SLEEP = JSON file, 0 RAM, 0 tokens), wake on trigger pattern matching + centroid similarity, and return to sleep after task.

**Closest prior art:**

| System | Similarity | Key Difference |
|--------|-----------|----------------|
| **Anthropic "Dreaming" (May 2026)** | Agents sleep between tasks, consolidate memories | Batch process, not neuron-like. No domain-specific wake triggers. No per-agent disk persistence. No 0-RAM DEEP_SLEEP. |
| **Google ADK pause/resume (May 2026)** | Zero compute while dormant | Workflow state machines, not memory agents. No trigger-based wake. No domain specialization. |
| **@cartisien/cogito (2026)** | Explicit wake/sleep API | Not memory-specialized. No domain routing. No trigger patterns. |
| **ZenBrain (April 2026)** | 7-layer memory with sleep consolidation | No agent spawning. No disk-based sleep. No domain-specific agents. Single monolithic system. |
| **MemForge (2025-2026)** | 10-phase sleep cycles | Procedural pipeline, not agent-based. No domain agents. No neurogenesis. |
| **dreamcontext RemSleep (2025-2026)** | Local-first sleep agent | Single agent, not multi-agent. No neuron analogy. No auto-spawning. |

**Conclusion:** No existing system combines (a) multiple domain-specialized agents, (b) disk-based DEEP_SLEEP with 0 RAM/tokens, (c) trigger-pattern-based wake conditions, and (d) consensus panel voting. **This appears to be a novel concept.**

### 2. Neurogenesis — NOVEL ✅

**Our concept:** Automatic spawning of new memory agents from semantic memory clusters. When a domain accumulates enough memories with distinct patterns, a new specialized agent is born. Inactive agents are automatically pruned.

**Closest prior art:**

| System | Similarity | Key Difference |
|--------|-----------|----------------|
| **Anthropic "Dreaming"** | Auto-discovers macro-patterns during sleep | No new agent creation. Patterns feed back into existing memory, not into new specialized agents. |
| **MemForge schema detection** | Detects new schemas during sleep cycle | Creates schema rules, not new agents. No spawning. No pruning. |
| **Dosidicus (neurogenesis sim)** | Hebbian learning + neurogenesis | Game simulation, not AI memory system. |
| **Werld (agentic life sim)** | Agent spawning from inception | Toy simulation, not practical memory system. |

**Conclusion:** No existing system automatically spawns new specialized AI memory agents from semantic clusters. **This appears to be a novel concept.**

### 3. 5-Tier Biologically-Inspired Architecture — Partially Novel ⚠️

The overall architecture is inspired by Complementary Learning Systems theory (hippocampus↔neocortex), which has prior art. However, the specific combination of:
- Ebbinghaus decay with mathematical thresholds
- Hybrid dense+BM25 semantic search
- Entity-extracting knowledge graph
- Sleep-like consolidation with LLM-powered merging
- Standby neuron agents + neurogenesis

...appears to be a **novel synthesis** not found in any single existing system.

---

## Potential Submission Angles

### Strongest (NOVEL):
1. **"Standby Neuron Agents: A Sparse-Activation Architecture for Memory Management in AI Systems"**
   - Zero-RAM disk-based sleep, trigger-pattern wake, consensus voting
   - Practical implementation with benchmarks

2. **"Neurogenesis: Automatic Agent Spawning from Semantic Memory Clusters"**
   - Tag-based + embedding-based domain detection
   - Self-pruning lifecycle management

### Strong (novel synthesis):
3. **"A 5-Tier Biologically-Inspired Memory Architecture for Persistent AI Assistants"**
   - Full implementation with all tiers operational
   - 320+ test coverage, production-ready

---

## Prior Art Risks (to be aware of)

- **Anthropic's "Dreaming" (May 2026)** — If they extend it toward agent spawning or domain-specialized sleep states, our novelty window narrows. **Recommendation: Submit soon.**
- **Google ADK** — Their pause/resume pattern is closest to DEEP_SLEEP. If they extend toward memory-specific agents, similar risk.
- **MemForge/ZenBrain** — Academic systems with similar neuroscience inspiration. Less commercial risk but could claim conceptual prior art.

---

## Action Items

1. ✅ LICENSE with patent notice added (AGPL-3.0 + IP clause)
2. ⬜ Submit to Anthropic with novelty claims clearly stated
3. ⬜ Consider ArXiv pre-print to establish public prior art date
4. ⬜ If Anthropic expresses interest, consult IP lawyer about provisional patent

---

**Overall Assessment:** The Standby Neuron Agent concept and Neurogenesis mechanism appear to be genuinely novel in the AI memory space as of June 2026. The timing is critical — with Anthropic's Dreaming feature and Google's ADK both shipping similar adjacent capabilities, the novelty window may be 3-6 months.
