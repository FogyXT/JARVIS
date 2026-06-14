"""
Context Injection Contract — definuje čo ide do LLM context window pri query.

Najťažšia otázka memory systému: pri retrieve, čo presne pošleme LLM-ke?
Koľko tokenov to zje? V akom formáte?

Tento modul odpovedá na túto otázku.

Kontrakt:
  1. Episodic Buffer → top 3 relevantné fakty, max 150 znakov každý
  2. Semantic Store → top 2 výsledky hybrid search, max 200 znakov každý
  3. Knowledge Graph → related entities, max 100 znakov
  4. Celkový budget: 800 tokenov (~600 words) na memory context
  5. Formát: štruktúrovaný, prioritizovaný, s relevance scores

Použitie:
    from tools.context_builder import build_context
    ctx = build_context("What Python bug did we fix?")
    # ctx je pripravený string pre vloženie do system promptu alebo user message
"""

import time

from tools.jarvis_logging import log


# ── Budget ────────────────────────────────────────────────────────────────

MAX_CONTEXT_TOKENS = 800      # max tokenov pre memory context
MAX_EPISODIC_CHARS = 150      # max znakov na episodický fakt
MAX_SEMANTIC_CHARS = 200      # max znakov na sémantický výsledok
MAX_KG_CHARS = 100            # max znakov na KG entitu
MAX_EPISODIC_ITEMS = 3        # koľko faktov z episodického bufferu
MAX_SEMANTIC_ITEMS = 2        # koľko výsledkov zo semantic search
MAX_KG_ITEMS = 5              # koľko KG entít


# ── Build Context ─────────────────────────────────────────────────────────

def build_context(query: str, include_kg: bool = True) -> str:
    """Postav context pre LLM z relevantných spomienok.

    Args:
        query: Užívateľský dopyt
        include_kg: Či zahrnúť Knowledge Graph kontext

    Returns:
        Formátovaný string pripravený pre context window.
        Prázdny string ak nič nenájdené.
    """
    sections = []
    total_chars = 0

    # 1. Episodic Buffer — najrýchlejší, najrelevantnejší
    try:
        from tools.episodic_memory import get_buffer
        buf = get_buffer()
        if buf:
            results = buf.retrieve(query=query, k=MAX_EPISODIC_ITEMS)
            if results:
                lines = ["[Recent & relevant]"]
                for r in results:
                    text = r["value"][:MAX_EPISODIC_CHARS]
                    lines.append(f"  • {text} (relevance: {r['score']:.0%})")
                    total_chars += len(text)
                sections.append("\n".join(lines))
    except Exception as e:
        log.debug(f"Episodic context failed: {e}", module="context_builder")

    # 2. Semantic Store — hlbšie, širšie vyhľadávanie
    try:
        from tools.rag_memory import _hybrid_search
        results = _hybrid_search(query, k=MAX_SEMANTIC_ITEMS, min_score=0.3)
        if results:
            lines = ["[From knowledge base]"]
            for r in results:
                text = r["text"][:MAX_SEMANTIC_CHARS]
                source = r["metadata"].get("source", "?")
                lines.append(f"  • {text} (source: {source})")
                total_chars += len(text)
            sections.append("\n".join(lines))
    except Exception as e:
        log.debug(f"Semantic context failed: {e}", module="context_builder")

    # 3. Knowledge Graph — vzťahy a súvislosti
    if include_kg:
        try:
            from tools.knowledge_graph import get_graph
            kg = get_graph()
            if kg and kg.graph.number_of_nodes() > 0:
                ctx = kg.get_context(query, max_hops=1)
                if ctx and len(ctx) > 10:
                    # Skráť na budget
                    lines = ctx.split("\n")[:MAX_KG_ITEMS + 1]  # +1 for header
                    kg_text = "\n".join(lines)[:MAX_KG_CHARS * MAX_KG_ITEMS]
                    sections.append(kg_text)
                    total_chars += len(kg_text)
        except Exception as e:
            log.debug(f"KG context failed: {e}", module="context_builder")

    if not sections:
        return ""

    # Header
    result = "── Memory context ──\n" + "\n\n".join(sections)

    # Budget check
    estimated_tokens = total_chars // 4
    if estimated_tokens > MAX_CONTEXT_TOKENS:
        log.debug(f"Context over budget: ~{estimated_tokens} tokens (max {MAX_CONTEXT_TOKENS})",
                 module="context_builder")

    return result


def build_context_compact(query: str) -> str:
    """Kompaktná verzia — max 300 tokenov. Pre rýchle queries."""
    sections = []

    try:
        from tools.episodic_memory import get_buffer
        buf = get_buffer()
        if buf:
            results = buf.retrieve(query=query, k=2)
            if results:
                facts = "; ".join(r["value"][:100] for r in results)
                sections.append(f"[Memory] {facts}")
    except Exception:
        pass

    try:
        from tools.rag_memory import _hybrid_search
        results = _hybrid_search(query, k=1, min_score=0.4)
        if results:
            sections.append(f"[Knowledge] {results[0]['text'][:150]}")
    except Exception:
        pass

    return " | ".join(sections) if sections else ""


def estimate_context_tokens(query: str) -> dict:
    """Odhadni koľko tokenov by context zjedol bez toho aby sa reálne postavil."""
    ctx = build_context(query)
    if not ctx:
        return {"tokens": 0, "chars": 0, "sections": 0}

    chars = len(ctx)
    tokens = chars // 4
    sections = ctx.count("[")  # rough count of sections by header markers

    return {
        "tokens": tokens,
        "chars": chars,
        "sections": sections,
        "budget": MAX_CONTEXT_TOKENS,
        "within_budget": tokens <= MAX_CONTEXT_TOKENS,
    }
