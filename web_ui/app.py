import os
import re
import sys
import json
import base64
import difflib
import importlib.util
import traceback
import time
import tempfile
from datetime import datetime

from flask import Flask, request, jsonify, Response, render_template
from anthropic import Anthropic
from dotenv import load_dotenv

# Make sure we can import from project root
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

load_dotenv()

# ---------------------------------------------------------------------------
# Import EXACT Jarvis system prompt and tools from jarvis.py
# ---------------------------------------------------------------------------
# Dynamically load jarvis.py without running its main()
_jarvis_spec = importlib.util.spec_from_file_location(
    "jarvis_module", os.path.join(_PROJECT_ROOT, "jarvis.py")
)
jarvis_mod = importlib.util.module_from_spec(_jarvis_spec)
_jarvis_spec.loader.exec_module(jarvis_mod)

JARVIS_SYSTEM_PROMPT = jarvis_mod.SYSTEM_PROMPT
JARVIS_TOOLS = jarvis_mod.AVAILABLE_TOOLS

print(f"✅ Imported Jarvis system prompt ({len(JARVIS_SYSTEM_PROMPT)} chars)")
print(f"✅ Imported Jarvis tools ({len(JARVIS_TOOLS)} definitions)")

# ---------------------------------------------------------------------------
# App init
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500 MB (lokálne bez limitu)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0  # no cache on static files during dev
app.config["TEMPLATES_AUTO_RELOAD"] = True

# ---------------------------------------------------------------------------
# Auth — simple login for remote access
# ---------------------------------------------------------------------------
import secrets
import time
from collections import defaultdict

app.secret_key = os.getenv("FLASK_SECRET_KEY", secrets.token_hex(32))
# Secure session cookies (HTTPS via ngrok)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Strict"
app.config["SESSION_COOKIE_SECURE"] = False  # False because Flask serves HTTP (ngrok adds HTTPS)

WEBUI_USER = os.getenv("WEBUI_USER", "")
WEBUI_PASS = os.getenv("WEBUI_PASS", "")
AUTH_ENABLED = bool(WEBUI_USER and WEBUI_PASS)

# Rate limiting: max attempts per IP
LOGIN_RATE_LIMIT = int(os.getenv("LOGIN_RATE_LIMIT", "5"))   # attempts
LOGIN_RATE_WINDOW = int(os.getenv("LOGIN_RATE_WINDOW", "60")) # seconds
_login_attempts = defaultdict(list)  # {ip: [timestamp, ...]}

def _check_rate_limit(ip):
    """Return (allowed: bool, wait_seconds: int)"""
    now = time.time()
    attempts = [t for t in _login_attempts[ip] if now - t < LOGIN_RATE_WINDOW]
    _login_attempts[ip] = attempts
    if len(attempts) >= LOGIN_RATE_LIMIT:
        wait = int(LOGIN_RATE_WINDOW - (now - attempts[0]) + 1)
        return False, max(1, wait)
    return True, 0

if AUTH_ENABLED:
    print(f"🔐 Auth enabled: user='{WEBUI_USER}' — rate limit {LOGIN_RATE_LIMIT}/{LOGIN_RATE_WINDOW}s")
else:
    print("⚠️  Auth DISABLED — set WEBUI_USER + WEBUI_PASS in .env to enable login")

def login_required(f):
    """Decorator: redirect to /login if not authenticated."""
    from functools import wraps
    @wraps(f)
    def wrapped(*args, **kwargs):
        if AUTH_ENABLED and not session.get("logged_in"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "Unauthorized", "login_required": True}), 401
            return redirect("/login")
        return f(*args, **kwargs)
    return wrapped

from flask import session, redirect


# Claude client via DeepSeek proxy (used by Jarvis mode if no direct Anthropic key)
claude = Anthropic()
CLAUDE_MODEL = "claude-sonnet-4-6"

# Direct Anthropic client for Haiku (cheap, vision, tools)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
HAIKU_MODEL = "claude-haiku-4-5-20251001"
haiku_client = Anthropic(api_key=ANTHROPIC_API_KEY, base_url="https://api.anthropic.com") if ANTHROPIC_API_KEY else None
if haiku_client:
    print(f"🧠 Haiku client ready ({HAIKU_MODEL})")
else:
    print("⚠️ Haiku client not available (no direct Anthropic API key)")

# Try loading DeepSeek key for coding mode
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_AVAILABLE = bool(DEEPSEEK_API_KEY)

# Import Jarvis tools functions for tool dispatch
TOOLS_AVAILABLE = False
try:
    import tools
    TOOLS_AVAILABLE = True
    print(f"🔧 Jarvis tool functions loaded")
except ImportError as e:
    print(f"⚠️ Tools import: {e}")

# ---------------------------------------------------------------------------
# Coding mode — same prompt & tools as Jarvis, but DeepSeek model
# ---------------------------------------------------------------------------
CODING_SYSTEM_PROMPT = JARVIS_SYSTEM_PROMPT  # identical to voice Jarvis


# Convert JARVIS_TOOLS (Anthropic format) to OpenAI function format for DeepSeek
CODING_TOOLS = []
for t in JARVIS_TOOLS:
    # Skip server-side web_search (Anthropic built-in)
    if t.get("type", "").startswith("web_search"):
        continue
    schema = t.get("input_schema", {})
    props = schema.get("properties", {})
    # Convert Anthropic required list to OpenAI required list
    required = schema.get("required", [])
    coding_tool = {
        "type": "function",
        "function": {
            "name": t["name"],
            "description": t.get("description", ""),
            "parameters": {
                "type": "object",
                "properties": props,
            }
        }
    }
    if required:
        coding_tool["function"]["parameters"]["required"] = required
    CODING_TOOLS.append(coding_tool)
print(f"Converted {len(CODING_TOOLS)} Jarvis tools to OpenAI format for DeepSeek")



