# Self-Modifying AI Systems: Research Summary

> Compiled June 2026 for the JARVIS project -- a voice-driven Python assistant that rewrites its own code via a developer sub-agent (`call_developer_agent`) and hot-restarts with `os.execv`.

---

## AREA 1: Self-Modifying AI Systems

### Patterns for AI Agents That Edit Their Own Source Code

The field has matured significantly since 2024. The most influential framework is the **Darwin Godel Machine** (ICLR 2026), which maintains a population of coding agents, samples parents, creates self-modified offspring, evaluates them against coding benchmarks, and discards failures. This population-based, open-ended exploration achieved SWE-bench improvements from 20% to 50% by evolving prompts, tools, and workflows -- including the agent's own ability to further self-modify.

The **Godel Agent** (arXiv:2410.04444) takes a different tack: recursive self-modification via runtime memory introspection and dynamic code rewriting, without human priors. Its key insight is monkey-patching its own runtime logic while the agent is still running.

**RSIAI0** codifies the cycle as: Introspect -> Hypothesise -> Implement -> Sandbox Test -> Verify -> Restart. This is the closest published analogue to JARVIS's own approach.

The **god-agent** (169 lines) distills the pattern to essentials: one tool (bash), one loop. It writes Python mods into a watched directory and `exec()`s them into its global namespace every turn. Two reload points -- before each user turn and after every batch of tool calls.

### Safety Patterns

A clear hierarchy of safety depth has emerged:

| Depth | Mechanism | Example |
|-------|-----------|---------|
| 0 - Backup | Copy file before overwriting | JARVIS `.bak` pattern |
| 1 - Git isolation | Change on branch, reset to roll back | `ralph-codex`, `ait-vcs` |
| 2 - Savepoint | Atomic checkpoint per write, surgical rollback | `detent` (Python package), `agent-undo` |
| 3 - Verifier gates | Syntax -> lint -> typecheck -> test -> security pipeline | `Detent`, `MartinLoop` |
| 4 - Contract enforcement | Frozen holdout tests that spec compliance | `@baton-tools/harness` |

The **Hydra** system (arXiv:2605.15238) showed that asynchronous checking alongside generation reduces latency by 71% and token consumption by 70% versus post-hoc repair. **Stream of Revision** (arXiv:2602.01187) pushes further: self-correction within a single forward pass via revision-trigger tokens, requiring no external dependencies.

**`agent-undo`** is a particularly elegant tool: a filesystem watcher that snapshots every file write with BLAKE3 hashes, stores them in a content-addressable store plus SQLite timeline, and enables one-command rollback (`au oops`) with per-line agent attribution (`au blame`). It treats the agent as inherently untrusted.

### Hot-Reload Patterns

Three main approaches exist:

