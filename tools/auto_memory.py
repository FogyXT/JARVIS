"""
Auto-Memory Hook — automaticky ukladá fakty z každej konverzácie.

Ako ľudská pamäť: nečaká na príkaz "zapamätaj si toto."
Ukladá priebežne, automaticky, po každej interakcii.

Použitie:
    from tools.auto_memory import auto_remember
    auto_remember(user_message, assistant_response)

    # Alebo len text:
    auto_remember("We fixed the login timeout bug and added logging")
"""

import re
import time
import os
import hashlib
import json
import threading

from tools.jarvis_logging import log


# ── Config ────────────────────────────────────────────────────────────────

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COUNTER_FILE = os.path.join(PROJECT_ROOT, "auto_memory_counter.json")

# How often to run consolidation (every N calls)
CONSOLIDATE_EVERY = 10

# Time-based auto-save (runs regardless of consolidation count)
AUTO_SAVE_INTERVAL = int(os.environ.get("AUTO_SAVE_INTERVAL", "300"))      # 5 min between ticks
IDLE_PAUSE_THRESHOLD = int(os.environ.get("IDLE_PAUSE_THRESHOLD", "900"))  # 15 min idle → pause

# Conversation buffer — accumulates exchanges for timer-based auto-save
_conversation_buffer = []   # list of {user, assistant, timestamp}
_buffer_lock = threading.Lock()
MAX_CONVERSATION_BUFFER = 20

# Scheduler thread
_scheduler_thread = None
_scheduler_running = False

# Patterns that indicate important facts worth storing
FACT_PATTERNS = [
    # Rozhodnutia
    (r"(?i)(rozhodli|decided|chose|picked|going with|will use)\s+(.+)", "decision", 0.7),
    # Bugy
    (r"(?i)(bug|error|issue|problem|broken|fails?|crash)\s*[:—–-]\s*(.+)", "bug", 0.8),
    # Fixy
    (r"(?i)(fixed|opravil|vyriešil|solved|resolved|patched)\s+(.+)", "fix", 0.8),
    # Preferences
    (r"(?i)(prefer|want|like|dislike|hate|love|don'?t want|chcem|nechcem|páči|nepáči)\s+(.+)", "preference", 0.6),
    # Goals / Plans
    (r"(?i)(goal|cieľ|plan|plán|next step|todo|to-do|will build|will create|ideme|spravíme)\s+(.+)", "plan", 0.6),
    # Discoveries
    (r"(?i)(discovered|zistil|found out|learned|realized|našiel|objavil)\s+(.+)", "discovery", 0.7),
    # Tools / Tech
    (r"(?i)(using|používame|stack|tool|library|framework|knižnic[a-u])\s+(.+)", "tech", 0.5),
    # Architecture
    (r"(?i)(architecture|architektúr[a-z]*|design|návrh|pattern)\s+(.+)", "architecture", 0.7),
    # Progress
    (r"(?i)(completed|finished|done|hotov[oé]|dokončen[oé]|built|postavil|implemented)\s+(.+)", "progress", 0.7),
    # Deployments / publishing
    (r"(?i)(deploy|push|publish|release|zverejnil|vydal|nahral)\s+(.+)", "deploy", 0.8),
    # NEW: Created / added
    (r"(?i)(created|added|pridal|vytvoril|wrote|napísal)\s+(.+)", "progress", 0.7),
    # NEW: Tests / testing
    (r"(?i)(test|otestoval|verified|overil)\s+(.+)", "progress", 0.6),
    # NEW: Sent / shared
    (r"(?i)(sent|poslal|shared|zdieľal|posted|submitted)\s+(.+)", "deploy", 0.7),
    # NEW: Configured / set up
    (r"(?i)(configured|set up|nastavil|initialized|spustil)\s+(.+)", "tech", 0.7),
    # NEW: Key facts (this is X, X is Y)
    (r"(?i)(this is|toto je|it'?s a|je to)\s+(.+)", "fact", 0.4),
    # NEW: Personal facts — "my X is/are Y", "I have a X named Y"
    (r"(?i)(my\s+\w+(?:\s+\w+)?\s+(?:is|are|was|were)\s+(?:named\s+)?)(.+)", "personal", 0.6),
    (r"(?i)(i\s+have\s+(?:a|an|the)\s+)(.+)", "personal", 0.6),
    # NEW: Named entities — "X is called/named Y"
    (r"(?i)(\w+(?:\s+\w+)?\s+(?:is|are)\s+(?:called|named)\s+)(.+)", "personal", 0.6),
    # NEW: User identity — "I am X", "I'm a X"
    (r"(?i)(i\s+(?:am|'m)\s+(?:a|an|the|from|in|at)\s+)(.+)", "personal", 0.6),
    # NEW: Possessions — "X has a Y", "X owns a Y"
    (r"(?i)(\w+\s+(?:has|owns|possesses)\s+(?:a|an|the)\s+)(.+)", "personal", 0.5),
    # NEW: Locations — "X lives in Y", "X is from Y"
    (r"(?i)(\w+\s+(?:lives?\s+in|is\s+from|comes\s+from|pochádza\s+z|býva\s+v))\s+(.+)", "personal", 0.6),
    # NEW: Preferences and attributes — "my favorite X is Y", "X's favorite Y is Z"
    (r"(?i)((?:my|his|her|their|fogy'?s?)\s+(?:favorite|favourite)\s+\w+\s+(?:is|are))\s+(.+)", "preference", 0.6),
]

