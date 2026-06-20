"""
Local AI — lightweight vision via Ollama (OpenAI-kompatibilné API).

Spúšťa sa len na požiadanie (lazy init):
  - Prvý `describe_image()` → skontroluje či Ollama beží, ak nie → spustí `ollama serve`
  - Ak model nie je stiahnutý → automaticky ho stiahne
  - Pri ukončení procesu → ak sme Ollamu spustili my, ukončíme ju

Nepoužíva žiadne externé API kľúče, všetko beží lokálne.
"""

import os
import sys
import time
import json
import subprocess
import atexit
import urllib.request
import urllib.error

# ── Konfigurácia z .env ──────────────────────────────────────────────
LOCAL_AI_BASE_URL = os.getenv("LOCAL_AI_BASE_URL", "http://localhost:11434")
LOCAL_AI_MODEL = os.getenv("LOCAL_AI_MODEL", "llava")
LOCAL_AI_API_URL = f"{LOCAL_AI_BASE_URL}/v1"

# ── Interný stav ─────────────────────────────────────────────────────
_client = None          # OpenAI klient (lazy)
_server_proc = None     # subprocess.Popen ak sme spustili ollama sami
_available = None       # None=nekontrolované, False=chyba, True=OK
_started_by_us = False  # True ak sme ollama serve spustili my
_cleaned_up = False     # cleanup už bežal


def _log(msg):
    """Vypíše hlášku s prefixom."""
    print(f"[LocalAI] {msg}", flush=True)


def _find_ollama():
    """Nájde ollama executable v systéme."""
    candidates = [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe"),
        r"C:\Program Files\Ollama\ollama.exe",
    ]
    # Skús PATH
    try:
        import shutil
        p = shutil.which("ollama")
        if p:
            return p
    except Exception:
        pass
    for c in candidates:
        c_expanded = os.path.expandvars(c) if "%" in c else c
        if os.path.exists(c_expanded):
            return c_expanded
    return None


def _is_server_running(retries=1):
    """Overí či Ollama server odpovedá na LOCAL_AI_BASE_URL."""
    for _ in range(retries):
        try:
            urllib.request.urlopen(f"{LOCAL_AI_BASE_URL}/api/tags", timeout=2)
            return True
        except Exception:
            time.sleep(1)
    return False