def _compute_file_diff(path, new_content):
    """Compute diff between existing file and new content. Returns formatted diff string."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            old_content = f.read()
    except (FileNotFoundError, PermissionError):
        return None

    if old_content == new_content:
        return None

    old_lines = old_content.splitlines()
    new_lines = new_content.splitlines()
    diff_lines = list(difflib.unified_diff(
        old_lines, new_lines,
        fromfile=path, tofile=path,
        lineterm=''
    ))
    added = sum(1 for l in diff_lines if l.startswith('+') and not l.startswith('+++'))
    removed = sum(1 for l in diff_lines if l.startswith('-') and not l.startswith('---'))

    preview = '\n'.join(diff_lines[:35])
    if len(diff_lines) > 35:
        preview += f'\n… ({len(diff_lines)} lines total)'

    return f"📝 Diff: +{added}/−{removed} lines\n```diff\n{preview}\n```"


def _summarize_tool_args(name, args):
    """Summarize tool arguments for the task panel display."""
    if name == "file_manager":
        action = args.get("action", "")
        path = args.get("path", "")
        if action == "write":
            return f"{action} {path} ({len(args.get('content',''))} chars)"
        if action == "read":
            return f"{action} {path}"
        if action == "list":
            return f"{action} {path}"
        if action == "delete":
            return f"{action} {path}"
        if action == "create_folder":
            return f"mkdir {path}"
        return f"{action} {path}"
    if name == "execute_command":
        cmd = args.get("command", "")
        return cmd[:80] + ("…" if len(cmd) > 80 else "")
    if name == "web_search":
        return args.get("query", "")[:80]
    if name == "take_screenshot":
        return "screenshot"
    if name == "system_info":
        return f"category: {args.get('category', 'all')}"
    return json.dumps(args)[:120]


def _execute_coding_tool(name, args, session_id="default"):
    """Execute a coding-mode tool. Returns result string."""
    if not TOOLS_AVAILABLE:
        return "Tools unavailable."
    try:
        if name == "file_manager":
            action = args.get("action")
            path = args.get("path")
            content = args.get("content")
            if action == "write" and path and content is not None:
                diff = _compute_file_diff(path, content)
                result = tools.file_manager(action, path, content)
                if diff:
                    return f"{result}\n\n{diff}"
            return tools.file_manager(action, path, content)
        if name == "execute_command":
            return tools.execute_command(args.get("command"), args.get("timeout", 30))
        if name == "web_search":
            return tools.web_search(args.get("query", ""))
        if name == "take_screenshot":
            p = tools.take_screenshot()
            with open(p, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            return f"[SCREENSHOT:data:image/png;base64,{b64}]"
        if name == "system_info":
            return tools.system_info(args.get("category", "all"))
        if name == "instagram_dm":
            return tools.instagram_dm(args["target"], args["message"], args.get("browser"), args.get("attachment_path"))
        if name == "control_browser":
            return tools.control_browser(args.get("actions", []))
        if name == "download_file":
            return tools.download_file(args["url"], args["save_path"])
        if name == "image_search":
            return tools.image_search(args.get("query", ""), int(args.get("count", 3)))
        if name == "search_and_download_image":
            q = args.get("query", "")
            sp = args.get("save_path")
            sid = args.get("session_id")
            if not sp and sid:
                safe = q.replace(" ", "_").replace("/", "_").replace("\\", "_")[:50]
                sp = f"D:/JARVIS/web_ui/uploads/{sid}/images/{safe}.jpg"
            return tools.search_and_download_image(q, sp)
        if name == "memory":
            return tools.memory(args["action"], args.get("key"), args.get("value"))
        if name == "describe_image":
            return _describe_image(args.get("filename", ""), args.get("session_id", ""))
        if name == "minecraft_command":
            return tools.minecraft_command(args.get("command", ""))
        if name == "minecraft_say":
            return tools.minecraft_say(args.get("message", ""))
        if name == "minecraft_tell":
            return tools.minecraft_tell(args.get("player", ""), args.get("message", ""))
        if name == "minecraft_list_players":
            return tools.minecraft_list_players()
        if name == "minecraft_recent_chat":
            return tools.minecraft_recent_chat(args.get("minutes", 5))
        if name == "minecraft_wait_for_player":
            return tools.minecraft_wait_for_player(args.get("player_name", ""), args.get("timeout", 300))
        if name == "minecraft_check_ai_questions":
            return tools.minecraft_check_ai_questions(args.get("password", "12345"))
        if name == "launch_app":
            return tools.launch_app(args.get("app_name", ""))
        if name == "get_news":
            return tools.get_news(args.get("language", "sk"), int(args.get("count", 5)))
        if name == "call_developer_agent":
            return tools.call_developer_agent(args.get("target_filename", ""), args.get("task_description", ""))
        if name == "memory_search":
            return tools.memory_search(args.get("query", ""))
        if name == "rag_search":
            return tools.rag_search(args.get("query", ""))  # legacy fallback
        if name == "search_and_list_images":
            return tools.search_and_list_images(args.get("query", ""), int(args.get("max_results", 5)))
        if name == "open_web_ui":
            return tools.open_web_ui()
        if name == "dismiss_hud":
            return "HUD dismissed (no-op in web UI)"
        return f"Neznámy nástroj: {name}"
    except Exception as e:
        return f"Chyba {name}: {e}"


# ---------------------------------------------------------------------------
# Context usage estimation
# ---------------------------------------------------------------------------
def estimate_context_usage(history, model="deepseek"):
    """Estimate context token usage as percentage of model's limit."""
    total_chars = 0
    for msg in history:
        content = msg.get("content", "")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    text = block.get("text", "") or block.get("content", "")
                    total_chars += len(str(text))
                    if block.get("type") in ("tool_use", "tool_result"):
                        total_chars += 300  # overhead per tool block
        elif isinstance(content, str):
            total_chars += len(content)

    estimated_tokens = total_chars // 4 + 2000  # system prompt overhead
    max_tokens = 128000 if model == "deepseek" else 200000

    ctx_pct = min(99, round((estimated_tokens / max_tokens) * 100, 1))
    return {
        "pct": ctx_pct,
        "estimated": estimated_tokens,
        "max": max_tokens,
    }


def _find_uploaded_file(session_id, filename):
    """Find an uploaded file across ALL session dirs, global pool, and categories. Returns full path or None."""
    basename = os.path.basename(filename)
    all_cat_names = list(_FILE_CATEGORIES.keys()) + ["other"]

    def _try_dir(base_dir):
        # Direct file in root
        direct = os.path.join(base_dir, basename)
        if os.path.isfile(direct):
            return direct
        # In category subdirectories
        for cat_name in all_cat_names:
            candidate = os.path.join(base_dir, cat_name, basename)
            if os.path.isfile(candidate):
                return candidate
        return None

    # 1) Current session
    session_dir = os.path.join(_UPLOADS_DIR, session_id)
    result = _try_dir(session_dir)
    if result:
        return result

    # 2) Global pool
    result = _try_dir(_UPLOADS_DIR)
    if result:
        return result

    # 3) Other session directories
    if os.path.isdir(_UPLOADS_DIR):
        for dirname in sorted(os.listdir(_UPLOADS_DIR)):
            if dirname == session_id or dirname in all_cat_names:
                continue
            result = _try_dir(os.path.join(_UPLOADS_DIR, dirname))
            if result:
                return result

    return None


