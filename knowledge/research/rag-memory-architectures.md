# RAG + Memory Architectures for Persistent AI Assistants

**Audience:** AI reader (future Claude instances working on JARVIS)
**Context:** JARVIS is a voice-driven desktop assistant using ChromaDB with all-MiniLM-L6-v2 embeddings. This doc extracts patterns, not code.

---

## 1. Chunking Strategies

### The core tradeoff: semantic coherence vs. predictability

Fixed-size chunking (256-1024 tokens, 10-20% overlap) is fast, deterministic, and fine for homogeneous prose. But it destroys semantic boundaries -- splitting sentences, tables, or code blocks mid-structure. Semantic chunking (embedding-similarity-based boundaries) preserves topic integrity at 3-15x the indexing cost.

**Key insight for JARVIS:** For a single-user voice assistant, the optimal approach is likely **document-type routing before chunking**. Knowledge files (markdown, manuals) benefit from semantic chunking. Conversation logs benefit from fixed or clause-level chunking. A single global chunker is the most common source of production RAG failures.

### Practical baseline

Start with 400-600 token chunks, 15% overlap, plus a cross-encoder reranker on retrieval. This beats naive embedding-only retrieval by significant margins without the complexity of semantic chunking.

### Emerging pattern: hierarchical (parent-child) chunking

Store small searchable chunks (128-256 tokens) for retrieval, but point to larger parent passages (512-2048 tokens) for generation context. This is becoming the de facto production pattern for long-document QA -- it balances retrieval precision with generation context quality.

---

## 2. Embedding Strategy

### all-MiniLM-L6-v2 is outdated

This model (384-dim, 512 token context, trained 2021) underperforms modern alternatives on MTEB/BEIR benchmarks. Its 512-token context window is a hard ceiling -- any document chunk larger than that is silently truncated.

### Drop-in replacements at the same dimension

- **BAAI/bge-small-en-v1.5** (384-dim, MIT license) -- same dimensionality, no re-indexing needed, better retrieval quality
- **nomic-embed-text-v1.5** (768-dim via Matryoshka, Apache 2.0, 8192 context) -- requires re-embedding but offers dramatically longer context and the ability to dynamically truncate dimensions
- **Qwen3-Embedding-0.6B** (768-dim, Apache 2.0, 32768 context) -- extreme context length for very long documents

### When to re-embed

Embeddings are not portable between models. Switching models requires a full re-index. This is costly but worth doing when: (a) retrieval quality is measurably lacking, (b) you need longer context windows than 512 tokens, or (c) you're hitting dimension limits in ChromaDB.

### Matryoshka embeddings: a strategic consideration

Matryoshka models (like nomic-embed-text-v1.5) encode the same vector at multiple dimensionalities. You can store at 768-dim but search at 384-dim, getting 4x speedup with minimal quality loss. This gives flexibility to tune speed/accuracy tradeoffs without re-embedding.

---

## 3. Hybrid Search (Keyword + Vector)

### When it's worth it

Hybrid search consistently outperforms single-mode retrieval by 10-15% on accuracy and 3-5x on recall, per multiple 2024-2025 studies. The improvement is largest when:

- **Users enter keywords, not full questions** (voice queries tend to be short phrases -- exactly the case where pure semantic search underperforms)
- **Technical/acronym-heavy content** (entity names, product codes, medical terms that vector search can dilute)
- **Accuracy requirements are high** (hybrid reduces context failure rates by up to 49%)

### When it's NOT worth it

- Your dataset is small enough that one method captures everything
- Extreme latency sensitivity (hybrid doubles retrieval time)
- Pure factual lookups where exact match suffices

### Recommended fusion approach

Reciprocal Rank Fusion (RRF) is the standard. Start with 70% semantic / 30% keyword weighting and tune based on domain. ChromaDB does not natively support hybrid search -- you would need to run a separate keyword index (e.g., SQLite FTS5 or a small BM25 index) and merge results.

**For JARVIS specifically:** Adding a lightweight BM25 index alongside ChromaDB would be relatively low-effort and would likely improve retrieval for short, keyword-style voice commands significantly.

---

## 4. Memory Hierarchy Patterns

### The three-tier model (convergent across implementations)

Every major memory system -- HAMR, MemGPT, LangMem, OpenClaw -- converges on three tiers:

| Tier | Content | Retention | Retrieval |
|---|---|---|---|
| **Short-term (working)** | Raw recent turns, last 5-50 exchanges | Session or bounded token budget | Always present in context |
| **Mid-term (summarized)** | Compressed narratives about tasks, topics, interactions | Days to weeks | Semantic search, triggered by similarity or event |
| **Long-term (archival)** | Distilled facts, user attributes, verified knowledge | Permanent (or until explicitly deleted) | Semantic search + recency weighting |

### Retrieval scoring function (the HAMR pattern)

```
score = alpha * similarity(query, chunk) + beta * recency(chunk, time) + gamma * importance(chunk)
```

Default weights: alpha=0.4, beta=0.3, gamma=0.3. This balances relevance, freshness, and significance. The recency term is typically an exponential decay function.

### The compaction pipeline pattern

All mature memory systems use a **background compaction pipeline**:

1. **Short-to-mid:** When a task completes or a topic boundary is detected, the LLM summarizes the raw turns into structured insights (domain, key, summary). Existing mid-term entries on the same topic get their relevance bumped rather than duplicated.

