# Agent / Coding System Design Patterns

A research summary of patterns from OpenHands, Aider, LangGraph, and AutoGPT, distilled for a solo-developer AI assistant project (JARVIS). Focus is on concepts and architectural decisions, not implementation details.

---

## 1. OpenHands -- Event-Driven Agent with Stateless Steps

### Agent Loop
OpenHands V1 uses a single-step execution model: each `step()` call is one full reasoning cycle. The agent is **stateless between steps** -- it holds no mutable state, only reads from an event history and writes new events. This makes every step atomic, interruptible, and resumable.

### Planning Pattern
The agent does not pre-plan. Instead, it runs a **reasoning-action loop**: LLM query -> response parsing -> tool execution -> observation -> repeat. Each step is self-contained; the LLM decides the next action based on the accumulated event stream.

### Execution Pattern
Tools are called through a **three-layer abstraction**: LLM emits a JSON action -> a ToolExecutor interprets it -> structured Observation events return to the agent. All tools share a uniform interface. High-risk actions can be configured with human-in-the-loop confirmation gates.

### Self-Correction Pattern
OpenHands relies on **iteration limits and threshold-based termination** rather than explicit self-reflection. A newer pattern (Operon Stagnation Critic) uses Bayesian analysis over conversation history to detect when the agent is cycling without progress, replacing LLM-judged success scores with structural signals.

### Memory Pattern
Uses **event sourcing** -- all interactions are persisted as an immutable event log. This enables replay, state restoration, and incremental persistence. Context is managed via condensation: an `LLMSummarizingCondenser` compresses old history to prevent overflow, at roughly 2x cost reduction.

### Failure Handling
- **Stagnation detection**: structural analysis detects cycling
- **Human-in-the-loop**: configurable confirmation for risky actions
- **Sandboxing**: Docker or local isolation to contain execution failures
- **Resumability**: event-sourced state means crashes lose at most one step

### Key Takeaway for JARVIS
Stateless step design is powerful for reliability, but overkill for a single-user voice assistant. The event-sourcing pattern for conversation history is valuable -- an immutable log of every turn + tool result would make debugging and replay possible. The condensation pattern (compress old context) is directly applicable to JARVIS's history cap.

---

## 2. Aider -- Plan-Separate, Edit-Then-Verify

### Agent Loop
Aider's `Coder` class is a central orchestrator managing: message history, file tracking, model communication, edit processing, git operations, linting, and reflection. The flow per turn: user input -> assemble context (RepoMap + file contents) -> send to LLM -> parse response via edit format -> apply edits -> lint -> reflect -> commit.

### Planning Pattern
Aider's most impactful pattern is the **Architect/Editor split**: one model (the Architect) reasons about the solution in natural language, and a second model (the Editor) translates that solution into formatted code edits. This separation achieves state-of-the-art results (85% pass rate) because it lets each model focus on its strength -- reasoning or formatting. Even the same model used for both roles outperforms the monolithic approach.

### Execution Pattern
Code edits use a **pluggable `edit_format`** system: the LLM response is parsed according to the format (search-and-replace blocks, whole-file rewrites, diffs), and the corresponding Coder subclass applies the physical file changes. This decouples how the LLM expresses edits from how they're applied.

### Self-Correction Pattern
A **linting-and-reflection loop** runs after every edit: lint/tests are run on the changed code, errors are fed back to the LLM as a new message, and the model self-corrects. A configurable `max_reflections` cap prevents infinite loops. This is a pure error-feedback loop -- no meta-cognition, no external critic model.

### Memory Pattern
**Two-tier message history**: `cur_messages` (current turn) and `done_messages` (past turns). The **RepoMap** is a PageRank-based context generator that selects relevant files from the repository to include in the LLM context -- not full file contents, just the code structure that's relevant to the current task.

### Failure Handling
- **SwitchCoder exception**: commands like `/model` force a clean Coder re-creation, handled at the main-loop level
- **Retry on API failure**: integrated into `send_completion()`
- **Git safety**: every change is auto-committed with author attribution, making rollback trivial
- **Lint gate**: blocking errors prevent the edit from being accepted