def _describe_image(filename, session_id):
    """Use Claude vision to describe an uploaded image. Returns text description."""
    if not filename or not session_id:
        return "Missing filename or session_id."
    # Locate the image file — search in categories
    fpath = _find_uploaded_file(session_id, filename)
    if not fpath:
        # Try without session subdirectory
        fpath = os.path.join(_UPLOADS_DIR, os.path.basename(filename))
        if not os.path.exists(fpath):
            return f"Image file not found: {filename}"
    try:
        import mimetypes
        mt = mimetypes.guess_type(fpath)[0] or "image/jpeg"
        with open(fpath, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        # Call Haiku (cheap vision model) to describe the image
        client = haiku_client or claude
        model = HAIKU_MODEL if haiku_client else CLAUDE_MODEL
        resp = client.messages.create(
            model=model,
            max_tokens=500,
            system=[{"type": "text", "text": "Describe this image in detail in the user's language (Slovak or English based on what you see). Include: main subjects, colors, text visible, composition, style, mood."}],
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": mt, "data": b64}},
                {"type": "text", "text": "What's in this image?"}
            ]}],
        )
        desc = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
        return f"📷 Popis obrázka ({filename}):\n{desc}"
    except ImportError:
        return f"Image file found at {fpath} but vision API unavailable."
    except Exception as e:
        return f"Chyba pri popise obrázka {filename}: {e}"


def _load_memories():
    """Load memories from web_ui/memory.json. Returns dict."""
    try:
        if os.path.exists(_MEMORY_PATH):
            with open(_MEMORY_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_memories(mem):
    """Save memories dict to web_ui/memory.json."""
    try:
        os.makedirs(os.path.dirname(_MEMORY_PATH), exist_ok=True)
        with open(_MEMORY_PATH, "w", encoding="utf-8") as f:
            json.dump(mem, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _format_memories_for_prompt():
    """Format saved memories as a string for inclusion in the system prompt."""
    mem = _load_memories()
    if not mem:
        return ""
    lines = [f"- {k}: {v}" for k, v in mem.items()]
    return "\n".join(lines)


def _deepseek_send_plain(messages, tools=None):
    """Send messages to DeepSeek API (non-streaming). Returns raw response dict."""
    from openai import OpenAI
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        return {"error": "DEEPSEEK_API_KEY not set"}
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            tools=tools,
            stream=False,
            temperature=0.7,
        )
        return resp.model_dump()
    except Exception as e:
        return {"error": str(e)}


def _convert_to_oai(history):
    """Convert Anthropic-format history to OpenAI-format messages (text-only, DeepSeek doesn't support image_url)."""
    oai = []
    for msg in history:
        role = "assistant" if msg["role"] == "assistant" else "user"
        content = msg["content"]

        # tool/function messages keep plain string content
        if msg.get("tool_calls") or msg.get("role") == "tool":
            oai.append({"role": role, "content": str(content) if not isinstance(content, str) else content})
            if msg.get("tool_calls"):
                oai[-1]["tool_calls"] = msg["tool_calls"]
            if msg.get("tool_call_id"):
                oai[-1]["tool_call_id"] = msg["tool_call_id"]
            continue

        if isinstance(content, list):
            texts = []
            for block in content:
                if isinstance(block, dict):
                    t = block.get("type", "")
                    if t == "text":
                        texts.append(block["text"])
                    elif t == "image":
                        fname = block.get("filename", "image")
                        texts.append(f"[Image: {fname} — use describe_image tool to see its content]")
                    elif t == "tool_result":
                        texts.append(str(block.get("content", "")))
                    elif t == "tool_use":
                        texts.append(f"[Tool: {block.get('name', '?')}]")
                elif isinstance(block, str):
                    texts.append(block)
            oai.append({"role": role, "content": "\n".join(texts)})
        else:
            oai.append({"role": role, "content": str(content)})
    return oai


def _load_claude_md():
    """Load CLAUDE.md from project root if it exists."""
    md_path = os.path.join(_PROJECT_ROOT, "CLAUDE.md")
    if os.path.exists(md_path):
        try:
            with open(md_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            return f"\n\n[Project context from CLAUDE.md]:\n{content[:3000]}"
        except Exception:
            pass
    return ""


def _coding_chat_stream(history, session_id, prompt):
    """Coding mode: multi-tool loop with reasoning, timing, and stats."""

    # Inject memory context into coding mode too
    try:
        from tools.context_builder import build_context
        mem_ctx = build_context(prompt)
        if mem_ctx:
            prompt = f"{prompt}\n\n{mem_ctx}"
    except Exception:
        pass

    if DEEPSEEK_AVAILABLE:
        # Build system prompt with CLAUDE.md context + memories
        sys_prompt = CODING_SYSTEM_PROMPT + _load_claude_md()
        memories = _format_memories_for_prompt()
        if memories:
            sys_prompt += f"\n\n📌 ZAPAMÄTANÉ:\n{memories}"

        # Build OpenAI messages from history + new user message (don't mutate history yet)
        oai = _convert_to_oai(history)
        oai.append({"role": "user", "content": prompt})
        oai.insert(0, {"role": "system", "content": sys_prompt})

        loop_count = 0
        overall_start = time.time()
        for _ in range(30):
            loop_count += 1

            resp = _deepseek_send_plain(oai, tools=CODING_TOOLS)
            if "error" in resp:
                yield f"data: {json.dumps({'type': 'error', 'text': resp['error']})}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return

            usage = resp.get("usage", {})
            pt = usage.get("prompt_tokens", 0)
            ct = usage.get("completion_tokens", 0)

            msg = resp["choices"][0].get("message", {})

            # Check for reasoning in non-streaming response
            reasoning = msg.get("reasoning_content", "")
            if reasoning:
                yield f"data: {json.dumps({'type': 'reasoning', 'text': reasoning})}\n\n"

            oai.append({"role": "assistant", "content": msg.get("content", ""),
                        "tool_calls": msg.get("tool_calls")})

            tool_calls = msg.get("tool_calls")
            if not tool_calls:
                final = msg.get("content", "")
                # Send entire response instantly — no artificial delay
                yield f"data: {json.dumps({'type': 'token', 'text': final})}\n\n"
                total_elapsed = round(time.time() - overall_start, 1)
                ctx = estimate_context_usage(history, "deepseek")
                yield f"data: {json.dumps({'type': 'context', **ctx})}\n\n"
                yield f"data: {json.dumps({'type': 'stats', 'prompt_tokens': pt, 'completion_tokens': ct, 'elapsed_sec': total_elapsed, 'loop_calls': loop_count})}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"

                history.append({"role": "user", "content": [{"type": "text", "text": prompt}]})
                history.append({"role": "assistant", "content": [{"type": "text", "text": final}]})
                conversations[session_id] = history
                _auto_save(session_id, history)

                # Auto-memory: extract facts from coding exchanges
                try:
                    from tools.auto_memory import auto_remember
                    auto_remember(user_message=prompt, assistant_response=final)
                except Exception:
                    pass
                return

            # Signal tool usage with reasoning-like display
            for tc in tool_calls:
                name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    args = {}

                # Show tool call with arguments as reasoning block
                args_pretty = json.dumps(args, ensure_ascii=False, indent=1)[:500]
                yield f"data: {json.dumps({'type': 'reasoning', 'text': f'\n⚙️ {name}\n{args_pretty}\n'})}\n\n"

                # Task start event (for progress panel)
                yield f"data: {json.dumps({'type': 'task_start', 'name': name, 'args': _summarize_tool_args(name, args)})}\n\n"

                t_tool = time.time()
                result = _execute_coding_tool(name, args, session_id)
                tool_elapsed = time.time() - t_tool
                result_str = str(result)

                # Task end event
                yield f"data: {json.dumps({'type': 'task_end', 'name': name, 'elapsed': round(tool_elapsed, 1)})}\n\n"

                # Show truncated result as reasoning
                result_preview = result_str[:500]
                # Truncate with indicator if too long
                if len(result_str) > 500:
                    result_preview += f"\n… ({len(result_str)} chars total)"
                yield f"data: {json.dumps({'type': 'reasoning', 'text': f'✅ {name} ({tool_elapsed:.1f}s)\n{result_preview}\n'})}\n\n"

                # Stats update with OVERALL elapsed time (never resets)
                total_elapsed = round(time.time() - overall_start, 1)
                yield f"data: {json.dumps({'type': 'stats', 'prompt_tokens': pt, 'completion_tokens': ct, 'elapsed_sec': total_elapsed, 'tool': name})}\n\n"

                oai.append({"role": "tool", "tool_call_id": tc["id"], "content": result_str[:3000]})

        yield f"data: {json.dumps({'type': 'error', 'text': 'Tool limit (30) dosiahnutý — DeepSeek sa zacyklil v nástrojoch. Skús upresniť čo chceš.'})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return

    # Claude fallback
    sb = [{"type": "text", "text": "You are a coding assistant.", "cache_control": {"type": "ephemeral"}}]
    try:
        fallback_msgs = list(history) + [{"role": "user", "content": prompt}]
        with claude.messages.stream(model=CLAUDE_MODEL, max_tokens=4000, system=sb, messages=fallback_msgs) as s:
            for t in s.text_stream:
                yield f"data: {json.dumps({'type': 'token', 'text': t})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        final = s.get_final_message()
        history.append({"role": "user", "content": [{"type": "text", "text": prompt}]})
        history.append({"role": "assistant", "content": final.content})
        conversations[session_id] = history
        _auto_save(session_id, history)

        # Auto-memory: extract facts from coding fallback exchanges
        try:
            from tools.auto_memory import auto_remember
            auto_remember(user_message=prompt, assistant_response=str(final.content))
        except Exception:
            pass
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'text': str(e)})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"


