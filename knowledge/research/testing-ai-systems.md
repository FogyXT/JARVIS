# Testing AI-Powered Applications: Concepts & Patterns

> Research compiled for the JARVIS project (voice-driven Claude-powered desktop assistant with tool use and self-modifying code). Focused on concepts, not raw code.

---

## 1. Eval Frameworks for LLM Apps

The landscape has four major players, each with a different philosophy:

**DeepEval** (Apache 2.0) is the best fit for a solo Python project. It offers 50+ metrics (G-Eval, tool correctness, hallucination, task completion) and integrates natively with pytest -- meaning tests look like `def test_my_agent(): ...` and run alongside ordinary unit tests. No SaaS dependency required, and the free tier of the companion Confident-AI platform handles lightweight cloud evaluation.

**LangSmith** excels at trajectory-level tracing for LangChain/LangGraph agents but is opinionated toward that ecosystem. **Braintrust** offers the best experiment UI with dataset diffing and CI quality gates, but is cloud-only with per-seat pricing. **Promptfoo** (MIT, recently acquired by OpenAI) pioneered YAML-based eval and red-teaming but is CLI-only with no production monitoring.

For a solo project like JARVIS, the pragmatic stack is: **DeepEval for structured metrics** (tool correctness, task completion) run locally in pytest, optionally paired with **Langfuse** or **Arize Phoenix** for trace-level observability when debugging.

---

## 2. Prompt Regression Testing

Prompt changes introduce silent regressions -- the output remains grammatical but drifts in quality, safety, or correctness. Three detection strategies combine well:

**Golden test sets** -- A curated collection of (input, expected-behavior-criteria) pairs stored in the repo. Each prompt change runs against this set, and outputs are scored by semantic similarity (via embeddings), LLM-as-judge, or structural assertions (valid JSON, required keywords). A 50-100 example smoke suite runs on every PR; a 500+ example full suite runs nightly.

**Snapshot testing** -- Tools like PyLLMTest save golden outputs and flag changes that exceed a semantic similarity threshold (e.g., cosine distance > 0.1). Unlike traditional snapshot testing (exact string match), LLM snapshots compare meaning, not text.

**A/B comparison** -- The new prompt and the old prompt both score the golden set; a report highlights which examples improved, regressed, or stayed flat. This isolates changes that broadly improve quality from those that fix one case while breaking another.

For JARVIS specifically, the language detection prefix (`[SK]`/`[EN]`) is an easy regression target -- a golden set of bilingual inputs can verify the model still switches correctly after system prompt changes.

---

## 3. Behavioral Testing of Agents

Testing an agent means testing its **observable decisions**, not its exact wording. Key dimensions:

**Tool selection correctness** -- Did the agent call the right tool for the task? Frameworks like pygent-test/AgentCheck provide assertions such as `used_tool("file_manager")` and `used_tools_in_order(["web_search", "download_file"])`. For JARVIS, this means testing "when asked to take a screenshot, did it call `take_screenshot` and not `control_browser`?"

**Tool argument correctness** -- Were the parameters valid? DeepEval's `ToolCorrectnessMetric` compares the tools and arguments called against expected values, supporting exact match, unordered match, and ordering constraints. For JARVIS, this catches bugs like `execute_command("del *")` when the agent meant `execute_command("dir")`.

**Multi-step trajectory testing** -- The CORE framework encodes valid tool-use paths as Deterministic Finite Automata (DFAs), measuring path correctness and prefix criticality. TRAJECT-Bench adds trajectory exact-match and inclusion metrics, diagnosing "similar tool confusion" (calling `read` when `list` was correct) and "parameter-blind selection."

**Error recovery** -- Does the agent retry gracefully when a tool returns an error? Test by injecting failures (e.g., file not found, network timeout) and asserting the agent calls a fallback or rephrases the request rather than crashing or hallucinating.

---

## 4. Mocking the LLM

Testing tool code without real API calls is essential for fast, deterministic, cost-free test suites. Three approaches exist:

**Record/Replay (VCR pattern)** -- Record real LLM interactions to disk (cassettes), then replay them in tests. Tools like **agentape** (SDK interception) and **reel-vcr** (HTTP proxy) capture full tool-call trajectories and streaming output. Cassettes are checked into the repo; tests become deterministic and offline. Re-recording when prompts or models change keeps them fresh.

**Mock server** -- **fakellm** runs a local HTTP server that matches requests against a rules engine, returning predefined responses including tool calls, streaming chunks, and error codes (4xx/5xx for timeout/rate-limit simulation). No code changes needed -- just point `base_url` to localhost.

**Deterministic mock client** -- The simplest approach for JARVIS: subclass `anthropic.Anthropic` to return canned responses based on input patterns. No network, no files, no server process. Tool results are matched by content (e.g., "if the request contains 'list directory', return a mock file listing").

For JARVIS, a combination of **deterministic mocks for unit tests** (testing individual tool implementations) and **record/replay for integration tests** (testing the multi-tool loop) provides the best coverage-to-complexity ratio.

---

## 5. Testing Self-Modifying Code

JARVIS's `call_developer_agent` writes new `.py` files at runtime. Validating generated code requires several layers:

**Pre-write validation** -- Before overwriting the file, pass the generated source through `ast.parse()`. If the AST fails (syntax error), reject the output and retry. This catches the most common generation failure (unclosed brackets, missing colons, malformed imports) before any file is touched.

**Import check** -- After writing, run `python -c "import <module>"` in a subprocess. A failed import indicates missing dependencies or broken module-level code.