# Counter — koľkokrát sme volali
_counter = {"calls": 0, "facts_stored": 0, "last_consolidation": 0}


def _load_counter():
    global _counter
    try:
        if os.path.exists(COUNTER_FILE):
            import json
            with open(COUNTER_FILE, "r") as f:
                _counter.update(json.load(f))
    except Exception:
        pass


def _save_counter():
    import json
    os.makedirs(os.path.dirname(COUNTER_FILE), exist_ok=True)
    with open(COUNTER_FILE, "w") as f:
        json.dump(_counter, f)


_load_counter()


# ── Conversation Buffer ───────────────────────────────────────────────────

def _add_to_conversation_buffer(user_msg: str = "", assistant_resp: str = "") -> None:
    """Append an exchange to the rolling conversation buffer (thread-safe)."""
    if not user_msg and not assistant_resp:
        return
    with _buffer_lock:
        _conversation_buffer.append({
            "user": user_msg,
            "assistant": assistant_resp,
            "timestamp": time.time(),
        })
        while len(_conversation_buffer) > MAX_CONVERSATION_BUFFER:
            _conversation_buffer.pop(0)


# ── LLM Extraction ────────────────────────────────────────────────────────

LLM_EXTRACTION_PROMPT = """Extract ALL meaningful information from the following conversation exchange.
Do NOT limit yourself to predefined categories. Save everything worth remembering —
decisions, bugs, fixes, preferences, personal information, code architecture,
project details, technical choices, goals, discoveries, progress, configuration,
research findings, casual mentions, offhand comments, user context, file changes,
tool usage patterns — EVERYTHING that might be useful later.

For each fact, return:
- key: short unique identifier (snake_case, max 40 chars)
- value: the complete fact (1-3 sentences, preserves technical detail)
- type: one of [decision, bug, fix, preference, personal, tech, architecture, plan, discovery, progress, deploy, fact, research, context]
- importance: float 0.1-1.0 (higher = more critical to remember)

CRITICAL RULES:
- If code was changed: save WHAT file, WHAT change, WHY
- If research was done: save findings, sources, conclusions
- If user shared personal info: save it (name, location, preferences, tools, goals)
- If a bug was discussed: save symptoms, root cause, fix
- If architecture was discussed: save design decisions, trade-offs
- Err on the side of saving MORE. Better 10 redundant facts than 1 missed insight.

Conversation:
{text}

Return ONLY a JSON array of objects, nothing else. Example:
[{"key": "fixed_login_timeout", "value": "Fixed login timeout bug in auth.py by increasing timeout to 30s and adding retry logic", "type": "fix", "importance": 0.9}]
If nothing meaningful to extract, return []"""