@app.route("/api/upload", methods=["POST"])
@login_required
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "Empty filename"}), 400
    session_id = request.form.get("session_id", "default")
    # Bezpečnosť: session_id len alfanumerické znaky + pomlčky/podtržítka
    if not re.match(r'^[a-zA-Z0-9_-]+$', session_id):
        return jsonify({"error": "Invalid session_id"}), 400
    data = base64.b64encode(file.read()).decode("utf-8")
    media_type = file.content_type or "application/octet-stream"
    # Bezpečnosť: strip path separators from filename
    filename = os.path.basename(file.filename) or "upload.bin"

    # Save to disk in session-scoped uploads directory, categorized by file type
    category = _get_file_category(filename)
    session_upload_dir = os.path.join(_UPLOADS_DIR, session_id, category)
    os.makedirs(session_upload_dir, exist_ok=True)
    save_path = os.path.join(session_upload_dir, filename)
    # Avoid name collisions by appending a number if needed
    if os.path.exists(save_path):
        base, ext = os.path.splitext(filename)
        counter = 1
        while os.path.exists(os.path.join(session_upload_dir, f"{base}_{counter}{ext}")):
            counter += 1
        save_path = os.path.join(session_upload_dir, f"{base}_{counter}{ext}")
        filename = f"{base}_{counter}{ext}"
    try:
        with open(save_path, "wb") as sf:
            sf.write(base64.b64decode(data))
    except Exception as e:
        pass  # non-critical, base64 data is still returned

    file_size = os.path.getsize(save_path) if os.path.exists(save_path) else len(data) * 3 // 4
    # Return relative saved_path for the AI to reference
    relative_path = f"uploads/{session_id}/{category}/{filename}"
    return jsonify({
        "data": data,
        "media_type": media_type,
        "filename": filename,
        "saved_path": save_path,
        "relative_path": relative_path,
        "size": file_size,
    })


@app.route("/api/uploads/<session_id>", methods=["GET"])
@login_required
def list_uploads(session_id):
    """List all uploaded files for a session, grouped by category."""
    scanned = _scan_upload_files(session_id)
    if not scanned:
        return jsonify({"categories": {}})

    categories = {}
    for cat_name in list(_FILE_CATEGORIES.keys()) + ["other"]:
        files = scanned.get(cat_name)
        if not files:
            continue
        entries = []
        for fname, fpath, size, mtime, rel_path in files:
            entries.append({
                "filename": fname,
                "size": size,
                "modified": datetime.fromtimestamp(mtime).isoformat(),
                "category": cat_name,
                "relative_path": rel_path,
            })
        categories[cat_name] = entries

    return jsonify({"categories": categories})


