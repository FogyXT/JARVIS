# JARVIS Knowledge Base

Structured project memory. All `.md` files here are auto-indexed into ChromaDB for semantic search.

## Structure

| Directory | What goes here |
|-----------|---------------|
| `architecture/` | Design patterns, component relationships, data flow, thread safety decisions |
| `bugs/` | Bugs encountered, root cause, fix applied, date fixed |
| `decisions/` | Why we chose X over Y. Use `_TEMPLATE.md` for new entries. |
| `research/` | Research on other tools, frameworks, patterns — summaries, not raw dumps |

## Conventions

- One topic per file
- File name = kebab-case slug (`why-chromadb.md`, `microphone-thread-crash.md`)
- Start with context (what was the situation), then decision/outcome
- Write for future AI retrieval — be searchable, be specific
- Link related files with `[filename.md]` when relevant

## How it's indexed

On first RAG call, `tools/rag_memory.py` scans `knowledge/**/*.md` files and upserts them into the ChromaDB collection alongside `jarvis_memory.json` entries. The `knowledge:` prefix in the doc ID keeps them separate from user facts.
