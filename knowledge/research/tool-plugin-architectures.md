# Extensible Tool/Plugin Systems for AI Agents

## Summary of Concepts, Patterns, and Best Practices

---

## 1. Tool Dispatch Architecture

### The Three-Layer Pattern (Production Standard)

Production AI agent tool systems -- Claude Code, LangGraph, OpenAI Agents SDK -- converge on a **three-layer architecture**:

- **Registry Layer** -- A collection of tool definitions (name, description, input schema, metadata). Tools are either statically imported or dynamically discovered via entry points, directory scanning, or decorator-based registration (`@tool`, `@registry.register`).
- **Assembly Layer** -- Runtime filtering and assembly into the final tool pool sent to the model. This is where feature gates, permissions, MCP-server merges, and environment-specific pruning happen. **Partitioned sorting** (built-in tools first, external tools second) is a deliberate cache-optimization strategy -- the API server sets a cache breakpoint between partitions, so interleaving external tools would invalidate the entire cache key.
- **Execution Layer** -- The turn loop that receives `tool_use` blocks from the model, validates arguments, executes handlers, and returns `tool_result` blocks. This ranges from the SDK's built-in `ToolRunner` (recommended for most cases) to custom agentic loops with fine-grained control over logging, human-in-the-loop gates, and conditional continuation.

### Dynamic Registration Patterns

Five proven mechanisms exist for registering tools at runtime, each with different trade-offs:

- **Decorator-based** (`@tool`, `@registry.register`): Simplest API, good ergonomics. Used by LangChain, Pristan, and most Python frameworks.
- **Metaclass-based** (subclass `BaseTool`, auto-registration via `type.__new__`): Maximum framework control, used by LangChain's `BaseTool` subclassing path.
- **Entry points** (`pyproject.toml` `[project.entry-points]`): Standard Python packaging mechanism, enables third-party plugins without modifying the host codebase.
- **Directory scanning** (`importlib.import_module` + `pkgutil.iter_modules`): Runtime discovery from a plugin folder. No registration step required; just drop a file.
- **AST scanning**: Parse source files without importing them (used by KeyRegistry). Useful when plugin module imports are expensive or unsafe.

**Key insight**: For single-process agent systems like JARVIS, decorator-based registration with explicit imports is the simplest and most maintainable. The entry-points pattern becomes essential when supporting third-party plugins in a distributed ecosystem.

---

## 2. Tool Schema Design Best Practices

### Naming Conventions

- Use **prefix-based namespaces** for related tools (`browser_open`, `browser_scroll`, `browser_click`). This helps the model select correctly when dozens or hundreds of tools are available.
- Use **action-oriented verb names** (`search_logs` over `logs`, `create_invoice` over `invoice`). Names should be `snake_case` with no special characters.
- Add **"when NOT to use" guidance** in descriptions if a tool is overused or overlaps with another.

### Descriptions that Drive Correct Selection

The single most impactful schema element is the **description field**. Effective descriptions:

- Tell the model **when to call the tool** ("Use this when the user asks about recent orders or order history"), not just what it does.
- Make implicit context explicit (specialized query formats, niche terminology, resource relationships).
- Describe tools as you "would to a new hire on your team" (Anthropic's guidance).
- Include parameter-level annotations: what each argument means, valid ranges, format expectations.

### Schema Rigor

- Mark every parameter as `required` unless it genuinely has a sensible default.
- Use `enum` for any parameter with a fixed set of values.
- Set `additionalProperties: false` on all object schemas to prevent hallucinated parameters.
- Use `strict: true` (Anthropic) or `strict: true` (OpenAI Structured Outputs) to guarantee the model's arguments conform to the schema -- this eliminates JSON parsing errors.
- For numeric parameters, add `minimum`/`maximum` bounds.
- For string parameters, consider format hints (`date-time`, `uri`, `email`).

### Granularity Trade-off

The most important structural decision is **how many tools to define**. Anthropic's guidance is clear: "Fewer, more thoughtful tools outperform many thin wrappers." A consolidated `schedule_event` tool beats separate `list_users` + `list_events` + `create_event` tools. A `get_customer_context` that returns all relevant information at once beats three sequential lookup calls. The reasoning: each tool call costs tokens, and the model's selection accuracy drops sharply as the tool count grows (from ~94% at 6 tools to ~71% at 18 tools in flat registries).

For systems that genuinely need many tools (50+), the **Tool Search / Skills** pattern provides progressive disclosure -- tools are loaded on demand rather than all at once. The `ToolSearchTool` pattern (Anthropic) and `Skills` pattern (LangChain) both defer tool definitions so the base tool list stays cache-stable.

---

## 3. Tool Result Formatting for LLM Self-Correction

### Return Errors, Not Exceptions

The fundamental principle: **errors are data, not exceptions**. Every failure must be returned as a `tool_result` block with `"is_error": true`, not thrown as an exception. This lets the model see the error and decide how to respond:

```json
{
  "type": "tool_result",
  "tool_use_id": "abc123",
  "content": "File not found: /data/reports/q3.csv. Available files: q1.csv, q2.csv.",
  "is_error": true
}
```

### Actionable Error Messages

Generic error codes or Python tracebacks are useless to the model. Effective error messages:

- Tell the model **what went wrong** in plain language.
- Tell the model **what to do instead** ("Use a different date range" or "Available options are: ...").
- For truncation (e.g., result too large), steer toward filters or pagination rather than repeating a broad query.

### Response Structure Choices

Test different response formats (XML, JSON, Markdown) against your own evaluation. LLMs tend to perform better with formats that match their training data. Offer a `ResponseFormat` enum (`"concise"` vs `"detailed"`) so the model can control verbosity -- this can reduce tokens to roughly one-third of the detailed version.

### Truncation Discipline

Any tool that could return large results should implement **pagination, range selection, filtering, and/or truncation** with sensible defaults. The default content limit for tool results should be explicit (e.g., 3000 characters for JARVIS). Truncation messages should guide the model to more targeted queries.

---

## 4. Security Patterns for Tool Execution

### Defense in Depth

Security for agent tool systems requires overlapping, independent layers. Claude Code's BashTool demonstrates 7+ layers: AST parsing, command substitution blocking, dangerous-command denylists, compound-command splitting limits, safe environment variable stripping, sed whitelist validation, and path validation for each command category. The principle: "any single layer can fail, but an attacker needs to bypass all layers simultaneously."

### Essential Security Controls

- **Deny-by-default network**: No outbound network access unless explicitly allowed for a specific tool.
- **Deny-by-default filesystem**: Ephemeral workspace; no host mounts.
- **Hard execution timeouts**: Default timeout per tool call (e.g., 30 seconds), with granular per-tool limits.
- **Memory/resource limits**: Cgroups or VM-level caps on CPU, memory, and disk I/O.
- **Input validation**: Validate all tool arguments server-side before execution. Check ranges, sizes, nesting depth (e.g., max 10-20 levels), and byte sizes (e.g., max 64KB per argument).
- **Input size limits**: Prevent LLM-generated fork bombs or giant file writes. Enforce maximum content size on write operations.
- **Rate limiting**: Global and per-tool rate limits with rolling windows and circuit breakers. Auto-open after N failures; TTL-based cooldown.

### The Fail-Closed Default Pattern

New tools should default to the most conservative settings: non-concurrent, read-write capable, permission-required. Each property must be explicitly opted into (e.g., `isReadOnly: true`) rather than opted out of. The rationale: marking a read-only tool as non-read-only causes "unnecessary permission prompts -- annoying but safe." The reverse (marking a destructive tool as read-only) could enable "data corruption -- dangerous and subtle."

### Sandboxing Tiers

For code execution tools especially, three isolation tiers exist:

- **Process isolation** (Linux namespaces + seccomp + cgroups): Fastest (~5ms boot), ~0% CPU overhead. Adequate for single-user desktop systems.
- **Syscall interception** (gVisor/runsc): ~50ms boot, ~20% overhead. Recommended default for production.
- **Hardware virtualization** (Firecracker microVM): ~250ms boot, ~1% overhead. Required for multi-tenant systems.

### Human-in-the-Loop Gating

Destructive operations (email sends, database writes, financial transactions, file deletions) should require explicit approval. Implement this as a tool-level `confirmationRequired` flag rather than a global setting -- each tool knows its own destructiveness.

---

## 5. Hot-Reloading Tools Without Restart

### Options and Trade-offs

- **In-place function patching** (`mighty_patcher`): Uses C extensions to modify function objects in memory. All references update automatically. Not production-safe (memory leaks on repeated reloads).
- **Decorator-based re-read** (`hotfunc`): `@hotreload` decorator re-reads the source file on every call. Simple but slow; only top-level functions.
- **Module-level reload** (`importlib.reload`): Standard Python approach. Stale references are the main problem -- existing objects continue pointing to old modules.
- **MCP HMR** (`mcp-hmr`): Dependency-graph-aware hot module replacement for MCP servers. Only changed modules and their dependents reload; server connections (stdio transport) are preserved.

### Practical Advice for JARVIS

For a single-user desktop assistant, the simplest viable pattern is the **backup-and-restart** approach JARVIS already uses via `call_developer_agent` -> `os.execv`. True hot-reload adds significant complexity and is primarily beneficial for server processes that cannot tolerate downtime. A middle ground: watch tool files with a filesystem watcher (`watchdog`), and only support hot-add (new tools), not hot-modify (changed tools), without restart.

---

## 6. Testing Patterns for LLM-Facing Tools

### What to Test

Testing AI-agent tool systems requires testing at three levels:

- **Schema validity**: Does each tool have a valid JSON Schema? Are descriptions non-empty? Are required fields actually required? Do parameter names follow conventions? Contract-test tool schemas against your API specs in CI to catch drift.
- **Tool execution**: Does the handler correctly process valid inputs? Does it gracefully handle invalid inputs, timeouts, and external failures? Can it produce targeted error messages?
- **Model behavior**: Given a user query, does the model select the correct tool with the correct arguments? This is the hardest and most important test.

### Testing Patterns

- **Trace-based assertion**: "Assert against the trace, not the prose" (Understudy framework). Don't test what the agent said; test what it did -- the sequence of tool calls. This is more deterministic and more informative.
- **Repository-backed mocks**: Match mock responses by tool name + arguments + context. Can fall back to real execution for unregistered cases. Provides deterministic testing while maintaining realism.
- **LLM-powered simulation**: For multi-turn stateful workflows (booking systems, databases), use an LLM to generate adaptive mock responses rather than static fixtures. Maintain shared state across tool calls.
- **Schema-first testing**: Generate valid and invalid payloads from your tool schemas automatically. Use tools like Zod Contract Mock Forge to produce boundary violations, union exhaustiveness tests, and drift detection between tool schemas and implementation.
- **Dependency injection**: Mock the LLM layer itself for deterministic unit tests of agent decision logic. This isolates tool selection behavior from model variability.
- **Edge case coverage**: Test malformed tool output, missing fields, type mismatches, API failures, budget exhaustion, and max-retry scenarios.

### Rubrics for Behavioral Testing

For qualities that can't be checked deterministically, use LLM judges with structured rubrics:

- `TOOL_USAGE_CORRECTNESS`: Did the agent use the right tool with the right parameters?
- `POLICY_COMPLIANCE`: Did the agent respect security and safety constraints?
- `TASK_COMPLETION`: Did the agent achieve the user's goal?
- `ADVERSARIAL_ROBUSTNESS`: Did the agent resist prompt injection attempts?

---

## 7. Versioning and Deprecation of Tools

### The Versioning Challenge

Tools in AI agent systems face a unique versioning problem: the "consumer" is an LLM, not a human developer. The LLM cannot read migration guides or changelogs. This means **backward compatibility is more critical** than in traditional API design, and breaking changes must be signalled in-band (through the tool interface itself) rather than through documentation.

### Practical Patterns

- **Additive changes are safe**: Adding new optional parameters, adding new tools, expanding enum values -- these are non-breaking and require no migration.
- **Version-pin in production**: Pin every agent run to a specific tool-set version. Don't fetch "latest" at runtime. This ensures reproducibility and makes rollback trivial.
- **Deprecation lifecycle**: Announce deprecation in the tool description ("[DEPRECATED: Use `search_logs` instead]"), maintain the old tool for a transition period, then remove. The old tool's description should actively redirect to the replacement.
- **SemVer for tool contracts**: Major version bumps for breaking changes (renamed tools, removed required parameters, changed return types). Minor for additive changes. Patch for bug fixes with identical schemas.
- **Alias support**: When renaming a tool, keep the old name as an alias for one minor version cycle. The dispatch layer resolves aliases silently.
- **Canary rollouts**: Route a small fraction of requests to the new tool version first. Monitor for task completion rate drops (the signal that the model is confused by the change).
- **Contract validation in CI**: Before deploying a tool change, validate that new tool schemas are supersets of old schemas (backward compatible) or explicitly flagged with a major version bump.

### The Anthropic Managed Agents Pattern

Anthropic's managed agents support version pinning: create v1 of a prompt/tool-set, ship v2, detect regression, roll back by pinning sessions to version 1. The key practice: production callers always pin to explicit version IDs, not bare agent IDs.

---

## 8. Key Architectural Takeaways for JARVIS

JARVIS's current architecture (static `AVAILABLE_TOOLS` list, manual `_execute_tool` dispatch, `os.execv` restart) aligns well with a single-user desktop assistant. The most impactful improvements from this research, in priority order:

1. **Add `is_error` to tool results** -- return structured errors instead of plain strings. This enables the model to self-correct on failures.
2. **Write actionable error messages** -- include what went wrong and what to do instead.
3. **Add per-tool timeouts** -- prevent a stuck tool from blocking the entire turn loop.
4. **Implement a Tool base class** -- replace the flat `_execute_tool` dispatch with dynamic method lookup, making new tools easier to add.
5. **Surface `isReadOnly` metadata** -- allow the model to parallelize read-only calls while serializing writes.
6. **Schema-first testing** -- validate tool schemas as part of startup to catch drift early.
7. **Deprecation description pattern** -- when removing/renaming a tool, prepend `[DEPRECATED: Use X instead]` to the description for a transition period.

---

### Sources

- [Anthropic -- Writing Effective Tools for AI Agents](https://www.anthropic.com/engineering/writing-tools-for-agents)
- [Anthropic -- Tool Use Concepts (Skills Repository)](https://github.com/anthropics/skills/blob/main/skills/claude-api/shared/tool-use-concepts.md)
- [LangChain -- Tools Documentation](https://docs.langchain.com/oss/python/langchain/tools)
- [LangChain -- Skills Documentation](https://docs.langchain.com/oss/python/langchain/multi-agent/skills)
- [LangChain -- Workflows and Agents](https://docs.langchain.com/oss/javascript/langgraph/workflows-agents)
- [OpenAI -- Function Calling Cookbook](https://cookbook.openai.com/examples/orchestrating_agents)
- [OpenAI -- Apps SDK Tool Documentation](https://developers.openai.com/apps-sdk/plan/tools)
- [Claude Code Architecture -- Tool System Deep Dive](https://github.com/Windy3f3f3f3f/how-claude-code-works/blob/main/en/docs/04-tool-system.md)
- [Claude Code Architecture -- WaveSpeed Analysis](https://wavespeed.ai/blog/posts/claude-code-architecture-leaked-source-deep-dive/)
- [Understudy -- Scenario Testing for AI Agents](https://github.com/gojiplus/understudy)
- [ToolSimulator -- Scalable Tool Testing for AI Agents](https://aihub.hkuspace.hku.hk/2026/04/21/toolsimulator-scalable-tool-testing-for-ai-agents/)
- [Pristan -- Function-based Plugin System for Python](https://github.com/mutating/pristan)
- [python-registries -- Registry Pattern for Plugin Systems](https://github.com/beanbaginc/python-registries)
- [PerimeterX/mighty-patcher -- Hot Reload for Python](https://github.com/szajbus/hotfunc)
- [SitePoint -- AI Agent Testing Automation Developer Workflows](https://www.sitepoint.com/ai-agent-testing-automation-developer-workflows-for-2026/)
- [Sandbox Management for AI Coding Agents](https://blaxel.ai/blog/sandbox-management-for-ai-coding-agents)
- [mcp-warden -- Security Guardrails for MCP Agents](https://www.npmjs.com/package/mcp-warden)
- [Anthropic Managed Agents -- Prompt Versioning and Rollback](https://platform.claude.com/cookbook/managed-agents-cma-prompt-versioning-and-rollback)
- [Skywork -- Ultimate Guide: How AI Agents Use Tools 2026](https://skywork.ai/blog/ai-agents-using-tools-ultimate-guide-2026/)
