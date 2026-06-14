# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Jarvis is a single-user, voice-driven desktop assistant for Windows. It listens via microphone, transcribes through Google Speech Recognition, dispatches to the Anthropic Claude API (`claude-sonnet-4-6`), and speaks responses back through Microsoft Edge neural TTS. The user is addressed as **Fogy**; runtime prompts and console output are bilingual (Slovak / English).

It is a modular project: `jarvis.py` is the entry point, `tools/` is a package of tool implementations.

## Running

```powershell
# .env must define ANTHROPIC_API_KEY
python jarvis.py
```

Dependencies (install with pip as needed): `anthropic`, `python-dotenv`, `speechrecognition`, `pygame`, `edge-tts`, `pyautogui`, `requests`, `beautifulsoup4`, plus a PyAudio backend for `speech_recognition`.

Runtime commands inside the loop:
- `text` → switch to keyboard input mode
- `hlas` / `voice` → switch back to microphone
- `koniec` / `exit` → shut down

## Architecture

### Main loop (`jarvis.py:main`)

Per turn: read user input (voice or text) → `process_with_claude(user_input, history)` → loop. `history` is a single list of messages reused across turns and capped to `MAX_HISTORY_TURNS * 2` entries so context can't grow unbounded.

### Startup flow (`async_main`)
1. Logging into `jarvis.log` starts.
2. Two daemon threads start: text reader (stdin) + voice listener (mic).
3. On the **first user input**, `memory("read")` is called and its content is prepended to the user message so Claude sees its stored context without an extra API round trip.
4. Voice listener emits a short beep (`winsound.Beep`) before recording.

### Claude turn (`process_with_claude`)

1. Appends user message to `history`.
2. Calls `client.messages.create` with:
   - `system` as a single text block carrying `cache_control: ephemeral` — this is the correct way to enable prompt caching.
   - `tools=AVAILABLE_TOOLS` where the last tool also carries `cache_control: ephemeral` so the tools section is cached alongside the system prompt.
3. Enters a **multi-tool loop**: if `stop_reason == "tool_use"`, every `tool_use` block in the assistant message is executed via `_execute_tool`, results are returned as a single `user` turn of `tool_result` blocks, and Claude is called again. Loop continues until `stop_reason != "tool_use"`.
4. Final text is parsed by `extract_text_and_speak`, which strips the `[SK]` / `[EN]` prefix the model is required to emit, updates the global `CURRENT_LANG` (thread-safe via `_lang_lock`), and routes to `speak()` with the matching TTS voice.

Token usage (input, output, cache reads, cache creation) is printed every Claude call.

### Tools (`tools/` package)

Tool schemas in `jarvis.py:AVAILABLE_TOOLS` and dispatch in `_execute_tool` are kept in lockstep. All tools are implemented in the `tools/` package:

| Tool (function → file) | Purpose |
|---|---|
| `control_browser` → `tools/browser.py` | Action sequence over `webbrowser` + `pyautogui`. Supports `open_url`, `wait`, `type`, `press`, `hotkey`, `click_at` (`value="x,y"`), `scroll`. Set `browser="opera"` on `open_url` to launch Opera via the installed executable (`_open_with_opera`), falling back to the default browser. |
| `instagram_dm` → `tools/instagram.py` | Pošle text + voliteľnú fotku (attachment_path) na Instagram DM cez automatizáciu prehliadača. |
| `file_manager` → `tools/file_manager.py` | Unified filesystem op: `read` / `write` / `append` / `create_folder` / `delete` / `list`. Creates parent dirs on write. Read output is truncated at 10k chars. |
| `execute_command` → `tools/system.py` | Runs a PowerShell command (`powershell -NoProfile -Command ...`) with a timeout. Returns truncated stdout/stderr + exit code. |
| `web_search` | Server-side Anthropic built-in search (handled by the API). Returns up to 10 results with citations and snippets. |
| `image_search` → `tools/image_search.py` | Bing Images search by description. Returns image URLs. |
| `search_and_download_image` → `tools/image_search.py` | Searches + downloads the first matching image. |
| `download_file` → `tools/downloader.py` | Stiahne súbor z URL na disk. |
| `take_screenshot` → `tools/browser.py` | Saves `screenshot.png`. Handled specially: image returned as base64 inside `tool_result.content` for Claude to analyse. |
| `memory` → `tools/memory.py` | Persistent key-value in `jarvis_memory.json`. Actions: `save`, `read`, `delete`. Auto-loaded at session start. |
| `call_developer_agent` → `tools/__init__.py` | Sub-agent that rewrites whole files. See below. |