def _llm_extract_facts(text: str, model: str = "deepseek-chat") -> list[dict]:
    """Use the specified LLM to extract meaningful facts from conversation text.

    Args:
        text: Conversation text to extract from
        model: LLM to use — matches the conversation model

    Returns list of {key, value, type, importance} dicts.
    Falls back to empty list on any failure.
    """
    if not text or len(text.strip()) < 20:
        return []

    prompt = LLM_EXTRACTION_PROMPT.replace("{text}", text[:8000])  # safety cap

    try:
        from tools.llm_helper import call_llm
        result = call_llm(prompt, model=model, max_tokens=2000, temperature=0.1)
        if not result:
            return []

        # Strip markdown fences if present
        result = result.strip()
        if result.startswith("```"):
            result = result.split("\n", 1)[-1] if "\n" in result else result[3:]
            if result.endswith("```"):
                result = result[:-3]

        facts = json.loads(result)
        if not isinstance(facts, list):
            return []

        # Validate and normalize
        validated = []
        for f in facts:
            if not all(k in f for k in ["key", "value", "type"]):
                continue
            value = str(f["value"])[:300]
            if len(value) < 3:
                continue
            content_hash = hashlib.sha256(value.encode()).hexdigest()[:16]
            validated.append({
                "key": f"auto_{f['type']}_{content_hash}",
                "value": value,
                "type": str(f["type"]),
                "importance": min(1.0, max(0.1, float(f.get("importance", 0.5)))),
            })
        return validated
    except (json.JSONDecodeError, ValueError, Exception) as e:
        log.debug(f"LLM extraction failed: {e}", module="auto_memory")
        return []


# ── Fact Extraction ───────────────────────────────────────────────────────

def _extract_facts(text: str) -> list[dict]:
    """Extrahuj dôležité fakty z textu pomocou patternov.

    DEPRECATED: kept as fallback when DEEPSEEK_API_KEY is not available.
    Use _llm_extract_facts() for AI-powered extraction without hardcoded patterns.
    """
    facts = []
    seen = set()

    # Process each line separately for clean capturing
    lines = text.split("\n")
    for pattern, fact_type, base_importance in FACT_PATTERNS:
        for line in lines:
            for match in re.finditer(pattern, line):
                # Get the captured content
                if match.lastindex and match.lastindex >= 2:
                    content = match.group(2).strip()
                elif match.lastindex == 1:
                    content = match.group(1).strip()
                else:
                    content = match.group(0).strip()

                # Skip too short or too long
                if len(content) < 3 or len(content) > 300:
                    continue

                # Clean up
                content = content.strip(".,;:!?\"' \t\n")

                # Truncate at first sentence boundary to avoid capturing assistant response
                for sep in ['. ', '! ', '? ', '.\n', '!\n', '?\n']:
                    idx = content.find(sep)
                    if idx > 10:  # only truncate if we have meaningful content before
                        content = content[:idx + 1]
                        break

                content = content[0].upper() + content[1:] if content else ""

                # Skip duplicates
                key = content.lower()[:50]
                if key in seen:
                    continue
                seen.add(key)

                # Boost importance for longer/more specific facts
                importance = base_importance
                if len(content) > 50:
                    importance = min(1.0, importance + 0.1)
                if any(c.isdigit() for c in content):
                    importance = min(1.0, importance + 0.05)

                # Content-hash key for persistent dedup (was: timestamp-based — caused 57-73% duplicates)
                content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
                facts.append({
                    "key": f"auto_{fact_type}_{content_hash}",
                    "value": content,
                    "type": fact_type,
                    "importance": round(importance, 2),
                })

    return facts


# ── Auto-Remember ─────────────────────────────────────────────────────────