2. **Mid-to-long:** Periodic sweep finds entries below a relevance threshold. These are distilled to keyword-extracted blurbs and moved to archival storage. The compaction itself uses the same LLM -- not a separate summarizer.

### Key design rule: compression uses the SAME model

OpenClaw and MemGPT both demonstrate that the compression/compaction model should be the same agent, not a separate summarizer. This ensures the "voice" of memories matches the agent's identity and the summaries capture what the agent itself would consider relevant.

---

## 5. Summarization Pipelines

### What to summarize vs. what to keep raw

- **Raw (verbatim) keeps:** Decision-making conversations, instructions the user gave, configuration preferences, personal context the user shared
- **Summarize:** Routine chit-chat, failed tool calls, repeated clarifications, intermediate reasoning steps
- **Discard entirely:** Transient system errors, duplicate context, out-of-scope tangents

### Event triggers for summarization

Don't summarize continuously. Trigger compaction on:
- Topic shifts (detected via embedding distance or explicit cue)
- Task completion (tool call chain ends)
- Time gaps (15+ minutes of silence between turns)
- Token budget pressure (context approaching MAX_HISTORY_TURNS)

### Structured output format for memory entries

Instead of free-text summaries, structure memory entries as:

```json
{
  "domain": "email",
  "key": "boss-communication-preference",
  "summary": "Boss prefers bullet-point replies",
  "importance": 0.75,
  "last_accessed": "2026-06-11T14:30:00Z",
  "access_count": 12
}
```

Structured keys enable exact retrieval (overwrite/update a known fact) while summaries enable semantic retrieval.

---

## 6. What to Store vs. Discard

### High-value information to always store

- **User preferences and attributes** (name, language preference, recurring requests)
- **Task outcomes** (what worked, what failed, user corrections)
- **Personal context** (relationships, projects, schedules the user shared)
- **Decision records** (why a particular choice was made)
- **Configuration overrides** (anything the user explicitly customized)

### Low-value information to discard

- **Transient errors** (microphone noise, one-off command failures)
- **Routine acknowledgments** ("okay", "thanks", "good morning")
- **Duplicated context** (same information said differently across turns)
- **Out-of-scope tangents** (the user went off-topic and returned)

### The importance score heuristic

For each piece of information, ask:
1. Would the assistant's response quality degrade if this were missing?
2. Is this information likely to be referenced again (same session, next session, next week)?
3. Is this a confirmed fact from the user, or an inference?

Store only items that score "yes" on at least two of three.

---

## 7. LlamaIndex Patterns (applicable to any RAG)

### Auto-mode routing

Instead of a single retrieval strategy, classify each query into: chunk-level retrieval, document-level retrieval (via metadata), or direct content access. Lightweight routing -- the LLM or a small classifier chooses.

### Composite retrieval

For heterogeneous knowledge (conversation logs + documentation + personal info), maintain separate indices and route queries to the most relevant one. This prevents domain contamination (e.g., a coding question pulling from chat history instead of docs).

### Knowledge graph fusion

For multi-hop queries requiring cross-paragraph reasoning, a lightweight knowledge graph (extracting entity-relationship triples from stored content) significantly outperforms flat vector search. This is advanced but worth noting for when JARVIS needs to answer questions that require connecting facts across different documents.

---

## 8. LangChain Memory Patterns (conceptual)

### The four memory archetypes

1. **Buffer** -- last N raw exchanges (simple, bounded)
2. **Summary** -- LLM-compressed narrative of everything before the buffer
3. **Entity** -- structured facts about people, places, things (triple extraction)
4. **Vector-store** -- semantic retrieval over past conversation snippets

### The hybrid pattern (recommended)

Use **buffer for recency** + **summary for compression** + **vector-store for semantic recall**. The buffer handles the last ~5 turns, the summary captures everything before that in compact form, and the vector store provides long-range retrieval. This three-layer approach covers all temporal ranges efficiently.

---

## 9. Practical Recommendations for JARVIS

1. **Keep ChromaDB, improve retrieval:** Add a small BM25 index alongside it. Hybrid search will meaningfully improve voice query retrieval (short keyword-style utterances).

2. **Upgrade embeddings when feasible:** Switch from all-MiniLM-L6-v2 to bge-small-en-v1.5 (same dimension, drop-in replacement) or nomic-embed-text-v1.5 (longer context, Matryoshka flexibility). The 512-token ceiling of the current model is a genuine limitation for document chunks.

3. **Implement the three-tier memory hierarchy:** JARVIS already has working memory (history list) and a single-tier vector store (memory tool). Add a mid-term tier that periodically summarizes old history entries and stores them as structured memory objects in a second ChromaDB collection.

4. **Use importance + recency scoring in retrieval:** When querying memory, blend similarity with recency (exponential decay) and access frequency. This prevents old-but-irrelevant memories from polluting results.

5. **Trigger compaction on task completion:** Use tool call chain termination as the signal to summarize the preceding history into a structured memory entry. This piggybacks on JARVIS's existing multi-tool loop.

6. **Store structured, not free-text:** Store memory entries with domain, key, and importance fields. This allows both exact-key lookup and semantic search, and enables deduplication (update-in-place when the same key reappears).

7. **Discard aggressively:** Voice assistants generate enormous amounts of low-signal interaction. Implement a decay mechanism: entries not accessed in N sessions get compressed; entries not accessed in N*3 sessions get archived; entries not accessed in N*10 get deleted.
