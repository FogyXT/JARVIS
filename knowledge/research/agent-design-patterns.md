# AI System Design Patterns for Autonomous Agents

## 1. Foundational Principle: Simplicity First

The single most important insight from Anthropic's "Building Effective Agents" (Dec 2024) is: **most applications do not need agents at all.** A single well-optimized LLM call with retrieval and in-context examples is often sufficient. Agents should only be deployed when the solution path is ambiguous, the task justifies the latency/cost tradeoff, and no critical capability bottlenecks exist.

**The core agent architecture has only three components:** Environment + Tools + System prompt, with the model called in a loop. Complexity kills iteration speed. Optimizations (caching, parallel tool calls) should follow, not precede, establishing core behavior.

---

## 2. Tool Calling: Schema Design and Error Recovery

### Schema Design
- **Names must be unambiguous and action-oriented** (e.g., `search_flights` not `flights`). The natural-language description field is the single most important factor for correct tool selection by the LLM.
- **Typed parameters** with enums, ranges, and format constraints prevent hallucinated arguments. Set `additionalProperties: false` to block injection of unexpected keys.
- **Too many tools degrade accuracy.** Consider dynamic tool loading -- expose only the subset relevant to the current context or user intent.
- **Tool format should mirror what the model saw on the internet during training.** Avoid unusual formatting overhead (e.g., exact line counting).

### Error Recovery
A key insight from the literature: **never crash on tool errors -- return them to the model as tool results.** The model can read the error message and pivot. The failure taxonomy to handle:

| Failure Type | Recovery Strategy |
|---|---|
| Tool execution errors (runtime exceptions) | Catch in dispatcher; return error text as tool result |
| Malformed calls (wrong name, wrong args) | Return corrective message listing valid options |
| Domain-level errors (valid format, impossible request) | Teach via error messages -- list valid alternatives |
| Graceful degradation (tool unavailable) | Use cached fallback, skip and explain, or surface outage |

A **validate-then-repair layer** can catch semantic malformations that pass JSON validation (e.g., null on optional fields, scalar where array expected, relational invariant violations like offset without limit). Repair budget is spent only where needed.

**Idempotency is critical** -- retries of non-idempotent tools (writes, payments) cause duplicate side effects. Route idempotent calls to retry; non-idempotent calls must gate on human confirmation.

---

## 3. Reasoning Loops: The Dominant Pattern

**ReAct (Reasoning + Acting)** is the default loop: Think -> Act (call tool) -> Observe (read result) -> Think again... This produces traceable trajectories useful for both governance and debugging. The LLM decides which tools to call based on reasoning, then adapts based on results.

**Key variants:**
- **Multi-step reasoning** extends ReAct with structured state fields (not just message history) -- e.g., `search_results`, `analysis`, `final_answer` -- enabling staged workflows like agent searches, then analyzes, then answers.
- **Search-based deliberation** allocates additional compute (self-consistency, tree-of-thoughts, backtracking) only when uncertainty is high, acting as test-time compute scaling rather than a static process.
- **Chain-of-thought** within the agent context helps the model reason before acting, but should be integrated naturally into the ReAct loop rather than prompted separately.

---

## 4. The Five Workflow Patterns (Anthropic)

These patterns form the building blocks of agentic systems, arranged by increasing complexity:

1. **Prompt Chaining** -- Sequential LLM calls with programmatic gates between them. Best when subtasks are cleanly separable and each step's output is the next step's input.

2. **Routing** -- Classify input and dispatch to specialized handlers. Simple example: easy questions go to a cheaper model, hard questions to an expensive one.

3. **Parallelization** -- Two forms: *Sectioning* runs independent subtasks in parallel (e.g., simultaneously process query and run content safety check); *Voting* runs the same task multiple times and aggregates results (e.g., multi-perspective code review).

4. **Orchestrator-Workers** -- A central LLM dynamically decomposes a task, delegates to worker agents, and synthesizes their results. The workers can be specialized (by domain or tool access) and need not all be the same model.

5. **Evaluator-Optimizer** -- One LLM generates, another evaluates and provides feedback in a loop. The generator revises based on critique until a quality threshold is met. Requires clear evaluation criteria.

---

## 5. Planning Agents

The core pattern is **separate planning from execution**. A planner produces a plan with explicit constraints and success criteria; an executor carries it out under stricter tool permissions. This improves controllability, supports human-in-the-loop approval for high-impact steps, and reduces the blast radius of failures.

**Plan-then-Execute flow:** Planner creates full plan -> Executor runs steps sequentially -> Finalizer summarizes. Best for tasks with clear, predictable sequences where you want visibility into the plan upfront.