def auto_remember(user_message: str = "", assistant_response: str = "",
                  context: str = "", model: str = "deepseek-chat") -> dict:
    """Automaticky ulož dôležité fakty z konverzácie.

    Volaj po každej výmene (user message + assistant response).
    Uses the same LLM model that handled the conversation for extraction.

    Args:
        model: LLM to use for extraction. Matches the conversation model.
               "deepseek-chat" (coding mode), "claude-sonnet-4-6" (Jarvis mode), etc.

    Returns:
        {"stored": N, "facts": [...], "consolidated": bool}
    """
    global _counter
    _counter["calls"] += 1

    # Add to conversation buffer for time-based auto-save
    _add_to_conversation_buffer(user_message, assistant_response)

    # Extract facts — LLM first, regex fallback
    combined = f"User: {user_message}\nAssistant: {assistant_response}"
    if context:
        combined += f"\nContext: {context}"

    facts = _llm_extract_facts(combined, model=model)

    if not facts:
        # Fallback: regex patterns (works without API key)
        facts = _extract_facts(user_message)
        facts += _extract_facts(assistant_response)
        if context:
            facts += _extract_facts(context)

    # Deduplicate within this batch
    seen_keys = set()
    unique_facts = []
    for f in facts:
        if f["key"] not in seen_keys:
            seen_keys.add(f["key"])
            unique_facts.append(f)
    facts = unique_facts
    if not facts:
        _save_counter()
        return {"stored": 0, "facts": [], "consolidated": False}

    # Store each fact — skip duplicates in buffer AND persistent store
    stored_count = 0
    try:
        from tools.memory import memory, _load_memory
        from tools.episodic_memory import get_buffer
        buf = get_buffer()

        # Load persistent JSON for cross-session dedup
        persistent_mem = _load_memory()

        for fact in facts:
            # Check if a very similar fact already exists (3-level dedup)
            duplicate = False

            # Level 1: Content-hash key already in persistent JSON
            if fact["key"] in persistent_mem:
                duplicate = True

            # Level 2: EpisodicBuffer (in-memory)
            if not duplicate and buf:
                for item in buf.working + buf.episodic:
                    existing_val = item.value.lower().strip()[:60]
                    new_val = fact["value"].lower().strip()[:60]
                    if existing_val == new_val:
                        duplicate = True
                        break
                    if len(new_val) > 20 and new_val[:40] in existing_val:
                        duplicate = True
                        break

            # Level 3: Check persistent JSON for near-duplicate values
            if not duplicate:
                for existing_val in persistent_mem.values():
                    if isinstance(existing_val, str):
                        ev = existing_val.lower().strip()[:60]
                        nv = fact["value"].lower().strip()[:60]
                        if ev == nv or (len(nv) > 20 and nv[:40] in ev):
                            duplicate = True
                            break

            if duplicate:
                log.debug(f"Skipping duplicate: {fact['value'][:60]}", module="auto_memory")
                continue

            memory("save", fact["key"], fact["value"])
            stored_count += 1
            _counter["facts_stored"] += 1
            log.debug(f"Auto-remembered: {fact['value'][:80]}",
                     module="auto_memory",
                     data={"type": fact["type"], "importance": fact["importance"]})
    except Exception as e:
        log.warn(f"Auto-memory store failed: {e}", module="auto_memory")

    # Periodically consolidate
    consolidated = False
    if _counter["calls"] % CONSOLIDATE_EVERY == 0:
        try:
            from tools.consolidation import consolidate_quick
            result = consolidate_quick()
            _counter["last_consolidation"] = time.time()
            consolidated = True
            log.debug(f"Auto-consolidation: {result['elapsed_ms']}ms",
                     module="auto_memory")
        except Exception as e:
            log.warn(f"Auto-consolidation failed: {e}", module="auto_memory")

    _save_counter()
    return {"stored": stored_count, "facts": facts, "consolidated": consolidated}


def auto_remember_text(text: str) -> dict:
    """Skratka — automaticky si zapamätaj z jedného textu."""
    return auto_remember(assistant_response=text)


# ── Time-Based Auto-Save Scheduler ────────────────────────────────────────

