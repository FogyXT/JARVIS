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

from tools.jarvis_logging import log


# ── Config ────────────────────────────────────────────────────────────────

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COUNTER_FILE = os.path.join(PROJECT_ROOT, "auto_memory_counter.json")

# How often to run consolidation (every N calls)
CONSOLIDATE_EVERY = 10

# Patterns that indicate important facts worth storing
FACT_PATTERNS = [
    # Rozhodnutia
    (r"(?i)(rozhodli|decided|chose|picked|going with|will use)\s+.+", "decision", 0.7),
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


# ── Fact Extraction ───────────────────────────────────────────────────────

def _extract_facts(text: str) -> list[dict]:
    """Extrahuj dôležité fakty z textu pomocou patternov."""
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
                if len(content) < 8 or len(content) > 300:
                    continue

                # Clean up
                content = content.strip(".,;:!?\"' \t\n")
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
                  context: str = "") -> dict:
    """Automaticky ulož dôležité fakty z konverzácie.

    Volaj po každej výmene (user message + assistant response).

    Returns:
        {"stored": N, "facts": [...], "consolidated": bool}
    """
    global _counter
    _counter["calls"] += 1

    # Combine all text
    combined = f"{user_message} {assistant_response} {context}"

    # Extract facts
    facts = _extract_facts(combined)
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


def get_stats() -> dict:
    """Štatistiky auto-memory."""
    return dict(_counter)