**Plan-Execute-Verify** adds a verification gate: Plan -> Execute -> Verify -> Iterate (if failed). This enables error detection and self-correction.

**Tradeoff vs. ReAct:** Planning commits to a sequence upfront (good for predictability), while ReAct adapts step-by-step (good for ambiguity). Hybrid approaches use a plan as scaffolding but allow the executor to deviate when observations contradict plan assumptions.

---

## 6. Reflection Agents (Self-Critique)

The **Reflection** pattern: Generator creates draft -> Critic evaluates -> Generator revises -> Critic checks again. This continues until a quality threshold is met or an iteration limit is reached (infinite loops are a real cost risk).

**Variants:**
- **Reflexion** -- The agent stores its mistakes in episodic memory and retrieves relevant failures before acting on similar tasks. It learns from past errors without retraining.
- **Self-Refine** -- The same model generates, reviews, and revises its own output. Cheaper than using separate generator/evaluator models but can miss systematic blind spots.
- **External critic** -- A separate model or rule-based verifier checks proposals against policy, missing evidence, or unsafe side effects *before execution*. This defines the agent's operational semantics, not just its performance.

**Key insight:** Reflection is most valuable when there are objective criteria for quality (unit tests for code, rubric for writing). Without clear criteria, the critic may reinforce the generator's biases.

---

## 7. Multi-Agent Patterns

### Supervisor/Router Pattern
A supervisor agent routes tasks to specialized sub-agents (Research, Code, Writer, etc.) based on intent. Each sub-agent masters one domain with a tailored toolset and system prompt. The supervisor can be an LLM or a lighter classifier.

**When to fan out:** When tasks genuinely require multiple areas of expertise; when context isolation matters (each agent's context window is devoted to its specialty); when toolsets conflict or are too large for a single agent.

**Key design rule:** Specialization beats monolithic agents. Each sub-agent should be the smallest competent unit for its domain.

### Hierarchical Agents (Router -> Specialist)
A generalization of the supervisor pattern with multiple levels. High-level routers decompose goals into sub-goals, mid-level planners sequence them, and low-level executors handle specific tool calls. This mirrors organizational hierarchy and naturally limits context window size at each level.

**Benefits:** Clear delegation boundaries; independent optimization per level; natural human-in-the-loop insertion points at each level.
**Cost:** Higher latency and token consumption; more failure modes to debug.

### Evaluator-Optimizer
This is a multi-agent pattern even when both agents are the same model -- one plays the generator role, one the evaluator role. The separation of concerns prevents the model from shortcutting its own critique to match its generation.

---

## 8. Memory Architecture

Structured memory supports coherence beyond raw context windows. The three types:

- **Episodic memory** -- What happened (conversation history, action traces)
- **Semantic memory** -- Facts (user preferences, domain knowledge, RAG documents)
- **Procedural memory** -- Skills (tool usage patterns, successful workflows)

For a solo-developer project, episodic memory (history window) + semantic memory (persistent key-value store) is sufficient. Procedural memory emerges from the system prompt and tool descriptions.

**Critical tradeoff:** Memory increases the attack surface -- stored information can be retrieved in unintended contexts. Use verifiers to check claims against trusted sources.

---

## 9. Practical Rules of Thumb

- **Start with interfaces, not models.** Define tool schemas and action templates first. This reduces brittleness by turning open-ended text into typed actions.
- **Classify actions by reversibility.** Low-risk reads get minimal deliberation; high-risk writes trigger additional verification, multi-step evidence gathering, or human confirmation.
- **Build a trace-first data flywheel.** Log full trajectories (prompts, tool calls, outputs, outcomes). Continuously mine failures for targeted improvements -- better prompts, new tools, stronger verifiers.
- **Evaluate as a system, not a model.** Report success rate alongside cost, latency, trace completeness, robustness under variability, and safety violations.
- **Budget awareness is unsolved.** Agents lack clear mechanisms for enforcing cost budgets. Solving this for your project (e.g., per-turn token caps, tool call limits) provides a real advantage.

---

## 10. Key Sources

- Anthropic, "Building Effective Agents" (Dec 2024) -- https://www.anthropic.com/engineering/building-effective-agents
- "AI Agent Systems: Architectures, Applications, and Evaluation" (arXiv 2601.01743)
- "Schema First Tool APIs for LLM Agents" (arXiv 2603.13404)
- "A Review of Prominent Paradigms for LLM-Based Agents: Tool Use, Planning, and Feedback Learning" (arXiv 2406.05804)
- "Agentic Large Language Models, a Survey" (arXiv 2503.23037)
- "From Language to Action: A Review of LLMs as Autonomous Agents and Tool Users" (arXiv 2508.17281)
- LangGraph Tutorials and Agent Pattern Libraries