@app.route("/api/uploads/<session_id>/<path:filename>")
@login_required
def serve_upload(session_id, filename):
    """Serve an uploaded file. Searches current session, all other sessions, global pool."""
    from flask import send_from_directory, abort
    all_cat_names = list(_FILE_CATEGORIES.keys()) + ["other"]

    def _try_serve(base_dir):
        direct = os.path.join(base_dir, filename)
        if os.path.isfile(direct):
            return send_from_directory(base_dir, filename)
        for cat_name in all_cat_names:
            cat_dir = os.path.join(base_dir, cat_name)
            candidate = os.path.join(cat_dir, filename)
            if os.path.isfile(candidate):
                return send_from_directory(cat_dir, filename)
        return None

    # 1) Current session
    session_dir = os.path.join(_UPLOADS_DIR, session_id)
    result = _try_serve(session_dir)
    if result:
        return result

    # 2) Global pool
    result = _try_serve(_UPLOADS_DIR)
    if result:
        return result

    # 3) All other session directories
    if os.path.isdir(_UPLOADS_DIR):
        for dirname in sorted(os.listdir(_UPLOADS_DIR)):
            if dirname == session_id or dirname in all_cat_names:
                continue
            result = _try_serve(os.path.join(_UPLOADS_DIR, dirname))
            if result:
                return result

    abort(404)


