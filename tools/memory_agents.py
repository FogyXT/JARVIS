"""
Standby Neuron Agents v2 — dynamický, neurónom-inšpirovaný pamäťový systém.

Architektúra:
- Agenti = JSON súbory na disku (DEEP_SLEEP = 0 RAM, 0 tokenov)
- Dynamické spawnovanie — konsolidácia vytvára nových agentov z memory clusterov
- Granulárne triggre — úzke regex/embedding vzory namiesto širokých keywords
- Consensus voting — viacero agentov skóruje query, top K sa zobudí
- Neurogenesis — automatická detekcia nových domén

Stavy agenta:
  DEEP_SLEEP   → len JSON na disku (0 RAM, 0 tokenov)
  LIGHT_SLEEP  → centroid v RAM (~3KB) pre rýchly scoring
  ACTIVE       → spracúva úlohu (spotrebúva tokeny)
  DEAD         → neaktívny, kandidát na odstránenie

Použitie:
    from tools.memory_agents import query_memory, store_memory, neurogenesis
    results = query_memory("What Python bug did we fix?")
    store_memory("bug_fix", "Fixed memory leak in API", "Python asyncio memory leak")
    neurogenesis()  # spawn new agents from memory clusters
"""

import os
import re
import json
import time
import math
from typing import Optional, Any
from dataclasses import dataclass, field, asdict

import numpy as np

from tools.jarvis_logging import log


# ── Config ────────────────────────────────────────────────────────────────

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENTS_DIR = os.path.join(PROJECT_ROOT, "agents")
BLACKBOARD_FILE = os.path.join(AGENTS_DIR, "blackboard.json")
ROUTER_CONFIG_FILE = os.path.join(AGENTS_DIR, "router.json")

# Wake thresholds
LIGHT_SLEEP_THRESHOLD = 0.15   # min score to stay in LIGHT_SLEEP (centroid in RAM)
WAKE_THRESHOLD = 0.30          # min score to wake to ACTIVE
MAX_ACTIVE_AGENTS = 3          # max agents active at once (consensus panel)
MIN_MEMORIES_FOR_SPAWN = 5     # min cluster size to spawn a new agent
AGENT_PRUNE_DAYS = 30          # agents not woken for N days → DEAD → removed

os.makedirs(AGENTS_DIR, exist_ok=True)


# ── Agent Config (serializable to JSON) ──────────────────────────────────

@dataclass
class AgentConfig:
    """Plne serializovateľná konfigurácia agenta. V DEEP_SLEEP je toto jediné čo existuje."""
    name: str                        # unique slug, e.g. "tech_python_async"
    domain: str                      # broad category: "tech", "personal", "projects"
    description: str                 # what this agent specializes in
    trigger_patterns: list[str] = field(default_factory=list)  # regex patterns that wake it
    centroid: Optional[list[float]] = None  # domain centroid (serialized)
    centroid_items: int = 0          # how many items contributed to centroid
    state: str = "DEEP_SLEEP"        # DEEP_SLEEP | LIGHT_SLEEP | ACTIVE | DEAD
    spawn_source: str = "manual"     # "manual" | "neurogenesis" | "consolidation"
    created_at: float = field(default_factory=time.time)
    last_woken: float = 0.0
    wake_count: int = 0
    success_count: int = 0           # times its results were useful

    # Runtime-only (not serialized)
    _centroid_np: Optional[np.ndarray] = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("_centroid_np", None)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "AgentConfig":
        d.pop("_centroid_np", None)
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ── Agent Store (disk-based persistence) ─────────────────────────────────