def _start_server():
    """Spustí ollama serve ako subprocess (bez okna)."""
    global _server_proc, _started_by_us

    ollama = _find_ollama()
    if not ollama:
        _log("❌ ollama executable nenájdený. Stiahni z https://ollama.com/download/windows")
        return False

    try:
        _server_proc = subprocess.Popen(
            [ollama, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        _started_by_us = True
        _log("🔄 Spúšťam Ollama server...")

        # Čakáme kým server naskočí (max 15s)
        for i in range(30):
            time.sleep(0.5)
            if _is_server_running():
                _log("✅ Ollama server ready")
                return True
            if i % 6 == 0:
                _log(f"⏳ Čakám na server... ({i//2 + 1}s)")

        _log("❌ Ollama server sa nespustil (timeout)")
        return False
    except Exception as e:
        _log(f"❌ Chyba pri štarte Ollamy: {e}")
        _server_proc = None
        return False


def _ensure_model():
    """
    Skontroluje či je vision model stiahnutý.
    Ak nie → stiahne ho (môže trvať).
    """
    # Zoznam stiahnutých modelov cez API
    try:
        req = urllib.request.Request(f"{LOCAL_AI_BASE_URL}/api/tags")
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read())
        model_base = LOCAL_AI_MODEL.split(":")[0]
        for m in data.get("models", []):
            name = m.get("name", "")
            if name.startswith(model_base) or name.startswith(LOCAL_AI_MODEL):
                return True  # už stiahnutý
    except Exception:
        pass

    # Model nie je → stiahneme cez CLI
    ollama = _find_ollama()
    if not ollama:
        return False

    _log(f"📥 Sťahujem '{LOCAL_AI_MODEL}' (prvé spustenie, cca 2-4 GB)...")
    try:
        proc = subprocess.Popen(
            [ollama, "pull", LOCAL_AI_MODEL],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        for line in iter(proc.stdout.readline, ""):
            if line.strip():
                # Vytiahni percentá z progress baru: "pulling xyz: 45%..."
                stripped = line.strip().strip("\x1b[...]").strip()
                if "%" in stripped:
                    sys.stdout.write(f"\r📥 {stripped[:60]}")
                    sys.stdout.flush()
                else:
                    _log(stripped[:80])
        proc.wait(timeout=600)
        if proc.returncode == 0:
            _log(f"\n✅ Model '{LOCAL_AI_MODEL}' pripravený")
            return True
        _log(f"❌ Chyba pri sťahovaní modelu (kód: {proc.returncode})")
        return False
    except subprocess.TimeoutExpired:
        proc.kill()
        _log(f"\n❌ Timeout pri sťahovaní '{LOCAL_AI_MODEL}'")
        return False
    except Exception as e:
        _log(f"❌ Chyba pri sťahovaní: {e}")
        return False


def _init():
    """
    Lazy inicializácia: spustí Ollama server ak treba,
    vytvorí OpenAI klienta, stiahne model ak chýba.
    """
    global _client, _available

    if _available is True:
        return True
    if _available is False:
        return False

    # 1) Je server hore?
    if not _is_server_running():
        if not _start_server():
            _available = False
            return False

    # 2) Vytvor OpenAI klienta
    try:
        from openai import OpenAI
        _client = OpenAI(base_url=LOCAL_AI_API_URL, api_key="ollama")
    except Exception as e:
        _log(f"❌ OpenAI klient: {e}")
        _available = False
        return False

    # 3) Model k dispozícii?
    if not _ensure_model():
        _available = False
        return False

    _available = True
    return True


def describe_image(filepath, prompt=None):
    """
    Popíše obrázok pomocou lokálneho vision modelu (Ollama).

    Args:
        filepath: Cesta k obrázku
        prompt:  Vlastná otázka (default: detailný popis)

    Returns:
        (description_or_none, error_or_none)
    """
    if not _init():
        msg = (
            "Lokálne AI vision nie je dostupné.\n"
            "1. Stiahni Ollamu: https://ollama.com/download/windows\n"
            "2. Spusti: ollama pull llava\n"
            "3. Alebo nastav LOCAL_AI_BASE_URL v .env na vlastný server"
        )
        return None, msg

    if not filepath or not os.path.exists(filepath):
        return None, f"Súbor neexistuje: {filepath}"

    # Načítaj obrázok a zakóduj do base64
    import mimetypes
    import base64 as _b64

    mt = mimetypes.guess_type(filepath)[0] or "image/jpeg"
    try:
        with open(filepath, "rb") as f:
            b64 = _b64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        return None, f"Chyba pri čítaní súboru: {e}"

    text_prompt = prompt or (
        "Describe this image in detail. Include: main subjects, colors, "
        "text visible, composition, style, mood. "
        "Use Slovak or English based on what you see."
    )

    try:
        resp = _client.chat.completions.create(
            model=LOCAL_AI_MODEL,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": text_prompt},
                    {"type": "image_url", "image_url": {
                        "url": f"data:{mt};base64,{b64}"
                    }},
                ]
            }],
            max_tokens=500,
            temperature=0.3,
        )
        desc = resp.choices[0].message.content or ""
        return desc.strip(), None
    except Exception as e:
        err = str(e)
        # Ak model neexistuje, skús stiahnuť a opakovať
        if "model" in err.lower() and ("not found" in err.lower() or "not exist" in err.lower()):
            _log(f"Model '{LOCAL_AI_MODEL}' nenájdený, sťahujem...")
            if _ensure_model():
                return describe_image(filepath, prompt)
        return None, f"Chyba vision: {err}"


def warmup():
    """
    Pre-load the vision model do RAM (volá sa pri štarte web UI).
    Aby prvý describe_image bol instantný, nie ~5s na načítanie modelu.
    """
    if not _init():
        return False

    import base64, struct, zlib

    # 1×1 čierny PNG
    def _tiny_png():
        def chunk(ctype, data):
            c = ctype + data
            return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
        sig = b'\x89PNG\r\n\x1a\n'
        ihdr = chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
        raw = zlib.compress(b'\x00\x00\x00\x00')  # čierny pixel
        return sig + ihdr + chunk(b'IDAT', raw) + chunk(b'IEND', b'')

    try:
        b64 = base64.b64encode(_tiny_png()).decode()
        _client.chat.completions.create(
            model=LOCAL_AI_MODEL,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": "what color"},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
            ]}],
            max_tokens=1,
        )
        _log(f"🔥 Model '{LOCAL_AI_MODEL}' načítaný do RAM (warmup hotový)")
        return True
    except Exception as e:
        _log(f"⚠️ Warmup zlyhal: {e} — model sa načíta až pri prvom describe_image")
        return False


def cleanup():
    """Zastaví Ollama server ak sme ho spustili my."""
    global _server_proc, _available, _client, _cleaned_up
    if _cleaned_up:
        return
    _cleaned_up = True

    if _server_proc is not None and _started_by_us:
        _log("Zastavujem Ollama server...")
        _server_proc.terminate()
        try:
            _server_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _server_proc.kill()
            _server_proc.wait(timeout=2)
        _log("✅ Ollama server zastavený")
        _server_proc = None
        _started_by_us = False

    _available = None
    _client = None


# Automatický cleanup pri ukončení Python procesu
atexit.register(cleanup)
