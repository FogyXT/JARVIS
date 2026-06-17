"""
Shared LLM helpers — DeepSeek V4 Flash and Claude Haiku.
Import this from auto_memory, consolidation, or web_ui to avoid circular imports.

All functions return empty string on failure (never raise).
"""

import os
import sys

# Ensure the parent directory is importable (for running standalone)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.jarvis_logging import log


def call_deepseek(prompt: str, max_tokens: int = 300, temperature: float = 0.1) -> str:
    """Call DeepSeek V4 Flash for fast, cheap responses.

    Returns empty string if API key missing or call fails.
    """
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        log.warn("DEEPSEEK_API_KEY not set — LLM call skipped", module="llm_helper")
        return ""

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
            stream=False,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        log.warn(f"DeepSeek call failed: {e}", module="llm_helper")
        return ""


def call_haiku(prompt: str, max_tokens: int = 300, temperature: float = 0.1) -> str:
    """Call Claude Haiku as fallback when DeepSeek is unavailable.

    Returns empty string if API key missing or call fails.
    """
    return _call_anthropic(prompt, "claude-haiku-4-5-20251001", max_tokens, temperature)


def call_sonnet(prompt: str, max_tokens: int = 300, temperature: float = 0.1) -> str:
    """Call Claude Sonnet 4.6 — matches Jarvis mode model.

    Returns empty string if API key missing or call fails.
    """
    return _call_anthropic(prompt, "claude-sonnet-4-6", max_tokens, temperature)


def _call_anthropic(prompt: str, model: str, max_tokens: int, temperature: float) -> str:
    """Internal: call Anthropic Claude API."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return ""

    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system="Return only the requested output. No markdown, no commentary.",
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()
    except Exception:
        return ""


def call_llm(prompt: str, model: str = "deepseek-chat",
             max_tokens: int = 2000, temperature: float = 0.1) -> str:
    """Route to the right LLM based on model name.

    model options: "deepseek-chat", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"
    Returns empty string on failure.
    """
    if "deepseek" in model:
        return call_deepseek(prompt, max_tokens, temperature)
    elif "sonnet" in model or "claude-sonnet" in model:
        return call_sonnet(prompt, max_tokens, temperature)
    elif "haiku" in model:
        return call_haiku(prompt, max_tokens, temperature)
    else:
        # Unknown model — try DeepSeek first, then Sonnet fallback
        result = call_deepseek(prompt, max_tokens, temperature)
        if not result:
            result = call_sonnet(prompt, max_tokens, temperature)
        return result