### Self-modification (`call_developer_agent`)

When the model wants to change its own code, it calls `call_developer_agent(target_filename, task_description)`. Flow:

1. Reads current file contents.
2. Spawns a second Claude API call (`claude-sonnet-4-6`) with a strict system prompt: "return only the complete final source, no markdown fences, no commentary".
3. Strips any leading ```python fences just in case.
4. **Backs up** the existing file to `<filename>.bak` (via `shutil.copy2`) before overwriting.
5. Writes the new file.
6. If the target was `jarvis.py` or `tools/*`, calls `os.execv(sys.executable, [sys.executable] + sys.argv)` to hot-restart the whole process.

Only `.py`, `.md`, `.txt`, `.json` paths are accepted as a safety floor.

### Language flow

The model is instructed to detect Fogy's language and prefix every reply with `[SK]` or `[EN]`. `extract_text_and_speak` parses that tag, updates `CURRENT_LANG` (under `_lang_lock`), and the next `listen()` call uses `sk-SK` or `en-US` as the Google STT language code. There is no separate "set language" tool — the tag in the response is authoritative.

## Thread safety

- `CURRENT_LANG` is guarded by `_lang_lock` (`threading.Lock()`). Read in voice thread, written in executor thread from `extract_text_and_speak`.
- `_is_jarvis_speaking` is written in main thread (`speak()`) and read in voice thread. Single-writer with GIL protection is acceptable.
- `_input_mode` written in main async loop, read in voice thread. GIL-protected single-writer.
- `history` list is written+read only from the executor thread — no cross-thread access.

## Knowledge base

The `knowledge/` directory stores what the project learns over time. Every `.md` file inside it is auto-indexed into ChromaDB (`tools/rag_memory.py:_index_knowledge_files`) and becomes semantically searchable across sessions.

### Structure

| Directory | What belongs |
|---|---|
| `knowledge/architecture/` | Design patterns, component relationships, data flow decisions |
| `knowledge/bugs/` | Bugs found and fixed — symptoms, root cause, fix, prevention |
| `knowledge/decisions/` | Why we chose X over Y. Use `_TEMPLATE.md` as starting point. |
| `knowledge/research/` | Notes from studying other tools/frameworks — summaries, not raw dumps |

### When you should write to it

After any non-trivial task, ask yourself: *"Will this help future me (or a future Claude) working on this project?"* If yes, create or update the relevant file.

Examples of worth-storing discoveries:
- A bug whose root cause took >5 minutes to find → `knowledge/bugs/<slug>.md`
- A design choice between two approaches → `knowledge/decisions/<slug>.md`
- A pattern that repeats across the codebase → `knowledge/architecture/<slug>.md`
- What we learned from evaluating a tool/library → `knowledge/research/<slug>.md`

Do NOT store: temporary logs, trivial one-liner changes, generic Python knowledge, duplicates.

### Automatic knowledge workflow (DO THIS WITHOUT BEING ASKED)

**Before any non-trivial task:**
1. Search the knowledge base FIRST with: `python -c "import tools.rag_memory; tools.rag_memory._ensure_init(); print(tools.rag_memory.rag_search('your query'))"`
2. This is automatic. You do not wait for the user to say "search knowledge."
3. Apply what you find. If a previous bug fix, architecture decision, or research pattern is relevant, use it.

**After any significant discovery:**
1. Save it to `knowledge/` immediately — don't wait to be told
2. A bug fix that took more than one attempt, an architecture insight, a pattern that worked → write it
3. The file auto-indexes into ChromaDB. Next session, it's findable.

This is how the project gets smarter over time. The user should never need to say "save that" or "search knowledge."

## Change philosophy

**Preserve intent. Improve implementation.** Do not change what the system does simply because a different design looks nicer. Do not break working subsystems without clear technical benefit. Do not remove capabilities.

Before any change that alters behavior, describe:
- **Current behavior** — what the code does now
- **Proposed behavior** — what it will do after
- **Benefits** — why the change is worth it
- **Risks** — what could break

Prefer the smallest change that solves the problem. Prefer evolution over replacement.

## 5-Tier Memory System (MANDATORY — use proactively!)

JARVIS now has a **5-tier biologically-inspired memory system** (324 tests, all phases complete). You MUST use it — do NOT wait to be told.

**FIRST THING EVERY SESSION:** Load memory and search what we were doing:
```bash
python -c "from tools.rag_memory import rag_search; print(rag_search('recent work jarvis'))"
```

**BEFORE any non-trivial task:** Search memory for relevant past knowledge.
**AFTER any discovery/decision:** Store it immediately with `memory("save", key, value)`.
**EVERY ~30 min:** Run `consolidate_quick()` to apply decay and promotion.

**Tiers:**
| Tier | Module | Purpose |
|------|--------|---------|
| 1+2 Episodic | `tools.episodic_memory` | Working(64)+Episodic(256), Ebbinghaus decay, cosine search |
| 3 Semantic | `tools.rag_memory` | ChromaDB v2, all-mpnet-base-v2, hybrid dense+BM25 search |
| 4 Knowledge Graph | `tools.knowledge_graph` | spaCy NER, NetworkX+SQLite, multi-hop reasoning |
| 5 Cold Archive | `tools.cold_archive` | JSON filesystem, search, thaw, compact |
| — Consolidation | `tools.consolidation` | 7-stage pipeline (quick 60ms / full 4.5s with DeepSeek) |
| — Agents | `tools.memory_agents` | 3 domain agents (personal/tech/projects), 0 tokens idle |

**When to use (PREFER agents over raw calls):**
- **BEFORE any non-trivial task:** `route_and_act("query", action="retrieve")` — agents wake on relevance, search only their domain
- **AFTER significant discoveries:** `route_and_act("text", action="store", key=..., value=...)` — agents add domain enrichment + cross-agent messages
- **Quick lookup:** `memory("read", key=...)` — direct EpisodicBuffer hit, no agent overhead
- **Semantic search:** `rag_search("query")` — hybrid dense+BM25 across all ChromaDB
- **Periodically:** `consolidate_quick()` — decay, clustering, promotion (auto-scheduled every 5min)

**Integration:** `tools/memory.py` auto-routes through all tiers. `memory("save")` → Episodic + JSON + ChromaDB + KG. `memory("read")` → Episodic first, ChromaDB fallback, JSON last resort.

[[use-jarvis-memory]] [[ultimate-ai-memory-architecture]] [[standby-neuron-agents]]

## Sub-agent usage

Use sub-agents proactively when they save time or improve result quality. You decide which type and when — the user doesn't need to request them.

**Always use sub-agents for:**
- Broad codebase searches ("find everywhere X is used", "how are modules connected") → **Explore agent**
- Complex implementation planning before writing code → **Plan agent**
- Parallel independent tasks (e.g. one agent reads the old code, another researches best practices) → spawn both at once

**Consider sub-agents for:**
- Adversarial verification of your own findings ("did I miss a bug?")
- Code review of a diff while you continue other work
- Research that requires reading many files across the project

**Don't bother for:**
- Reading a single known file path
- Finding one specific function/class definition
- Tasks completable in under 3 trivial steps

Spawn independent agents in parallel (one message, multiple Agent tool calls). Prefer Explore over manual Grep/Glob sweeps when the search spans multiple directories or naming conventions.

## Things to know before editing

- The system prompt + tool schema are designed to be **prompt-cache stable**. Avoid embedding session-mutating data (memory contents, current language, timestamps) into `SYSTEM_PROMPT` — that would invalidate the cache every turn. Memory is auto-loaded via prepending to the first user message instead.
- `call_developer_agent` invokes `os.execv` from inside the running interpreter — anything in the parent process state (audio handles, microphone) is dropped. The new process starts fresh from `main()`.
- All file writes from `file_manager.write` overwrite without confirmation.
- `pyautogui` automation runs against the real desktop. Do not move the mouse / type while `control_browser` is executing a sequence.
- `take_screenshot` is special-cased in the turn loop: its `tool_result` content is a list with an `image` block, not a string. The other tools all return plain strings (truncated to 3000 chars before being sent back to the model).
- Web search is server-side (Anthropic built-in tool). `tools/web_search.py` (client-side) exists as a fallback but is not the default.
- Image search scrapes Bing Images. Results may vary; model should verify the URL works before sharing.