def auto_save_from_conversation() -> dict:
    """Drain the conversation buffer and save everything via LLM extraction.

    Called by the scheduler timer every AUTO_SAVE_INTERVAL seconds.
    Drains ALL buffered exchanges at once to minimize API calls.
    """
    with _buffer_lock:
        if not _conversation_buffer:
            return {"stored": 0, "facts": []}
        exchanges = list(_conversation_buffer)
        _conversation_buffer.clear()

    # Build combined text from all buffered exchanges
    parts = []
    for ex in exchanges:
        if ex["user"] or ex["assistant"]:
            parts.append(f"User: {ex['user']}\nAssistant: {ex['assistant']}")
    combined = "\n---\n".join(parts)

    if not combined.strip():
        return {"stored": 0, "facts": []}

    # Extract facts via LLM
    facts = _llm_extract_facts(combined)
    if not facts:
        return {"stored": 0, "facts": []}

    # Dedup and save (same logic as auto_remember)
    seen_keys = set()
    unique_facts = []
    for f in facts:
        if f["key"] not in seen_keys:
            seen_keys.add(f["key"])
            unique_facts.append(f)
    facts = unique_facts

    stored_count = 0
    try:
        from tools.memory import memory, _load_memory
        from tools.episodic_memory import get_buffer
        buf = get_buffer()
        persistent_mem = _load_memory()

        for fact in facts:
            duplicate = False

            # Level 1: content-hash in persistent JSON
            if fact["key"] in persistent_mem:
                duplicate = True

            # Level 2: EpisodicBuffer
            if not duplicate and buf:
                for item in buf.working + buf.episodic:
                    existing_val = item.value.lower().strip()[:60]
                    new_val = fact["value"].lower().strip()[:60]
                    if existing_val == new_val or (len(new_val) > 20 and new_val[:40] in existing_val):
                        duplicate = True
                        break

            # Level 3: persistent JSON near-duplicate
            if not duplicate:
                for existing_val in persistent_mem.values():
                    if isinstance(existing_val, str):
                        ev = existing_val.lower().strip()[:60]
                        nv = fact["value"].lower().strip()[:60]
                        if ev == nv or (len(nv) > 20 and nv[:40] in ev):
                            duplicate = True
                            break

            if duplicate:
                continue

            memory("save", fact["key"], fact["value"])
            stored_count += 1
            _counter["facts_stored"] += 1
    except Exception as e:
        log.warn(f"Auto-save store failed: {e}", module="auto_memory")

    _save_counter()
    if stored_count:
        log.info(f"Auto-saved {stored_count} facts from {len(exchanges)} exchanges",
                 module="auto_memory")

    return {"stored": stored_count, "facts": facts}


def _memory_scheduler_loop() -> None:
    """Daemon thread: auto-save every AUTO_SAVE_INTERVAL seconds when not idle."""
    global _scheduler_running
    log.info(f"Auto-save scheduler started (interval={AUTO_SAVE_INTERVAL}s, idle={IDLE_PAUSE_THRESHOLD}s)",
             module="auto_memory")

    while _scheduler_running:
        time.sleep(AUTO_SAVE_INTERVAL)
        if not _scheduler_running:
            break

        try:
            from tools.consolidation import is_idle
            if is_idle(IDLE_PAUSE_THRESHOLD):
                continue

            # Skip if nothing new to save — don't waste cycles on empty buffer
            with _buffer_lock:
                if not _conversation_buffer:
                    continue

            auto_save_from_conversation()
        except Exception as e:
            log.warn(f"Auto-save tick failed: {e}", module="auto_memory")


def start_auto_save_scheduler() -> None:
    """Start the auto-save daemon thread. Safe to call multiple times."""
    global _scheduler_thread, _scheduler_running
    if _scheduler_thread and _scheduler_thread.is_alive():
        return

    _scheduler_running = True
    _scheduler_thread = threading.Thread(
        target=_memory_scheduler_loop,
        daemon=True,
        name="auto-save-scheduler",
    )
    _scheduler_thread.start()
    log.info("Auto-save scheduler daemon started", module="auto_memory")


def get_stats() -> dict:
    """Štatistiky auto-memory."""
    return dict(_counter)