@app.route("/api/transcribe", methods=["POST"])
@login_required
def transcribe():
    """Receive WAV audio, transcribe via Google Speech Recognition, return text."""
    if "audio" not in request.files:
        return jsonify({"error": "No audio file"}), 400
    f = request.files["audio"]
    tmp = os.path.join(tempfile.gettempdir(), "jarvis_mic.wav")
    try:
        f.save(tmp)
        import speech_recognition as sr
        r = sr.Recognizer()
        with sr.AudioFile(tmp) as src:
            audio = r.record(src)
        text = r.recognize_google(audio, language="sk-SK")
        if not text.strip():
            return jsonify({"text": ""})
        return jsonify({"text": text.strip()})
    except ImportError:
        return jsonify({"error": "speech_recognition nie je nainštalovaný"}), 500
    except sr.UnknownValueError:
        return jsonify({"text": ""})
    except sr.RequestError as e:
        return jsonify({"error": f"Google STT: {e}"}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass


@app.route("/api/history", methods=["GET", "DELETE"])
@login_required
def handle_history():
    session_id = request.args.get("session_id", "default")
    stream = request.args.get("stream", "0")
    if request.method == "DELETE":
        conversations[session_id] = []
        return jsonify({"status": "cleared"})

    # SSE streaming mode for real-time sync between devices
    if stream == "1":
        def generate():
            last_len = len(_get_history(session_id))
            import time as _time
            for _ in range(600):  # 10 min timeout
                _time.sleep(1.5)
                current = _get_history(session_id)
                if len(current) != last_len:
                    last_len = len(current)
                    simplified = []
                    for msg in current:
                        role = msg["role"]
                        content = msg["content"]
                        if isinstance(content, list):
                            texts = []
                            for block in content:
                                if isinstance(block, dict):
                                    t = block.get("type", "")
                                    if t == "text": texts.append(block.get("text", ""))
                            content = " ".join(texts)
                        simplified.append({"role": role, "content": str(content)[:500]})
                    yield f"data: {json.dumps({'type': 'refresh', 'messages': simplified})}\n\n"
        return Response(generate(), mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    history = _get_history(session_id)
    simplified = []
    for msg in history:
        role = msg["role"]
        content = msg["content"]
        if isinstance(content, list):
            texts = []
            for block in content:
                if isinstance(block, dict):
                    t = block.get("type", "")
                    if t == "text": texts.append(block.get("text", ""))
                    elif t == "tool_result": texts.append("[Tool result]")
                    elif t == "tool_use": texts.append(f"[Tool: {block.get('name', '?')}]")
                    elif t == "image": texts.append("[📷 Image]")
                elif isinstance(block, str): texts.append(block)
            content = "\n".join(texts)
        simplified.append({"role": role, "content": str(content)[:500]})
    return jsonify({"messages": simplified})


# ---------------------------------------------------------------------------
# Session management (save/load/list/delete)
# ---------------------------------------------------------------------------
# _SESSIONS_DIR and _ensure_sessions_dir are already defined above (line ~91)

@app.route("/api/sessions", methods=["GET"])
@login_required
def list_sessions():
    """List all saved sessions."""
    _ensure_sessions_dir()
    sessions = []
    for fname in sorted(os.listdir(_SESSIONS_DIR)):
        if fname.endswith(".json"):
            sid = fname[:-5]
            path = os.path.join(_SESSIONS_DIR, fname)
            mtime = os.path.getmtime(path)
            size = os.path.getsize(path)
            sessions.append({
                "id": sid,
                "name": sid,
                "modified": datetime.fromtimestamp(mtime).isoformat(),
                "messages": size // 1000,  # rough estimate
            })
    return jsonify({"sessions": sorted(sessions, key=lambda s: s["modified"], reverse=True)})


@app.route("/api/sessions/last", methods=["GET"])
@login_required
def get_last_session():
    """Get the most recently modified session."""
    _ensure_sessions_dir()
    try:
        files = [f for f in os.listdir(_SESSIONS_DIR) if f.endswith(".json")]
        if not files:
            return jsonify({"status": "none"})
        files.sort(key=lambda f: os.path.getmtime(os.path.join(_SESSIONS_DIR, f)), reverse=True)
        latest = files[0]
        sid = latest[:-5]
        path = os.path.join(_SESSIONS_DIR, latest)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return jsonify({"status": "loaded", "id": sid, "history": data})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/sessions/<session_id>", methods=["GET", "DELETE", "PUT"])
@login_required
def handle_session(session_id):
    """Get, delete, or rename a saved session."""
    from urllib.parse import unquote
    session_id = unquote(session_id)
    _ensure_sessions_dir()
    path = os.path.join(_SESSIONS_DIR, f"{session_id}.json")

    if request.method == "DELETE":
        if os.path.exists(path):
            os.remove(path)
            return jsonify({"status": "deleted", "id": session_id})
        return jsonify({"error": "Session not found"}), 404

    if request.method == "PUT":
        data = request.json or {}
        conv = data.get("history", [])
        with open(path, "w", encoding="utf-8") as f:
            json.dump(conv, f, ensure_ascii=False, indent=2)
        return jsonify({"status": "saved", "id": session_id, "messages": len(conv)})

    if request.method == "GET":
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                conv = json.load(f)
            return jsonify({"status": "loaded", "id": session_id, "history": conv})
        return jsonify({"error": "Session not found"}), 404


@app.route("/api/command", methods=["POST"])
@login_required
def handle_command():
    """Handle chat commands like /clear, /new, /help, /compact."""
    data = request.json or {}
    cmd = data.get("command", "").lower().strip()
    session_id = data.get("session_id", "default")

    if cmd in ("clear", "new"):
        conversations[session_id] = []
        return jsonify({"status": "ok", "message": "✅ Chat vymazaný."})

    if cmd == "help":
        return jsonify({"status": "ok", "message": """**Dostupné príkazy:**
- `/new` alebo `/clear` — nový chat
- `/save <názov>` — uložiť session
- `/load <názov>` — načítať session
- `/list` — zoznam uložených session
- `/delete <názov>` — vymazať session
- `/compact` — zhustiť konverzáciu
- `/help` — tento zoznam
- `/stats` — štatistiky aktuálnej session"""})

    if cmd == "list":
        _ensure_sessions_dir()
        sessions = [f[:-5] for f in os.listdir(_SESSIONS_DIR) if f.endswith(".json")]
        if sessions:
            return jsonify({"status": "ok", "message": "**Uložené session:**\n" + "\n".join(f"- {s}" for s in sorted(sessions))})
        return jsonify({"status": "ok", "message": "Žiadne uložené session."})

    if cmd.startswith("save "):
        name = cmd[5:].strip()
        if not name:
            return jsonify({"status": "error", "message": "Názov je povinný: /save <názov>"})
        conv = conversations.get(session_id, [])
        _ensure_sessions_dir()
        path = os.path.join(_SESSIONS_DIR, f"{name}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(conv, f, ensure_ascii=False, indent=2)
        return jsonify({"status": "ok", "message": f"✅ Session '{name}' uložená ({len(conv)} správ)."})

    if cmd.startswith("load "):
        name = cmd[5:].strip()
        _ensure_sessions_dir()
        path = os.path.join(_SESSIONS_DIR, f"{name}.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                conv = json.load(f)
            conversations[session_id] = conv
            return jsonify({"status": "ok", "message": f"✅ Session '{name}' načítaná.", "history": conv})
        return jsonify({"status": "error", "message": f"Session '{name}' neexistuje."})

    if cmd.startswith("delete "):
        name = cmd[7:].strip()
        _ensure_sessions_dir()
        path = os.path.join(_SESSIONS_DIR, f"{name}.json")
        if os.path.exists(path):
            os.remove(path)
            return jsonify({"status": "ok", "message": f"🗑️ Session '{name}' vymazaná."})
        return jsonify({"status": "error", "message": f"Session '{name}' neexistuje."})

    if cmd == "compact":
        conv = conversations.get(session_id, [])
        if len(conv) < 4:
            return jsonify({"status": "ok", "message": "Konverzácia je krátka, netreba compactovať."})
        # Simple compact: keep first system message + last 6 messages
        kept = conv[-6:] if len(conv) > 6 else conv
        conversations[session_id] = kept
        return jsonify({"status": "ok", "message": f"✅ Konverzácia zhustená na {len(kept)} správ."})

    if cmd == "stats":
        conv = conversations.get(session_id, [])
        msg_count = len(conv)
        user_msgs = sum(1 for m in conv if m["role"] == "user")
        asst_msgs = sum(1 for m in conv if m["role"] == "assistant")
        total_chars = sum(len(str(m.get("content", ""))) for m in conv)
        return jsonify({"status": "ok", "message": f"**Štatistiky session:**\n- Správy celkom: {msg_count}\n- Tvoje: {user_msgs}\n- Odpovede: {asst_msgs}\n- Text: ~{total_chars} znakov"})

    return jsonify({"status": "error", "message": f"Neznámy príkaz: /{cmd}. Napíš /help."})


# ---------------------------------------------------------------------------
# Memory API
# ---------------------------------------------------------------------------
@app.route("/api/memory", methods=["GET", "POST", "DELETE"])
@login_required
def handle_memory():
    """Read, save, or delete memories."""
    if request.method == "GET":
        mem = _load_memories()
        return jsonify({"memories": mem})

    if request.method == "POST":
        data = request.json or {}
        key = data.get("key", "").strip()
        value = data.get("value", "").strip()
        if not key or not value:
            return jsonify({"error": "key and value required"}), 400
        mem = _load_memories()
        mem[key] = value
        _save_memories(mem)
        return jsonify({"status": "saved", "key": key, "memories": len(mem)})

    if request.method == "DELETE":
        data = request.json or {}
        key = data.get("key", "").strip()
        mem = _load_memories()
        if key in mem:
            del mem[key]
            _save_memories(mem)
            return jsonify({"status": "deleted", "key": key})
        return jsonify({"error": "key not found"}), 404


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        # Rate limit check
        ip = request.remote_addr or "unknown"
        allowed, wait = _check_rate_limit(ip)
        if not allowed:
            return jsonify({"ok": False, "error": f"Príliš veľa pokusov. Počkaj {wait}s."}), 429

        data = request.json or {}
        if data.get("user") == WEBUI_USER and data.get("pass") == WEBUI_PASS:
            _login_attempts.pop(ip, None)  # clear on success
            session["logged_in"] = True
            session.permanent = True
            return jsonify({"ok": True})
        # Record failed attempt
        _login_attempts[ip].append(time.time())
        return jsonify({"ok": False, "error": "Nesprávne meno alebo heslo"}), 403
    # GET — render login page
    return render_template("login.html", auth_enabled=AUTH_ENABLED)

@app.route("/logout")
def logout():
    session.pop("logged_in", None)
    return redirect("/login")

@app.route("/")
@login_required
def index():
    return render_template("index.html", deepseek_available=DEEPSEEK_AVAILABLE)

@app.route("/api/config")
@login_required
def api_config():
    return jsonify({
        "claude_model": CLAUDE_MODEL,
        "jarvis_model": CLAUDE_MODEL,
        "coding_model": "deepseek-chat",
        "deepseek_available": DEEPSEEK_AVAILABLE,
        "tools_count": len(JARVIS_TOOLS),
    })

@app.route("/api/chat", methods=["POST"])
@login_required
def chat():
    # Mark user activity for auto-save idle detection
    try:
        from tools.consolidation import touch
        touch()
    except ImportError:
        pass

    data = request.json or {}
    mode = data.get("mode", "coding")
    session_id = data.get("session_id", "coding_main")
    prompt = data.get("message", "") or data.get("prompt", "")
    images = data.get("images", [])

    # Ak máme images s base64 dátami, pripoj ich do promptu
    if images:
        img_refs = []
        for img in images:
            if img.get("saved_path"):
                img_refs.append(f"[File: {img.get('filename', '?')} (path: {img['saved_path']})]")
            elif img.get("data"):
                img_refs.append(f"[Uploaded image: {img.get('filename', '?')}]")
        if img_refs:
            prompt = prompt + "\n" + "\n".join(img_refs)

    # Load conversation history for this session (server-side persistence)
    history = conversations.get(session_id, [])

    if mode == "jarvis":
        return _jarvis_chat_stream(history, session_id, prompt)
    else:
        return _coding_chat_stream(history, session_id, prompt)

def _jarvis_chat_stream(history, session_id, prompt):
    """Jarvis mode: Claude with full tools, conversation history, and persistence."""
    def generate():
        final_text = ""
        overall_start = time.time()
        try:
            # Build messages for API call (don't mutate history until success)
            _msgs = list(history)

            # Inject memory context into user message (context_builder pulls from all 5 tiers)
            try:
                from tools.context_builder import build_context
                mem_ctx = build_context(prompt)
                if mem_ctx:
                    augmented_prompt = f"{prompt}\n\n{mem_ctx}"
                else:
                    augmented_prompt = prompt
            except Exception:
                augmented_prompt = prompt

            _msgs.append({"role": "user", "content": [{"type": "text", "text": augmented_prompt}]})

            max_turns = 5
            for turn in range(max_turns):
                resp = claude.messages.create(
                    model=CLAUDE_MODEL,
                    max_tokens=4000,
                    system=[{"type": "text", "text": JARVIS_SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
                    tools=JARVIS_TOOLS,
                    messages=_msgs,
                )
                _msgs.append({"role": "assistant", "content": resp.content})

                # Stream text blocks and detect tool use
                has_tools = False
                for block in resp.content:
                    if getattr(block, "type", None) == "text":
                        final_text += block.text
                        yield f"data: {json.dumps({'type': 'token', 'text': block.text})}\n\n"
                    elif getattr(block, "type", None) == "tool_use":
                        has_tools = True

                if not has_tools or resp.stop_reason != "tool_use":
                    break

                # Execute tool calls with visible progress
                tool_results = []
                for block in resp.content:
                    if getattr(block, "type", None) != "tool_use":
                        continue
                    name = block.name
                    inp = dict(block.input) if hasattr(block.input, "items") else {}
                    args_summary = _summarize_tool_args(name, inp)
                    # Show tool call as reasoning block in chat
                    yield f"data: {json.dumps({'type': 'reasoning', 'text': f'⚙️ {name}: {args_summary}'})}\n\n"
                    yield f"data: {json.dumps({'type': 'task_start', 'name': name, 'args': args_summary})}\n\n"
                    t_start = time.time()
                    try:
                        result = _execute_coding_tool(name, inp, session_id)
                    except Exception as e:
                        result = f"Error: {e}"
                    elapsed = round(time.time() - t_start, 1)
                    yield f"data: {json.dumps({'type': 'task_end', 'name': name, 'elapsed': elapsed})}\n\n"
                    # Show result preview as reasoning
                    result_str = str(result)[:300]
                    yield f"data: {json.dumps({'type': 'reasoning', 'text': f'✅ {name} ({elapsed}s): {result_str}'})}\n\n"
                    tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": str(result)[:3000]})
                _msgs.append({"role": "user", "content": tool_results})

            # Persist conversation on success
            history.append({"role": "user", "content": [{"type": "text", "text": prompt}]})
            history.append({"role": "assistant", "content": [{"type": "text", "text": final_text}]})
            conversations[session_id] = history
            _auto_save(session_id, history)

            # ── 5-Tier Memory Integration ──
            # Auto-memory: extract and store facts from this exchange
            try:
                from tools.auto_memory import auto_remember
                auto_remember(user_message=prompt, assistant_response=final_text)
            except Exception:
                pass

            # Periodic consolidation: keep memory healthy (every ~10 exchanges)
            try:
                from tools.auto_memory import _counter
                if _counter.get("calls", 0) % 10 == 0:
                    from tools.consolidation import consolidate_quick
                    consolidate_quick()
            except Exception:
                pass

            total_elapsed = round(time.time() - overall_start, 1)
            yield f"data: {json.dumps({'type': 'stats', 'elapsed_sec': total_elapsed})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as e:
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'type': 'error', 'text': str(e)})}\n\n"
    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_UPLOADS_DIR = os.path.join(os.path.dirname(__file__), "uploads")
_FILE_CATEGORIES = {
    "images":       {"jpg", "jpeg", "png", "gif", "webp", "bmp", "svg", "ico", "heic", "heif"},
    "documents":    {"pdf", "txt", "rtf", "odt", "doc", "docx", "md"},
    "spreadsheets": {"xls", "xlsx", "csv", "ods"},
    "videos":       {"mp4", "avi", "mkv", "mov", "wmv", "flv", "webm"},
    "audio":        {"mp3", "wav", "ogg", "flac", "aac", "m4a", "wma"},
    "archives":     {"zip", "rar", "7z", "tar", "gz", "bz2", "xz"},
    "code":         {"py", "js", "ts", "html", "css", "php", "java", "cpp", "c", "h", "rs", "go", "swift", "kt"},
}
# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _ensure_sessions_dir():
    os.makedirs(_SESSIONS_DIR, exist_ok=True)

def _get_file_category(filename):
    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    for cat, exts in _FILE_CATEGORIES.items():
        if ext in exts: return cat
    return "other"

def _scan_upload_files(session_id):
    session_dir = os.path.join(_UPLOADS_DIR, session_id)
    result = {}
    all_cat_names = list(_FILE_CATEGORIES.keys()) + ["other"]

    # Helper: scan a directory for categorized files
    def _scan_dir(base_dir, rel_prefix=""):
        if not os.path.isdir(base_dir):
            return
        # Scan category subdirectories
        for cat_name in all_cat_names:
            cat_dir = os.path.join(base_dir, cat_name)
            if not os.path.isdir(cat_dir):
                continue
            for fname in sorted(os.listdir(cat_dir)):
                fpath = os.path.join(cat_dir, fname)
                if os.path.isfile(fpath):
                    rel = rel_prefix + f"{cat_name}/{fname}"
                    if cat_name not in result:
                        result[cat_name] = []
                    existing = {entry[0] for entry in result.get(cat_name, [])}
                    if fname not in existing:
                        result[cat_name].append((fname, fpath, os.path.getsize(fpath), os.path.getmtime(fpath), rel))
        # Scan loose files in root
        for fname in sorted(os.listdir(base_dir)):
            fpath = os.path.join(base_dir, fname)
            if os.path.isfile(fpath):
                cat = _get_file_category(fname)
                if cat not in result:
                    result[cat] = []
                existing = {entry[0] for entry in result.get(cat, [])}
                if fname not in existing:
                    result[cat].append((fname, fpath, os.path.getsize(fpath), os.path.getmtime(fpath), rel_prefix + fname))

    # 1) Current session
    _scan_dir(session_dir)

    # 2) Global pool (uploads/<category>/)
    _scan_dir(_UPLOADS_DIR, rel_prefix="../")

    # 3) ALL other session directories — so new chats can see previously uploaded files
    if os.path.isdir(_UPLOADS_DIR):
        for dirname in sorted(os.listdir(_UPLOADS_DIR)):
            if dirname == session_id:
                continue  # already scanned
            if dirname in all_cat_names:
                continue  # skip global pool category dirs
            other_session_dir = os.path.join(_UPLOADS_DIR, dirname)
            if os.path.isdir(other_session_dir):
                _scan_dir(other_session_dir, rel_prefix=f"../{dirname}/")

    return result

def _auto_save(session_id, msgs=None):
    if msgs is None:
        if session_id not in conversations: return
        msgs = conversations[session_id]
    _ensure_sessions_dir()
    saved = []
    for m in msgs:
        content = m.get("content", "")
        if isinstance(content, list):
            content = " ".join(str(c.get("text", "")) for c in content if c.get("type") == "text")
        saved.append({"role": m.get("role", "user"), "content": str(content)[:2000]})
    with open(os.path.join(_SESSIONS_DIR, f"{session_id}.json"), "w", encoding="utf-8") as f:
        json.dump(saved, f, ensure_ascii=False, indent=2)

def _get_history(session_id):
    conversations.setdefault(session_id, [])
    return conversations[session_id]

# ---------------------------------------------------------------------------
# Conversation storage
# ---------------------------------------------------------------------------
conversations = {}
AUTO_SESSION_ID = "_auto"
MAX_HISTORY_TURNS = 20

_SESSIONS_DIR = os.path.join(os.path.dirname(__file__), "sessions")
_MEMORY_PATH = os.path.join(os.path.dirname(__file__), "memory.json")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _auto_load_last():
    """Auto-load poslednej session (najnovšie upravený .json)."""
    sess_dir = os.path.join(os.path.dirname(__file__), "sessions")
    if not os.path.isdir(sess_dir):
        return None
    best = None
    best_time = 0
    for fname in os.listdir(sess_dir):
        if fname.endswith(".json"):
            fpath = os.path.join(sess_dir, fname)
            mtime = os.path.getmtime(fpath)
            if mtime > best_time:
                best_time = mtime
                best = fname
    if best:
        sid = best.replace(".json", "")
        try:
            with open(os.path.join(sess_dir, best), "r", encoding="utf-8") as f:
                data = json.load(f)
            return sid, data
        except Exception:
            return None
    return None

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    port = int(os.getenv("WEBUI_PORT", 5000))
    host = os.getenv("WEBUI_HOST", "127.0.0.1")

    jarvis_model_name = HAIKU_MODEL if haiku_client else CLAUDE_MODEL
    print(f"🤖 Jarvis mode: {jarvis_model_name} — tools: {len(JARVIS_TOOLS)}")
    if DEEPSEEK_AVAILABLE:
        print(f"💻 Coding mode: DeepSeek (5 tools, reasoning, stats)")
    else:
        print(f"💻 Coding mode: {CLAUDE_MODEL} (coding prompt)")

    if host not in ("127.0.0.1", "localhost", "::1"):
        print("⚠️  WARNING: Web UI bound to non-localhost! Anyone on the network can access tools.")
        print("   Set WEBUI_HOST=127.0.0.1 in .env for local-only access.")

    # Auto-load last session
    loaded = _auto_load_last()
    if loaded:
        sid, data = loaded
        conversations[sid] = data
        if "coding" in sid or "main" in sid:
            conversations["coding_main"] = data
        print(f"📂 Pokračovať v session: {sid} ({len(data)} správ)")
    else:
        print("📂 Nová session (žiadna uložená)")

    print(f"🌐 http://{host}:{port}")
    print(f"📁 Upload limit: 500 MB")
    print(f"Press Ctrl+C to stop.")

    # Start time-based auto-save scheduler
    try:
        from tools.auto_memory import start_auto_save_scheduler
        start_auto_save_scheduler()
        print(f"⏱️  Auto-save scheduler: every {os.getenv('AUTO_SAVE_INTERVAL', '300')}s (idle pause: {os.getenv('IDLE_PAUSE_THRESHOLD', '900')}s)")
    except Exception:
        pass

    os.makedirs(os.path.join(os.path.dirname(__file__), "templates"), exist_ok=True)
    os.makedirs(os.path.join(os.path.dirname(__file__), "static"), exist_ok=True)

    from waitress import serve
    print(f"🚀 Waitress WSGI server — http://{host}:{port}")
    serve(app, host=host, port=port, threads=12, connection_limit=50)


if __name__ == "__main__":
    # Debug: print all registered routes before starting
    print("=" * 60)
    print("REGISTERED ROUTES:")
    for rule in app.url_map.iter_rules():
        methods = ",".join(sorted(rule.methods - {"HEAD", "OPTIONS"}))
        print(f"  {methods:6s} {rule.rule}")
    print("=" * 60)
    main()