1. **`os.execv` (JARVIS's approach)** -- Hard restart of the Python process. Simple, clean state, but drops all handles (audio, microphone, network). The RSIAI0 framework uses the same pattern after verification.

2. **`importlib.reload`** -- Module-level hot reload without losing process state. Used by the god-agent via `exec()`. More surgical but risks stale references and partial state.

3. **Process supervision** -- A watchdog that restarts the child agent on file changes. Used by `MartinLoop` and production coding agents. Most robust but most complex.

### How Other AI Coding Tools Handle File Modifications

**Aider** implements a Strategy pattern with five edit formats:
- SEARCH/REPLACE blocks (EditBlockCoder) for targeted edits
- Whole-file rewrites (WholeFileCoder) for major changes
- Unified diffs (UnifiedDiffCoder) for git-style patches
- V4A diffs (PatchCoder) with 3-line context
- Tool-calling JSON (SingleWholeFileFunctionCoder) for structured models

Each strategy shares a three-method interface: `get_edits()`, `apply_edits()`, `render_incremental_response()`. Failed matches raise ValueError with diagnostics sent back to the LLM for self-correction.

**Cursor** takes a radically different approach: full-file rewriting via a specialised fast-apply model (fine-tuned Llama-3-70b running at ~1000 tokens/second). Their reasoning is that models have seen more complete files than diffs in training, and extra output tokens give more forward passes to determine correctness. The speed breakthrough is **speculative edits**: since most output matches the existing code, matching chunks are fed back as accepted tokens and processed in parallel; only points of disagreement generate new tokens (4-5x speedup).

**Claude Code** enforces a strict read-before-edit discipline with three tiers: Edit (single string replacement), MultiEdit (multiple atomic replacements with rollback on any failure), and Write (complete overwrite, only when >50% of file changes). Edit requires byte-for-byte exact matching of old_string. MultiEdit rolls back all edits if any single one fails. This atomicity guarantee is a strong safety property.

### Key Takeaway for JARVIS

JARVIS's current pattern -- `call_developer_agent` reads file, spawns sub-agent, backs up to `.bak`, writes new file, hot-restarts with `os.execv` -- is sound but could benefit from:

- A `Savepoint` abstraction before each write (beyond simple `.bak`)
- A verifier gate run on the model's output *before* writing (syntax check at minimum)
- Tracking write provenance (which Claude call produced which file state)

---

## AREA 2: Developer Agents / Sub-Agents for Code Generation

### Architect/Editor Split

This is Aider's most impactful architectural contribution. A **strong reasoner** (e.g., o1-preview, Claude Sonnet) analyses the problem and describes *what* to change. A **cheaper editor model** (e.g., DeepSeek, o1-mini) converts the description into properly formatted file edits. This dual-model approach achieved 85% SOTA on SWE-bench.

The separation prevents two failure modes: the reasoning model getting distracted by formatting details, and the editing model having to reason beyond its capability. The architect never touches code; the editor never solves design problems.

### Adversarial Review (Generator + Critic)

Multiple projects implement an actor-critic loop where one AI writes code and another (or several others) critique it:

- **Comfy Internals** fans a PR diff out to four models from four different AI labs (OpenAI, Anthropic, Google, Moonshot), two passes each (adversarial + edge-case), then a single judge model consolidates findings. The key insight: four models from one lab function as one opinion; cross-lab diversity catches fundamentally different bug classes.

- **Google's Jules** embeds a critic model that reviews every proposed change *before* the user sees it. The critic does not fix code -- it flags issues and hands back to the generator. This follows the actor-critic RL pattern.

- **grill-me-codex** runs an adversarial debate where a second model (Codex) tears apart Claude's plan until both models sign off, bounded by a round limit.

- **CodexLoop** structures the cycle as six steps per iteration: Evaluate -> Suggest -> Rank -> Apply -> Validate -> Record. A judge call ranks proposals on six dimensions (correctness, requirement satisfaction, simplicity, maintainability, risk, testability).

### Iterative Refinement (Generate -> Test -> Fix -> Repeat)

This is the most widespread pattern. **GPT Engineer** and **MemoCoder** both implement it:

1. Generate code
2. Run tests
3. Categorise failure (compile error, runtime exception, assertion failure, timeout)
4. Feed failure details to the model
5. Repeat until passing or budget exhausted

MemoCoder adds a **Fixing Knowledge Set** -- a memory module storing successful repairs for future retrieval. The correctness pipeline pattern also includes **regression protection**: revert if previously passing tests break due to a new fix.

### Constraining Code Generation

Three layers of constraint have emerged:

1. **Strict prompting** -- "Return only the complete final source, no markdown fences, no commentary" (JARVIS's approach). Effective but fragile against model updates.

2. **Schema validation** -- Tool-calling interfaces (Anthropic's tool use, OpenAI's function calling) enforce structure at the API level. Cursor and Aider both use this.

3. **Lint gates** -- Post-generation checks that reject code failing syntax/lint/typecheck. Detent runs this as a composable verification pipeline before any write touches disk.

### Key Takeaway for JARVIS

JARVIS's `call_developer_agent` is a single-model pattern. Adding an adversarial review step -- even a lightweight one -- before writing would catch many errors. The simplest version: have the sub-agent critique its own output before finalising, or run a syntax check on the generated code as a minimal gate.

---

## AREA 3: Project Evolution Patterns

### Evolving a Codebase Safely With AI Assistance

The **Spec-Kit Clean Architecture** approach treats code generation like a planning problem: first create a YAML execution plan, then execute it step by step, each step producing an atomic git commit with validation checkpoints. Progressive rollback lets you undo specific steps without losing everything.

**`ralph-codex`** enforces immutability of product specs (read-only to the agent), fresh context on every iteration (prevents assumption drift), and git-backed rollback on branches. Tests decide reality, not the agent.

The consistent finding across projects: **specs should be append-only**. An agent can add new observations but should never edit or delete past knowledge. This prevents "prompt rot" where the agent's own modifications degrade its understanding over successive sessions.

### Regression Testing for AI-Modified Code

A 2024 study in *Automated Software Engineering* identified a critical gap: user feedback in AI code generation tools is transient and does not persist across sessions. Even when a user corrects generated code in session 1, the model returns the original uncorrected code in session 2.

Solutions include:

- **Code provenance tracking** -- Decompose code translation into sub-problems where each snippet is traceable to the query that produced it.
- **Supplemental memory components** -- k-Nearest Neighbours data stores that accumulate and retrieve correction information across sessions without retraining.
- **Frozen holdout tests** -- Tests that never change, enforcing spec compliance across all iterations. If a new fix breaks a holdout, it's rejected.

### Knowledge Transfer Between Sessions

What should persist? The research suggests these categories:

| What to persist | Why | How |
|----------------|-----|-----|
| Recurring error patterns | Avoid repeating same fixes | Fixing Knowledge Set (MemoCoder) |
| Session metadata (counts, durations, error signatures) | Identify behavioural drift | pi-evolver's personality vector |
| Recurring solutions (3+ occurrences) | Codify as reusable skill | Agent Evolver's `extract-pattern` |
| Important past corrections | Prevent regressions | k-NN correction data store |
| What NOT to do | Block known dead ends | Append-only learnings file |

**pi-evolver** is the most conservative approach: records only metadata (counts, durations, hashed error signatures) -- never prompts or code content. A personality vector of 5 bounded floats (rigor, creativity, verbosity, risk_tolerance, obedience) drifts based on session outcomes. What gets *promoted* to actual skills requires manual approval.

### Managing AI-Authored Changes in Version Control

Several tools and patterns address the uniqueness of AI-authored changes:

- **`ait-vcs`** isolates AI agent work in separate Git worktrees with attempt provenance (linking prompts, commands, files, and commits). Attempts are promoted or discarded before touching main.

- **`claw-vcs`** tracks *why* changes were made via structured "intent" objects, stores signed "capsules" with agent provenance claims, and enforces policies as versioned repository objects.

- **`tin`** treats conversation threads as the primary unit of change -- every commit is permanently linked to the AI prompt/response that produced it.

- **`git-sentinel`** converts Git history into structured, queryable intelligence for coding LLMs: conventions, pitfalls, decisions, hot files, co-change patterns. Exposes MCP tools plus a feedback loop for self-improving confidence scores.

### Key Takeaway for JARVIS

JARVIS currently has no cross-session memory apart from the explicit `memory` tool (which stores key-value pairs in `jarvis_memory.json`). Adding session-level recording of:

- Which files were modified in which session
- What the modification intent was
- Whether it succeeded or was rolled back

...would enable the agent to learn from its own history. The `memory` tool is already the right primitive; extending it with structured change records is a natural next step. Additionally, adopting git worktree isolation for `call_developer_agent` modifications would provide zero-cost rollback without needing a custom backup system.

---

## Summary of Recommendations for JARVIS

1. **Add a verifier gate** -- Run `py_compile` on generated code before writing; reject if syntax errors exist.
2. **Replace `.bak` with git isolation** -- Branch before modification, commit the safe state, reset branch on failure.
3. **Add write provenance** -- Log which file was modified by which sub-agent call, so the agent can inspect its own history.
4. **Consider an adversarial review step** -- Even a lightweight self-critique pass before file write would catch many issues.
5. **Persist session metadata** -- Track which modifications succeeded or failed across restarts, so the agent learns from past mistakes.
6. **Hard iteration limits** -- Prevent sub-agent infinite loops by capping rounds, tokens, or wall time.