class AgentStore:
    """Spravuje agentov na disku. DEEP_SLEEP agenti sú len JSON súbory."""

    def __init__(self):
        self.agents: dict[str, AgentConfig] = {}  # name → AgentConfig (loaded agents)
        os.makedirs(AGENTS_DIR, exist_ok=True)

    def _agent_path(self, name: str) -> str:
        safe = re.sub(r'[^a-z0-9_-]', '_', name.lower())
        return os.path.join(AGENTS_DIR, f"{safe}.json")

    def save(self, agent: AgentConfig):
        """Ulož agenta na disk (DEEP_SLEEP)."""
        path = self._agent_path(agent.name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(agent.to_dict(), f, ensure_ascii=False, indent=2)
        self.agents[agent.name] = agent

    def load(self, name: str) -> Optional[AgentConfig]:
        """Načítaj agenta z disku do LIGHT_SLEEP (centroid v RAM)."""
        if name in self.agents:
            agent = self.agents[name]
            if agent.state == "DEAD":
                return None
            # Promote DEEP_SLEEP → LIGHT_SLEEP
            if agent.state == "DEEP_SLEEP":
                agent.state = "LIGHT_SLEEP"
                if agent.centroid and len(agent.centroid) > 0:
                    agent._centroid_np = np.array(agent.centroid, dtype=np.float32)
            return agent

        path = self._agent_path(name)
        if not os.path.exists(path):
            return None

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        agent = AgentConfig.from_dict(data)
        agent.state = "LIGHT_SLEEP"

        # Load centroid into numpy
        if agent.centroid and len(agent.centroid) > 0:
            agent._centroid_np = np.array(agent.centroid, dtype=np.float32)

        self.agents[name] = agent
        return agent

    def load_all_light_sleep(self) -> list[AgentConfig]:
        """Načítaj všetkých non-DEAD agentov do LIGHT_SLEEP."""
        if not os.path.isdir(AGENTS_DIR):
            return []

        loaded = []
        for fname in sorted(os.listdir(AGENTS_DIR)):
            if fname.endswith(".json") and fname not in ("blackboard.json", "router.json"):
                name = fname[:-5]
                agent = self.load(name)
                if agent and agent.state != "DEAD":
                    loaded.append(agent)
        return loaded

    def delete(self, name: str):
        """Odstráň agenta z disku aj RAM."""
        path = self._agent_path(name)
        if os.path.exists(path):
            os.remove(path)
        self.agents.pop(name, None)
        log.info(f"Agent pruned: {name}", module="agents")

    def list_all(self) -> list[dict]:
        """Vypíš všetkých agentov (z disku)."""
        result = []
        if not os.path.isdir(AGENTS_DIR):
            return result
        for fname in sorted(os.listdir(AGENTS_DIR)):
            if fname.endswith(".json") and fname not in ("blackboard.json", "router.json"):
                path = os.path.join(AGENTS_DIR, fname)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    result.append({
                        "name": data.get("name", fname),
                        "domain": data.get("domain", "?"),
                        "state": data.get("state", "DEEP_SLEEP"),
                        "wake_count": data.get("wake_count", 0),
                        "spawn_source": data.get("spawn_source", "?"),
                        "trigger_count": len(data.get("trigger_patterns", [])),
                    })
                except Exception:
                    pass
        return result

    def count_by_state(self) -> dict:
        counts = {"DEEP_SLEEP": 0, "LIGHT_SLEEP": 0, "ACTIVE": 0, "DEAD": 0}
        # Count from RAM (loaded agents) first, then disk for DEEP_SLEEP
        disk_agents = {a["name"]: a for a in self.list_all()}
        for name, agent in self.agents.items():
            counts[agent.state] = counts.get(agent.state, 0) + 1
            disk_agents.pop(name, None)
        # Remaining on disk are DEEP_SLEEP
        for name, info in disk_agents.items():
            state = info.get("state", "DEEP_SLEEP")
            counts[state] = counts.get(state, 0) + 1
        return counts


# ── Blackboard (persistent inter-agent messages) ──────────────────────────

class Blackboard:
    """Perzistentná tabuľa pre riedku medzi-agentovú komunikáciu."""

    def __init__(self):
        self.messages: list[dict] = []
        self._load()

    def _load(self):
        if os.path.exists(BLACKBOARD_FILE):
            try:
                with open(BLACKBOARD_FILE, "r", encoding="utf-8") as f:
                    self.messages = json.load(f)
            except Exception:
                self.messages = []

    def _save(self):
        # Keep only recent messages (last 100)
        self.messages = self.messages[-100:]
        with open(BLACKBOARD_FILE, "w", encoding="utf-8") as f:
            json.dump(self.messages, f, ensure_ascii=False, indent=2)

    def post(self, from_agent: str, to_agent: str, content: str):
        msg = {"from": from_agent, "to": to_agent, "content": content,
               "timestamp": time.time()}
        self.messages.append(msg)
        self._save()
        log.debug(f"BB: {from_agent} → {to_agent}: {content[:60]}", module="agents")

    def read(self, agent_name: str, max_age: float = 3600) -> list[dict]:
        cutoff = time.time() - max_age
        return [m for m in self.messages
                if m["to"] in (agent_name, "all")
                and m["timestamp"] > cutoff]

    def stats(self) -> dict:
        return {"pending_messages": len(self.messages)}


# ── Neuron Router ────────────────────────────────────────────────────────

class NeuronRouter:
    """Mozog systému. Rozhoduje ktoré neuróny sa zobudia."""

    def __init__(self, store: AgentStore, blackboard: Blackboard):
        self.store = store
        self.blackboard = blackboard

    def _score_agent(self, agent: AgentConfig, text: str) -> float:
        """Vypočítaj relevance score 0-1 pre agenta a text."""
        text_lower = text.lower()
        score = 0.0
        components = 0

        # 1. Trigger pattern matching — count how many patterns fire
        pattern_matches = 0
        for pattern in agent.trigger_patterns:
            try:
                if re.search(pattern, text_lower):
                    pattern_matches += 1
            except re.error:
                pass
        if agent.trigger_patterns:
            # Weight: 0.5 per pattern match, capped at 1.0
            # 1 match = 0.5, 2+ matches = 1.0 — enough to wake from patterns alone
            pattern_score = min(1.0, pattern_matches * 0.5)
            score += pattern_score
            components += 1

        # 2. Embedding similarity k centroidu (ak existuje)
        if agent._centroid_np is not None and agent.centroid_items > 0:
            try:
                from tools.episodic_memory import _embed_text
                query_emb = _embed_text(text)
                c = agent._centroid_np
                c_norm = c / (np.linalg.norm(c) + 1e-8)
                q_norm = query_emb / (np.linalg.norm(query_emb) + 1e-8)
                sim = float(np.dot(c_norm, q_norm))
                score += max(0, sim)
                components += 1
            except Exception:
                pass

        # 3. Recent activity bonus (agents woken recently are slightly favored)
        if agent.wake_count > 0:
            recency = min(0.1, agent.wake_count * 0.01)
            score += recency
            components += 1

        return round(score / max(components, 1), 4)

    def wake_agents(self, text: str, max_wake: int = MAX_ACTIVE_AGENTS) -> list[AgentConfig]:
        """Zobuď najrelevantnejších agentov. Consensus: každý skóruje, top K vyhráva."""
        # Load all agents to LIGHT_SLEEP for scoring
        all_agents = self.store.load_all_light_sleep()

        # Score every agent
        scored = []
        for agent in all_agents:
            s = self._score_agent(agent, text)
            if s >= WAKE_THRESHOLD:
                scored.append((s, agent))

        # Sort by score, wake top K
        scored.sort(key=lambda x: x[0], reverse=True)
        woken = []
        for score, agent in scored[:max_wake]:
            agent.state = "ACTIVE"
            agent.wake_count += 1
            agent.last_woken = time.time()
            woken.append(agent)
            log.debug(f"Woke {agent.name} (score={score:.3f}, wake #{agent.wake_count})",
                     module="agents")

        # Keep others in LIGHT_SLEEP or demote to DEEP_SLEEP
        for score, agent in scored[max_wake:]:
            if score >= LIGHT_SLEEP_THRESHOLD:
                agent.state = "LIGHT_SLEEP"
            else:
                agent.state = "DEEP_SLEEP"
                agent._centroid_np = None  # free RAM
                self.store.save(agent)     # persist and remove from RAM
                if agent.name in self.store.agents:
                    pass  # keep in dict but without centroid

        return woken

    def sleep_all(self):
        """Uspi všetkých ACTIVE agentov späť do LIGHT_SLEEP."""
        for agent in list(self.store.agents.values()):
            if agent.state == "ACTIVE":
                agent.state = "LIGHT_SLEEP"

    def _update_centroid(self, agent: AgentConfig):
        """Prepočítaj centroid agenta z EpisodicBufferu."""
        try:
            from tools.episodic_memory import _embed_text, get_buffer
            buf = get_buffer()
            if buf is None:
                return

            texts = []
            for item in buf.working + buf.episodic:
                item_text = f"{item.key}: {item.value}".lower()
                # Check if item matches agent's triggers
                for pattern in agent.trigger_patterns:
                    try:
                        if re.search(pattern, item_text):
                            texts.append(f"{item.key}: {item.value}")
                            break
                    except re.error:
                        pass

            if texts:
                embs = np.array([_embed_text(t) for t in texts])
                agent.centroid = np.mean(embs, axis=0).tolist()
                agent._centroid_np = np.mean(embs, axis=0)
                agent.centroid_items = len(texts)
                agent.state = "LIGHT_SLEEP"
                self.store.save(agent)
                log.debug(f"Centroid updated: {agent.name} ({len(texts)} items)",
                         module="agents")
        except Exception as e:
            log.warn(f"Centroid update failed for {agent.name}: {e}", module="agents")


# ── Neurogenesis (dynamic agent spawning) ─────────────────────────────────

def neurogenesis(store: AgentStore = None, router: NeuronRouter = None) -> dict:
    """Deteguj nové domény z memory clusterov a spawnuj agentov.

    Volá sa z konsolidácie (consolidate_full).
    """
    if store is None:
        store = _get_store()
    if router is None:
        router = _get_router()

    try:
        from tools.episodic_memory import get_buffer
        buf = get_buffer()
        if buf is None or buf.size()["total"] < MIN_MEMORIES_FOR_SPAWN:
            return {"spawned": 0, "reason": "not enough memories"}
    except ImportError:
        return {"spawned": 0, "reason": "buffer unavailable"}

    # Get all existing agent trigger patterns to avoid duplicates
    existing_patterns = set()
    for agent in store.load_all_light_sleep():
        for p in agent.trigger_patterns:
            existing_patterns.add(p)

    spawned = 0

    # Strategy 1: Tag-based spawning
    # Group buffer items by tags, spawn if cluster is big enough
    tag_clusters: dict[str, list] = {}
    for item in buf.working + buf.episodic:
        for tag in (item.tags or []):
            if tag not in ("test", "personal", "tech", "projects"):
                if tag not in tag_clusters:
                    tag_clusters[tag] = []
                tag_clusters[tag].append(item)

    for tag, items in tag_clusters.items():
        if len(items) >= MIN_MEMORIES_FOR_SPAWN:
            agent_name = f"auto_{tag}_{len(items)}items"
            if any(a["name"] == agent_name for a in store.list_all()):
                continue

            # Build trigger patterns from item keys
            triggers = []
            for item in items:
                # Create regex from key words
                key_words = re.findall(r'\w+', item.key.lower())
                if key_words:
                    triggers.append(r'\b' + r'\b.*\b'.join(key_words[:3]) + r'\b')

            # Deduplicate and keep top 5
            triggers = list(set(triggers))[:5]

            agent = AgentConfig(
                name=agent_name,
                domain=tag,
                description=f"Auto-spawned agent for {tag} ({len(items)} memories)",
                trigger_patterns=triggers,
                state="DEEP_SLEEP",
                spawn_source="neurogenesis",
            )
            store.save(agent)
            spawned += 1
            log.info(f"Neurogenesis: spawned {agent_name} ({len(items)} items, {len(triggers)} triggers)",
                    module="agents")

    # Strategy 2: Embedding-cluster spawning
    # If consolidation finds semantic clusters, spawn agents for them
    # (done via consolidate_full → _stage_cluster → neurogenesis callback)

    # Prune DEAD agents (load directly from disk, bypassing DEAD filter)
    now = time.time()
    for fname in os.listdir(AGENTS_DIR):
        if not fname.endswith(".json") or fname in ("blackboard.json", "router.json"):
            continue
        path = os.path.join(AGENTS_DIR, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("state") == "DEAD":
                last_woken = data.get("last_woken", 0)
                if (now - last_woken) > AGENT_PRUNE_DAYS * 24 * 3600:
                    store.delete(data["name"])
        except Exception:
            pass

    return {"spawned": spawned, "tag_clusters": len(tag_clusters)}


# ── High-Level API ────────────────────────────────────────────────────────

def query_memory(query: str, k: int = 5) -> dict:
    """Hlavné API pre vyhľadávanie — agenti sa zobudia, nájdu, odhlasujú.

    Returns:
        {"results": [...], "agents_used": [...], "consensus_score": float}
    """
    router = _get_router()
    woken = router.wake_agents(query, max_wake=MAX_ACTIVE_AGENTS)

    results = []
    agents_used = []

    for agent in woken:
        agents_used.append({"name": agent.name, "domain": agent.domain,
                            "wake_count": agent.wake_count})

        # Agent retrieves from its domain
        try:
            from tools.rag_memory import _hybrid_search
            # Use agent's trigger patterns to filter
            domain_results = _hybrid_search(query, k=max(2, k // len(woken)),
                                           min_score=0.0)
            for r in domain_results:
                r["agent"] = agent.name
                r["domain"] = agent.domain
            results.extend(domain_results)
        except Exception as e:
            log.warn(f"Agent {agent.name} search failed: {e}", module="agents")

    # Cross-agent: check blackboard
    for agent in woken:
        msgs = router.blackboard.read(agent.name)
        if msgs:
            results.append({
                "text": f"💬 {len(msgs)} cross-agent messages",
                "score": 100, "agent": "blackboard", "domain": "cross-domain",
            })

    # Sort by score, deduplicate
    results.sort(key=lambda x: x.get("score", 0), reverse=True)
    seen = set()
    unique = []
    for r in results:
        key = r.get("text", "")[:80]
        if key not in seen:
            seen.add(key)
            unique.append(r)

    # Post cross-agent messages for future
    if len(woken) >= 2:
        for i, a1 in enumerate(woken):
            for a2 in woken[i+1:]:
                router.blackboard.post(a1.name, a2.name,
                                      f"Co-woken on query: {query[:80]}")

    router.sleep_all()

    return {
        "results": unique[:k],
        "agents_used": agents_used,
        "total_agents_scored": len(router.store.list_all()),
        "consensus_size": len(woken),
    }


def store_memory(key: str, value: str, text: str = None) -> dict:
    """Ulož spomienku cez agentov — tí ju obohatia o doménu."""
    router = _get_router()
    search_text = text or f"{key}: {value}"
    woken = router.wake_agents(search_text, max_wake=MAX_ACTIVE_AGENTS)

    enrichments = []
    total_boost = 0.0

    for agent in woken:
        boost = 0.0
        for pattern in agent.trigger_patterns:
            try:
                if re.search(pattern, search_text.lower()):
                    boost += 0.05
            except re.error:
                pass
        boost = min(0.3, boost)
        total_boost += boost
        enrichments.append({
            "agent": agent.name, "domain": agent.domain,
            "importance_boost": round(boost, 3),
        })

    # Actually save via raw memory (all 4 tiers)
    from tools.memory import memory
    result = memory("save", key, value)

    # Cross-agent notification
    if len(woken) >= 2:
        for i, a1 in enumerate(woken):
            for a2 in woken[i+1:]:
                router.blackboard.post(a1.name, a2.name,
                                      f"Shared memory: [{key}] — relevant to your domain")

    router.sleep_all()

    return {
        "saved": key,
        "agents_used": [a.name for a in woken],
        "enrichments": enrichments,
        "total_boost": round(total_boost, 3),
    }


def update_all_centroids():
    """Prepočítaj centroidy všetkých LIGHT_SLEEP agentov."""
    store = _get_store()
    router = _get_router()
    for agent in store.load_all_light_sleep():
        router._update_centroid(agent)
    log.info(f"Centroids updated", module="agents")


def get_agents_stats() -> list[dict]:
    return _get_store().list_all()


# ── Default Agent Spawning ────────────────────────────────────────────────

def _spawn_defaults(store: AgentStore):
    """Spawni predvolených agentov ak ešte neexistujú."""
    defaults = [
        AgentConfig(
            name="personal_user", domain="personal",
            description="User identity, preferences, personal facts",
            trigger_patterns=[
                r'\b(fogy|user|name|age|location|favorite|color|prefer|like|hate)\b',
                r'\b(my|mine|moje|môj|mám rád|nepáči)\b',
                r'\b(family|friend|health|remember.*personal)\b',
            ],
            state="DEEP_SLEEP", spawn_source="manual",
        ),
        AgentConfig(
            name="tech_python", domain="technical",
            description="Python programming, libraries, bugs, async",
            trigger_patterns=[
                r'\b(python|asyncio|async|await|numpy|pandas|spacy|fastapi|flask)\b',
                r'\b(bug.*fix|memory leak|import error|typeerror|attributeerror)\b',
                r'\b(pip install|requirements|venv|conda|poetry)\b',
            ],
            state="DEEP_SLEEP", spawn_source="manual",
        ),
        AgentConfig(
            name="tech_infra", domain="technical",
            description="Infrastructure: ChromaDB, APIs, Docker, databases",
            trigger_patterns=[
                r'\b(chromadb|qdrant|pinecone|vector|embedding|database|sql)\b',
                r'\b(api|rest|graphql|endpoint|server|deploy|docker|container)\b',
                r'\b(hybrid search|bm25|dense|sparse|rerank|min_score)\b',
            ],
            state="DEEP_SLEEP", spawn_source="manual",
        ),
        AgentConfig(
            name="projects_jarvis", domain="projects",
            description="JARVIS development, architecture, memory system",
            trigger_patterns=[
                r'\b(jarvis|claude|assistant|voice|speech|tts|stt)\b',
                r'\b(memory.*tier|episodic|semantic|knowledge graph|cold archive)\b',
                r'\b(consolidation|decay|reinforcement|promotion|archiv)\b',
                r'\b(standby.*neuron|agent.*spawn|neurogenesis|blackboard)\b',
            ],
            state="DEEP_SLEEP", spawn_source="manual",
        ),
        AgentConfig(
            name="research_alzheimer", domain="projects",
            description="Alzheimer memory prosthesis research",
            trigger_patterns=[
                r'\b(alzheimer|dementia|memory.*loss|memory.*prosthesis|brain.*interface)\b',
                r'\b(patient|clinical|neural|hippocamp|implant|prosthetic)\b',
            ],
            state="DEEP_SLEEP", spawn_source="manual",
        ),
        AgentConfig(
            name="tools_web", domain="technical",
            description="Web UI, JavaScript, CSS, browser automation",
            trigger_patterns=[
                r'\b(web.*ui|frontend|javascript|css|html|browser|script\.js)\b',
                r'\b(upload|preview|modal|sidebar|dropdown|stream|sse)\b',
                r'\b(pyautogui|selenium|webbrowser|control_browser)\b',
            ],
            state="DEEP_SLEEP", spawn_source="manual",
        ),
    ]

    existing = {a["name"] for a in store.list_all()}
    spawned = 0
    for agent in defaults:
        if agent.name not in existing:
            store.save(agent)
            spawned += 1

    if spawned:
        log.info(f"Spawned {spawned} default agents", module="agents")
    return spawned


# ── Singletons ────────────────────────────────────────────────────────────

_store: Optional[AgentStore] = None
_router: Optional[NeuronRouter] = None
_blackboard: Optional[Blackboard] = None


def _get_store() -> AgentStore:
    global _store
    if _store is None:
        _store = AgentStore()
        _spawn_defaults(_store)
    return _store


def _get_blackboard() -> Blackboard:
    global _blackboard
    if _blackboard is None:
        _blackboard = Blackboard()
    return _blackboard


def _get_router() -> NeuronRouter:
    global _router
    if _router is None:
        _router = NeuronRouter(_get_store(), _get_blackboard())
    return _router