### Key Takeaway for JARVIS
The Architect/Editor pattern is the most transferable insight: split reasoning from formatting/execution. For JARVIS, this could mean using the main Claude call for reasoning, and a cheaper model or structured output parser for the mechanical parts (tool call generation, text formatting). The edit_format abstraction is also valuable: decouple what the LLM says from how it's applied. The linting-reflection loop is directly applicable to JARVIS's `call_developer_agent` self-modification flow.

---

## 3. LangGraph -- Directed Graph Orchestration

### Agent Loop
LangGraph structures workflows as **directed state graphs (StateGraph)** with three primitives: **State** (shared memory with typed reducers), **Nodes** (units of computation -- LLM calls, tools, human checkpoints), and **Edges** (connections -- linear, conditional, or cyclical). The graph executes by traversing nodes along edges until a terminal condition is met.

### Planning Pattern
LangGraph codifies several planning archetypes:
- **Planner-Executor Loop**: a planner node decides the next action, an executor performs it, repeat. This is the generic ReAct pattern.
- **Plan-then-Execute**: generate a full plan upfront, then follow it sequentially. Extensions include re-planning on failure, DAG-based parallel execution, and hierarchical planning (sub-planners for subtasks).
- **Router pattern**: a node examines state and routes to the appropriate downstream node based on intent/classification.

### Execution Pattern
Nodes are **pure functions** accepting State and returning State updates. Conditional edges are **pure Python functions** reading typed state -- making execution deterministic and replayable. The **Send API** enables dynamic parallel forking: when the number of subtasks is unknown upfront, you can launch workers in parallel and gather results via state reducers.

### Self-Correction Pattern
The **Evaluator-Optimizer loop** is the canonical pattern: one node generates, another evaluates, loop until evaluation passes. This supports both automated (LLM-as-judge) and human-in-the-loop critique. The **Reflection pattern** extends this to self-correcting agents that evaluate and improve their own outputs iteratively.

### Memory Pattern
**Typed, versioned state** with annotated reducers. Each state field has clear ownership (which nodes write to it). Operational fields like `errors`, `credits_spent`, and `cursor` are included for production observability. **Checkpointing** (in-memory, SQLite, or Postgres) enables time-travel debugging, multi-turn conversations, and pause/resume.

### Failure Handling
- **Cyclic graphs** naturally support retries and re-execution
- **Circuit breaker pattern**: fault tolerance via state-machine gates
- **Human-in-the-loop pauses**: graphs can pause at checkpoints for human review before continuing
- **Observability**: each node gets its own log line, latency histogram, and unit test
- Token bloat management: cycles and retries can accumulate state; modular node design contains the blast radius

### Key Takeaway for JARVIS
LangGraph's core insight is that agent behavior is a **graph, not a loop**. JARVIS's current architecture is a simple linear loop (input -> Claude -> tools -> output). Explicitly modeling the flow as a graph would make it easier to add branching (e.g., "if this tool result indicates failure, go to a repair sub-graph") and parallelism (e.g., run web search and file read simultaneously). The typed-state-with-reducers pattern is directly applicable to JARVIS's `history` list -- using structured message types with merge semantics would make the code cleaner.

---

## 4. AutoGPT -- Autonomous Goal-Driven Loop

### Agent Loop
AutoGPT established the foundational autonomous loop: **Goal -> Plan -> Act -> Observe -> Reflect -> Re-Plan**. Each cycle produces a `Thought` structure containing reasoning, a step-by-step plan, and self-criticism. This is a closed-loop cycle rather than linear Q&A -- the agent keeps going until the goal is achieved or a hard limit is hit.

### Planning Pattern
Uses **Hierarchical Task Networks (HTNs)**: high-level goals are decomposed into trees of executable sub-tasks. The LLM generates ordered steps with explicit reasoning. Plans are expressed in free-form code or natural language, which makes them flexible but hard to validate.