**Subprocess execution** -- Execute the modified file in an isolated subprocess with a timeout. Capture stdout, stderr, and the exit code. For JARVIS, this can be integrated into the tool loop: after `call_developer_agent` writes a new tool, the harness can run a short "does this import and execute without crashing" check before the process restarts.

**Backup and diff** -- JARVIS already backs up files to `.bak` before overwriting. Testing can extend this: after the modified file runs, compare behavior against the backup on a small set of known inputs. If the new version fails a smoke test, the old version can be restored automatically.

---

## 6. Testing Voice/Speech Systems

Testing speech recognition (STT) and text-to-speech (TTS) without a physical microphone or speaker requires simulation:

**WAV test fixtures** -- Pre-recorded or synthesized WAV files (e.g., 440 Hz sine waves for basic validation, or TTS-generated speech from known text) serve as deterministic audio input. Tests validate that the pipeline accepts valid WAV headers and rejects corrupt/empty/zero-byte audio.

**Mocking STT** -- Replace the speech recognizer with a deterministic stub that returns predefined text based on the WAV filename or a lookup table. This lets you test the rest of the pipeline (Claude dispatch, tool execution, response speaking) without Google's API.

**Language detection accuracy** -- For JARVIS's bilingual setup, create WAV fixtures with Slovak and English phrases. Mock STT to return the expected transcribed text. Assert that `extract_text_and_speak` correctly updates `CURRENT_LANG` and selects the right TTS voice.

**Round-trip testing** -- The Project-Loqui pattern: feed a known text through TTS, pipe the resulting audio through STT, and compare the output to the original. Track Word Error Rate (WER) across different voices and noise conditions.

**Academic caveat** -- Research shows TTS-synthesized test cases can produce 21-34% false alarms (failures that don't occur with human speech). Google TTS produces the fewest false alarms (17%). Tests validated with synthetic audio should be supplemented with periodic real-voice recordings.

---

## 7. CI/CD for AI Projects

What belongs in CI for an AI-powered project like JARVIS?

**Every PR (fast, deterministic, cheap):**
- Tool schema validation -- verify `AVAILABLE_TOOLS` definitions match the actual function signatures in `tools/*.py`. A mismatch here silently breaks tool dispatch.
- Syntax checks -- `python -m py_compile` on all `.py` files, including any generated by self-modification tests.
- Deterministic mock tests -- run the turn loop against a mock Claude client with known tool-call patterns. Assert correct dispatch, argument passing, and error handling.
- Prompt contract checks -- using recorded fixtures (no live API calls), verify the system prompt still produces valid output structure (language prefix, no hallucinated tool names).

**Nightly or on merge (slower, may call APIs):**
- Golden dataset eval -- run the full eval suite against the real Claude API with temperature=0. Compare scores (tool correctness, task completion, language accuracy) against the previous baseline.
- Cost/latency regression -- track tokens per turn, API call count, and wall-clock time. Flag spikes above configurable thresholds.
- Real audio round-trip -- process a set of WAV fixtures through the full voice pipeline. Assert WER below threshold.

**Per release:**
- Red-teaming -- adversarial prompt testing (injection, off-topic, multilingual edge cases).
- Backup and restore test -- verify the `.bak` rollback mechanism actually works by simulating a failed self-modification.

Tools like **PromptProof** (deterministic contract checks with zero live calls) and **Agentura** (PR regression diffs with cost guardrails) are purpose-built for CI and integrate with GitHub Actions. For a solo project, a single `pytest` run with DeepEval metrics covers most of the fast path; a nightly GitHub Actions workflow with a real API key handles the rest.

---

## 8. Testing RAG / Memory Systems

JARVIS uses a simple JSON key-value store (`jarvis_memory.json`), not a vector database, but the evaluation concepts still apply:

**Synthetic queries with known answers** -- Create a set of (key, value) pairs, store them, then write retrieval tests that read each key and assert the correct value returns. For the `memory("save")` / `memory("read")` flow, this is straightforward: save a fact, read it back, assert exact match.

**Recall@k** -- For projects with chunked or vector storage, Recall@k measures whether the correct document appears in the top-k results. For JARVIS's exact-key lookup, this simplifies to `Recall@1 = 1.0` for all valid keys and `0.0` for missing keys.

**Temporal freshness** -- Test that overwriting a memory replaces the old value (no stale data), and that deleting a memory makes subsequent reads return "not found." JARVIS's single-writer, single-file model makes this deterministic.

**For future upgrades** (if JARVIS moves to vector or semantic memory), the **Sediment Benchmark** and **Engram Benchmark** patterns apply: test retrieval quality (Recall@k, MRR), temporal awareness (recency-weighted ranking), and deduplication (merging near-duplicate memories). The Engram framework goes further by measuring the **task performance delta** -- does the memory system actually make the agent more effective at real tasks, or is retrieval accuracy improving while agent behavior stays flat?

---

## Putting It Together for JARVIS

A pragmatic testing pyramid for the project:

1. **Unit tests** (pytest, no API calls) -- Mock Claude client. Test each tool in isolation. Test `extract_text_and_speak` with known inputs. Test `AVAILABLE_TOOLS` schema matches `_execute_tool` dispatch.
2. **Integration tests** (recorded cassettes, no live API) -- Test the multi-tool loop with a recorded trajectory. Test error injection (what happens when `execute_command` times out?).
3. **Eval suite** (live API, nightly) -- Golden dataset of 20-30 prompts covering all tools. Score tool correctness (DeepEval metric), language accuracy, and response quality.
4. **Self-modification safety** -- Pre-write AST check, post-write subprocess import test, `.bak` restore verification.

This keeps the fast feedback loop fast (everything runs locally, mock-based, in seconds) while still catching regressions that only appear with real model outputs.
