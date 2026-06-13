# Standby Neuron Agents — Novel Concept for AI Memory Management

**Date:** 2026-06-13
**Status:** Concept phase — not yet implemented anywhere
**Related:** [[ultimate-ai-memory-architecture]] [[five-tier-memory-for-jarvis]]

---

## The Core Idea

Use multiple specialized LLM agents as "standby neurons" that manage different domains of AI memory, waking only when their domain is relevant, communicating sparsely (event-driven), and consuming **zero tokens when idle** — exactly like biological neurons that fire sparsely.

## Origin

Concept by Fogy (2026-06-13), inspired by:
- Biological sparse activation (~86B neurons, few % active at any moment)
- CortexGraph's 5-agent pipeline (which uses deterministic rules, not AI)
- The observation that no existing system uses actual LLM agents for memory consolidation

## How It Works

### Architecture

```
┌─────────────────────────────────────────────┐
│              Memory Router                   │
│   (lightweight, always-on classifier)        │
│   Decides which domain agents to wake        │
└──────────┬──────────┬──────────┬────────────┘
           │          │          │
     ┌─────▼──┐  ┌────▼───┐  ┌──▼──────┐
     │Personal│  │ Tech   │  │ Projects│  ... N domains
     │ Agent  │  │ Agent  │  │ Agent   │
     │ (idle) │  │ (idle) │  │ (idle)  │
     └────────┘  └────────┘  └─────────┘
```

### States

| State | Token Consumption | Description |
|-------|------------------|-------------|
| **IDLE** | 0 | Agent exists as a prompt + configuration, not running |
| **WOKEN** | trigger cost (~100-200 tokens) | Router decides this domain is relevant, agent loads |
| **ACTIVE** | task cost (~500-2000 tokens) | Agent retrieves/manages/consolidates memories |
| **COMMUNICATING** | inter-agent cost (~200-500 tokens) | Two agents share relevant memories across domains |
| **CONSOLIDATING** | batch cost (~1000-5000 tokens) | Agent runs sleep-like replay/reorganization during system idle |

### Wake Triggers

An agent wakes when:
1. **New memory in its domain** — user creates a memory about "Python bug" → Tech Agent wakes
2. **Cross-domain reference detected** — new memory mentions both "health app" and "Python" → Health Agent + Tech Agent wake
3. **Consolidation cycle** — system idle for N minutes → all agents run lightweight consolidation
4. **Query relevance** — user asks about "my car" → Personal Agent wakes to retrieve

### Inter-Agent Communication (Sparse)

Agents communicate ONLY when:
- A memory spans multiple domains (e.g., "using Python for health tracking")
- Consolidation finds duplicate/similar memories across domains
- One agent needs context from another domain to understand a memory

Communication is **message-passing via a shared blackboard**, not direct agent-to-agent calls. This keeps coupling minimal.

### The Sleep Analog

During system idle (no user interaction for N minutes):
1. Router triggers "sleep cycle"
2. Each domain agent replays recent memories, strengthens important ones, weakens stale ones
3. Cross-domain consolidation: agents share overlapping memories
4. Knowledge graph is updated with new relations
5. Cold archive is compacted

## Why This Is Novel

| Existing Systems | Standby Neuron Agents |
|-----------------|----------------------|
| CortexGraph: deterministic Python "agents" | Actual LLM-powered reasoning per domain |
| Always-on pipelines that run on timers | Event-driven, wake on relevance only |
| Monolithic memory (one store for everything) | Domain-separated with sparse cross-talk |
| No inter-agent communication | Blackboard-based sparse communication |
| Always consuming resources | Zero tokens when idle (only prompt definition stored) |

## Implementation Path

1. Start with 2-3 domain agents (Personal, Technical, Projects)
2. Lightweight router using keyword + embedding similarity to decide which agents to wake
3. Each agent has: system prompt defining its domain, access to relevant memory partitions
4. Consolidation runs as background async task during idle
5. Measure: token savings vs monolithic approach, memory retrieval quality

## Potential Impact

If successful, this could:
- Reduce memory retrieval costs by 60-80% (only wake relevant agents)
- Improve retrieval quality (domain-specialized agents know their domain better)
- Enable memory to scale to millions of items (each agent manages a fraction)
- Provide a publishable novel architecture for AI memory management

## Connection to Alzheimer's Research

The sparse-activation, domain-separated architecture mirrors how the brain organizes memories across cortical regions. If we can build this for AI, it provides a computational model for how memory prosthesis could work:

- Different implant regions for different memory types (episodic, semantic, procedural)
- Sparse activation to minimize energy consumption
- Consolidation during sleep for memory strengthening
- Fallback routing when one region fails (like the brain's plasticity after damage)