### Execution Pattern
Tool calls return **structured observations** (standardized JSON with status/data/error fields). Tools have pre-hooks (availability checks, permissions) and post-hooks (result formatting). This wrapping layer ensures uniform feedback regardless of the tool's internals.

### Self-Correction Pattern
AutoGPT pioneered **forced meta-cognition**: every step includes an explicit `criticism` field. The agent must evaluate its own output before proceeding. This evolved into patterns like:
- **Self-reflection**: review trajectory, identify errors
- **Trio reflection** (AutoPlan): summarize -> find flaws -> suggest revisions
- **Batch-based reflection**: use multiple task instances in one iteration for more stable optimization

### Memory Pattern
**Three-tier memory**: short-term (LLM context window for recent N steps), medium-term (vector DB for semantic retrieval), long-term (filesystem for persistent knowledge across sessions). This three-tier design is the industry baseline, but vector retrieval quality directly impacts decision quality, and compression can discard critical state.

### Failure Cases (Hard-Won Lessons)
- **Infinite loops**: LLMs lack reliable "completion state" awareness. Mitigations: hard step caps, external completion detection, deduplication checks.
- **Token explosion**: linear context growth is unsustainable. Mitigations: rolling summaries, vector retrieval instead of full history, task isolation.
- **Goal drift**: noise accumulates in context over many steps. Mitigations: periodic goal re-anchoring, structured intermediate outputs.
- **Error propagation**: with error probability p per step, success rate decays as p^steps. Mitigations: critic agents, lower task chain length, human-in-the-loop checkpoints.
- **Sub-agent depth**: recursive decomposition past ~3 layers causes context collapse. Mitigations: max depth limits, deep-copy state between layers, blackboard communication.

### Key Takeaway for JARVIS
The three-tier memory model is over-engineered for a single-user assistant, but the *concept* of explicit self-criticism at each step is valuable. The failure case lessons are the most actionable: JARVIS already has a history cap, but explicit completion detection (does the model know when it's done?) and goal drift checks would prevent the assistant from going off-track mid-conversation. The pre-hook/post-hook tool wrapping pattern is simple and directly applicable to JARVIS's `_execute_tool` dispatch.

---

## Cross-Cutting Synthesis: What Matters for JARVIS

### 1. Split Reasoning from Execution (Aider's key insight)
The single most transferable pattern. JARVIS already has this structure implicitly (Claude reasons, tools execute), but making it explicit -- treating the reasoning pass and the tool-formatting pass as separate concerns -- would improve reliability and cache stability.

### 2. Agent Flow as a Graph, Not a Loop (LangGraph's key insight)
JARVIS's current linear loop is simple but brittle. Adding conditional branching (e.g., "on tool error, retry up to 3 times before escalating") and parallel execution (e.g., simultaneous web search + file read) would be easier with a graph model. This doesn't require a framework -- just a state machine with typed transitions.

### 3. Immutable Event Log for Debugging (OpenHands' key insight)
Persisting every turn + tool result as an immutable log enables replay, debugging, and state restoration. JARVIS's current in-memory history is lost on crash. A lightweight append-only log (JSON lines) would be a high-value addition.

### 4. Guardrails over Autonomy (AutoGPT's hard-won lesson)
Autonomous agents are unreliable -- the value comes from bounded autonomy with hard limits. JARVIS should have explicit: step caps per task, retry limits, danger-zone file protection (it already has this for `call_developer_agent` paths), and human interrupt capability.

### 5. Prompt Cache Stability (Cross-cutting)
All four frameworks implicitly depend on predictable context structure. JARVIS's current design (static system prompt + cache-controlled tools section + dynamic content in user messages only) is architecturally correct. The Architect/Editor split reinforces this: keep the reasoning prompt cache-stable, and vary only the execution content.

### 6. Structured Failure Feedback
Every framework handles tool errors differently, but the common pattern is: **uniform error structure** + **retry limits** + **escalation path**. JARVIS should standardize its tool error format and add retry logic before surfacing errors to the model.
