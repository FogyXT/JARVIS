import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="pygame")
import os
import re
import json
import base64
import asyncio
import sys
import threading
import queue
import unicodedata
import tempfile
import subprocess
import speech_recognition as sr
import pygame
import winsound
import edge_tts
from anthropic import Anthropic
from dotenv import load_dotenv
import tools

load_dotenv()

# Zabezpeč aby HuggingFace token bol dostupný pre faster-whisper
import os as _os_hf
if _os_hf.getenv("HF_TOKEN") and not _os_hf.getenv("HUGGINGFACE_HUB_TOKEN"):
    _os_hf.environ["HUGGINGFACE_HUB_TOKEN"] = _os_hf.getenv("HF_TOKEN")

CURRENT_MODEL = "claude-sonnet-4-6"
SLOVAK_VOICE = "sk-SK-LukasNeural"
ENGLISH_VOICE = "en-GB-SoniaNeural"
CURRENT_LANG = "sk"
MAX_HISTORY_TURNS = 8
_is_jarvis_speaking = False
_LOG_FILE = "jarvis.log"
_HUD_PORT = 9876
_WEBUI_PORT = 5000
_hud_event_queue = None  # queue.Queue (thread-safe bridge), inicializuje sa v async_main
_webui_proc = None  # referencia na subprocess Web UI


def log(msg: str):
    """Zapíše timestampovanú správu do jarvis.log aj na konzolu."""
    from datetime import datetime
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass  # log fail nie je kritický


def _get_local_ip():
    """Vráti lokálnu IP adresu (192.168.x.x) pre LAN prístup."""
    try:
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(1)
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def _start_webui():
    """Spustí Web UI server ako samostatný subprocess."""
    global _webui_proc
    webui_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_webui.py")
    if not os.path.exists(webui_path):
        log("⚠️ Web UI: run_webui.py nenájdený")
        return None
    try:
        _webui_proc = subprocess.Popen(
            [sys.executable, webui_path, "--host", "0.0.0.0", "--port", str(_WEBUI_PORT)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return _webui_proc
    except Exception as e:
        log(f"⚠️ Web UI: chyba pri štarte – {e}")
        return None


client = Anthropic()
# Haiku vision client — na overenie obrázkov pred odoslaním
_haiku_api_key = os.environ.get("ANTHROPIC_API_KEY", "")
_haiku_client = Anthropic(api_key=_haiku_api_key, base_url="https://api.anthropic.com") if _haiku_api_key else None

def describe_image(filepath):
    """Overí obsah obrázka cez Claude Haiku vision. Vráti popis."""
    if not _haiku_client:
        return "Chyba: ANTHROPIC_API_KEY nie je nastavený (potrebný pre vision)."
    if not os.path.exists(filepath):
        return f"Chyba: súbor {filepath} neexistuje."
    import base64 as _b64
    try:
        with open(filepath, "rb") as f:
            img_data = _b64.b64encode(f.read()).decode()
        # Detekcia MIME typu podľa base64 hlavičky, nie prípony (Bing často klame)
        mime = "image/jpeg"  # fallback
        prefix20 = img_data[:20]
        if prefix20.startswith("iVBORw0KGgo"): mime = "image/png"
        elif prefix20.startswith("R0lGOD"): mime = "image/gif"
        elif prefix20.startswith("UklGR"): mime = "image/webp"
        elif prefix20.startswith("Qk"): mime = "image/bmp"
        resp = _haiku_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": mime, "data": img_data}},
                {"type": "text", "text": "Stručne popíš čo je na tomto obrázku. Kto/čo to je? Je to jasne rozpoznateľné?"}
            ]}]
        )
        return resp.content[0].text
    except Exception as e:
        return f"Chyba pri analýze obrázka: {e}"

try:
    pygame.mixer.init()
except Exception as e:
    print(f"⚠️ Audio init: {e}")


# ── HUD WebSocket server ────────────────────────────────────────────────

def send_to_hud(event: dict):
    """Pošle event do HUD fronty (thread-safe, non-blocking)."""
    global _hud_event_queue
    try:
        if _hud_event_queue is not None:
            _hud_event_queue.put_nowait(json.dumps(event, ensure_ascii=False))
    except queue.Full:
        pass  # HUD nestíha, zahadzujeme najstaršie eventy
    except Exception as e:
        log(f"HUD event error: {e}")


async def _hud_server():
    """WebSocket server — broadcastuje eventy všetkým pripojeným HUD klientom."""
    import websockets
    clients = set()

    async def handler(ws):
        clients.add(ws)
        try:
            async for _ in ws:
                pass  # nečakáme správy od HUDu
        finally:
            clients.discard(ws)

    async with websockets.serve(handler, "127.0.0.1", _HUD_PORT):
        print(f"🖥️  HUD WebSocket server na porte {_HUD_PORT}")
        loop = asyncio.get_event_loop()
        while True:
            # thread-safe: drain z threading.Queue cez run_in_executor
            msg = await loop.run_in_executor(None, _hud_event_queue.get)
            dead = set()
            for ws in clients:
                try:
                    await ws.send(msg)
                except Exception:
                    dead.add(ws)
            clients -= dead


def _start_hud_process():
    """Spustí HUD overlay ako samostatný subprocess (neblokuje)."""
    try:
        hud_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hud", "overlay.py")
        if os.path.exists(hud_script):
            subprocess.Popen([sys.executable, hud_script],
                             creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
            print("🖥️  HUD overlay spustený")
            return True
        else:
            print("⚠️ HUD script nenájdený")
            return False
    except Exception as e:
        print(f"⚠️ Nepodarilo sa spustiť HUD: {e}")
        return False


SYSTEM_PROMPT = """You are Jarvis, an autonomous AI assistant for user "Fogy". Address him only as Fogy.

CRITICAL: You have REAL tools. Use them. NEVER say you did something unless you actually called the tool. If you say "sent" without calling instagram_dm, you are LYING.

SENDING PHOTOS ON INSTAGRAM:
- If user gives you a FILE PATH (like "D:/JARVIS/web_ui/uploads/images/photo.jpg" or [File: name (path: ...)]), call instagram_dm IMMEDIATELY with that path. Do NOT search, list files, or check memory. Just send.
- If user asks to FIND a photo ("send a photo of Ryan Gosling"), use search_and_list_images → show previews → wait for pick → download → instagram_dm.

LANGUAGE: Match Fogy's language. Prefix EVERY reply with [SK] or [EN].

STYLE: Concise. Don't ask permission — act. Don't narrate what you're doing — just do it.

=== INSTAGRAM PHOTO FLOW ===
When Fogy says "send a photo of X to Y on Instagram":

0. CHECK DISK: file_manager(action="list", path="D:/JARVIS/web_ui/uploads/images")
   If ANY filename contextually matches X → USE IT. Skip to step 4.

CRITICAL — DO NOT DOWNLOAD before Fogy picks! Follow this EXACT order:

1. If NOT on disk: search_and_list_images(query="X") → gives you URLs
   → Send ONE message showing all photos as inline previews:
     "📷 Pick one:
     1. ![](URL1)
     2. ![](URL2)
     3. ![](URL3)"
   → Fogy sees the actual photos rendered in chat and picks a number.
   → DO NOT call search_and_download_image yet. WAIT for Fogy's choice.

2. AFTER Fogy says a number: search_and_download_image(query, index=N)
   → NOW download only that one to web_ui/uploads/images/
   → describe_image() to verify, rename descriptively

3. instagram_dm(). Photo already on disk? Skip to step 3.

3. APPROVED → describe_image() optional, then instagram_dm()

4. instagram_dm(target="Y", message="", attachment_path=<file path>)
   Name the file descriptively based on what it shows (e.g. "ryan_gosling_smiling.jpg")

5. Short confirmation: "[EN] Sent." or "[SK] Poslané."

BE LAZY. Photo already on disk? Skip to step 4.

KNOWN IG CONTACTS:
- 'martinusarovy' / 'martin' / 'martin usarovy' → Martin
- 'skupina' / 'group' / 'partia' → group chat
- 'miska' / 'miška' → Miška
- 'dama' → another contact

TOOLS:
- control_browser: GUI/web automation as an action sequence. Action types: open_url, wait, type, press, hotkey, click_at (value="x,y"), scroll. Set browser="opera" on open_url to launch Opera. Chain blind actions confidently (open → wait → tab/click → type → enter).
- instagram_dm(target, message, attachment_path?): pošle správu na Instagram DM. Ak chceš poslať aj fotku, vyplň attachment_path cestou k už stiahnutému súboru. PREFEROVANÉ pred control_browser pre IG.
- file_manager: filesystem. action ∈ {read, write, append, create_folder, delete, list}. Provide path; content for write/append.
- execute_command: PowerShell command. Returns stdout/stderr/exit.
- web_search: server-side web search. Vráti citácie a snippety priamo. Použi na vyhľadanie informácií, URL, kontaktov.
- image_search(query, count=3): vyhľadá obrázky na webe a vráti URL.
- search_and_list_images(query): vyhľadá obrázky a vráti OČÍSLOVANÝ zoznam (názov, zdroj, veľkosť). Použi keď chceš nechať Fogyho VYBRAŤ ktorý obrázok sa mu páči.
- search_and_download_image(query, index?): stiahne obrázok. index=1 stiahne prvý, index=2 druhý atď. Použi KEĎ UŽ FOGY VYBRAL číslo.
- describe_image(filepath): overí obsah obrázka cez AI vision (Haiku). Použi PRED odoslaním fotky na Instagram — over či obrázok naozaj zobrazuje to čo Fogy chcel. Ak vráti že to nesedí, skús ďalší výsledok z image_search.
- download_file(url, save_path): stiahne akýkoľvek súbor z URL na disk. Kombinuj s image_search alebo vy a web_search.
- take_screenshot: ONLY when blind navigation has failed and you need to see the screen.
- memory: persistent key-value about Fogy. action ∈ {save, read, delete}. Memory is auto-loaded at session start.
- memory_search(query): PREHĽADÁ VŠETKY VRSTVY — Epizodickú pamäť (Tier 1+2), ChromaDB sémantiku (Tier 3), Knowledge Graph (Tier 4), aj Cold Archive (Tier 5). Výsledky zlúči a zoradí. Použi PRED AKOUKOĽVEK ÚLOHOU — aj keď si myslíš že odpoveď poznáš, pamäť vie viac než ty.
- open_web_ui: spustí webové rozhranie JARVISa (http://127.0.0.1:5000). Použi keď Fogy povie "otvor web", "zapni web ui", "spusti web".
- dismiss_hud: skryje HUD overlay. Kľúčová fráza: keď Fogy povie "ďakujem Jarvis" (alebo "to je všetko", "dismiss") — znamená to koniec konverzácie. Zavolaj dismiss_hud a NEODPOVEDAJ textom.
- call_developer_agent: sub-agent rewrites jarvis.py or tools.py based on a natural-language task. Jarvis auto-restarts on success. Use this when Fogy asks you to change your own code.
- system_info(category?): vráti info o systéme – disk, CPU, RAM, GPU, uptime. category='all' (default) vráti všetko; možnosti: 'disk','cpu','ram','gpu','uptime'.
- launch_app(app_name): spustí aplikáciu podľa názvu (spotify, discord, chrome, vscode, calculator, notepad, explorer, opera, steam...).
- get_news(language?, count?): vráti aktuálne novinky z RSS. language='sk' (SME, Aktuality) alebo 'en' (BBC). count=5.
- minecraft_command(command): odošle ľubovoľný Minecraft príkaz cez RCON (list, say, tell, weather, time...).
- minecraft_say(message): odošle správu do Minecraft chatu (ako server).
- minecraft_tell(player, message): odošle súkromnú správu hráčovi v MC.
- minecraft_list_players(): zoznam online hráčov na MC serveri.
- minecraft_recent_chat(minutes=5): prečíta recentné správy z Minecraft logu.
- minecraft_wait_for_player(player, timeout=300): počká kým sa hráč pripojí a pošle mu správu.
- minecraft_check_ai_questions(password): skontroluje MC chat na otázky s heslom !ai <heslo> <otázka>. Použi keď ťa Fogy požiada skontrolovať MC.

WORKFLOW:
- Simple search: image_search(query) → returns URLs
- Download: download_file(url, save_path) → returns file path
- Search + download: search_and_download_image(query) → does both, returns path
- Verify: describe_image(filepath) → AI vision check
- Send: instagram_dm(target, message, attachment_path)
- Fallback: if instagram_dm fails → control_browser with open_url → wait → click_at → type → press enter

For new IG contacts without a nickname, use the full URL https://www.instagram.com/direct/t/<id>/ as target.
"""
AVAILABLE_TOOLS = [
    {
        "name": "control_browser",
        "description": "Sekvencia GUI/web akcií (open_url, wait, type, press, hotkey, click_at, scroll). browser='opera' otvorí Operu.",
        "input_schema": {
            "type": "object",
            "properties": {
                "actions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": ["open_url", "wait", "type", "press", "hotkey", "click_at", "scroll"],
                            },
                            "value": {"type": "string"},
                            "browser": {"type": "string"},
                        },
                        "required": ["action"],
                    },
                }
            },
            "required": ["actions"],
        },
    },
    {
        "name": "download_file",
        "description": "Stiahne súbor z URL na disk (napr. fotku predtým než ju niekam pošleš).",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "save_path": {"type": "string"}
            },
            "required": ["url", "save_path"]
        }
    },
    {
        "name": "instagram_dm",
        "description": "Pošle správu (a voliteľne fotku) cez Instagram DM jedným volaním. Otvorí konverzáciu, vloží text (cez clipboard) a odošle. PREFEROVANÉ riešenie pre IG správy.",
        "input_schema": {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "Prezývka kontaktu (martinusarovy, martin, skupina, group, partia, miska, miška, dama) ALEBO plný URL https://www.instagram.com/direct/t/<id>/",
                },
                "message": {
                    "type": "string",
                    "description": "Text správy, ktorý sa má napísať a odoslať.",
                },
                "attachment_path": {
                    "type": "string",
                    "description": "Cesta k fotke (jpg/png) na nahratie a odoslanie. Voliteľné.",
                },
                "browser": {
                    "type": "string",
                    "description": "'opera' pre Operu, inak default browser. Voliteľné.",
                },
            },
            "required": ["target", "message"],
        },
    },
    {
        "name": "file_manager",
        "description": "Súborový systém: read|write|append|create_folder|delete|list.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["read", "write", "append", "create_folder", "delete", "list"],
                },
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["action", "path"],
        },
    },
    {
        "name": "execute_command",
        "description": "Spustí PowerShell príkaz; vráti stdout/stderr/exit. Voliteľne: timeout a working_dir.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "PowerShell príkaz"},
                "timeout": {"type": "number", "description": "Timeout v sekundách (default 15)"},
                "working_dir": {"type": "string", "description": "Pracovný adresár (voliteľné)"},
            },
            "required": ["command"],
        },
    },
    {
        "type": "web_search_20250305",
        "name": "web_search",
        "max_uses": 10,
    },
    {
        "name": "image_search",
        "description": "Vyhľadá obrázky na webe podľa slovného popisu. Vráti URL adresy obrázkov.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Čo hľadať (napr. 'hora na západe slnka')"},
                "count": {"type": "number", "description": "Počet obrázkov (1-5, default 3)"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_and_download_image",
        "description": "Vyhľadá obrázok podľa popisu a stiahne ho na disk. Vráti cestu k súboru.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Slovný popis obrázka"},
                "save_path": {"type": "string", "description": "Cesta kam uložiť (nepovinné)"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_and_list_images",
        "description": "Vyhľadá obrázky a vráti OČÍSLOVANÝ zoznam (názov, zdroj, veľkosť). Použi keď chceš nechať Fogyho VYBRAŤ ktorý obrázok chce. NEsťahuje — len vypíše výsledky.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Čo hľadať"},
                "max_results": {"type": "number", "description": "Koľko výsledkov (default 5)"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "describe_image",
        "description": "Overí obsah obrázka cez AI vision. Použi PRED odoslaním fotky na Instagram — over či obrázok naozaj zobrazuje to čo Fogy chcel.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filepath": {"type": "string", "description": "Absolútna cesta k obrázku na disku"}
            },
            "required": ["filepath"]
        }
    },
    {
        "name": "take_screenshot",
        "description": "Snímka obrazovky pre vizuálnu analýzu (len ako fallback).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "memory",
        "description": "Dlhodobá pamäť o Fogyovi (save|read|delete).",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["save", "read", "delete"]},
                "key": {"type": "string"},
                "value": {"type": "string"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "system_info",
        "description": "Získa informácie o systéme: disk, CPU, RAM, uptime. category='all' vráti všetko.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["all", "disk", "cpu", "ram", "gpu", "uptime"],
                    "description": "Čo chceš zistiť (default all).",
                },
            },
        },
    },
    {
        "name": "launch_app",
        "description": "Spustí aplikáciu podľa názvu (spotify, discord, chrome, vscode, opera, calculator, notepad, explorer, steam...).",
        "input_schema": {
            "type": "object",
            "properties": {
                "app_name": {
                    "type": "string",
                    "description": "Názov aplikácie (napr. 'spotify', 'discord', 'vscode', 'kalkulačka').",
                },
            },
            "required": ["app_name"],
        },
    },
    {
        "name": "get_news",
        "description": "Získa aktuálne novinky z RSS feedov (SME, Aktuality pre SK; BBC pre EN).",
        "input_schema": {
            "type": "object",
            "properties": {
                "language": {
                    "type": "string",
                    "enum": ["sk", "en"],
                    "description": "'sk' pre slovenské, 'en' pre anglické správy (default sk).",
                },
                "count": {
                    "type": "number",
                    "description": "Počet správ na zdroj (default 5).",
                },
            },
        },
    },
    {
        "name": "call_developer_agent",
        "description": "Programátorský sub-agent upraví jarvis.py alebo tools.py. Jarvis sa automaticky reštartuje.",
        "input_schema": {
            "type": "object",
            "properties": {
                "target_filename": {"type": "string"},
                "task_description": {"type": "string"},
            },
            "required": ["target_filename", "task_description"],
        },
        "cache_control": {"type": "ephemeral"},
    },
    {
        "name": "minecraft_command",
        "description": "Odošle ľubovoľný Minecraft príkaz cez RCON (napr. 'list', 'say Ahoj', 'time set day'). Vyžaduje RCON na MC serveri.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Minecraft príkaz (bez lomítka)"},
            },
            "required": ["command"],
        },
    },
    {
        "name": "minecraft_say",
        "description": "Odošle správu do Minecraft chatu ako server.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
            },
            "required": ["message"],
        },
    },
    {
        "name": "minecraft_tell",
        "description": "Odošle súkromnú správu hráčovi na Minecraft serveri.",
        "input_schema": {
            "type": "object",
            "properties": {
                "player": {"type": "string"},
                "message": {"type": "string"},
            },
            "required": ["player", "message"],
        },
    },
    {
        "name": "minecraft_list_players",
        "description": "Získa zoznam online hráčov na Minecraft serveri.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "minecraft_recent_chat",
        "description": "Prečíta recentné správy z Minecraft chatu (z log súboru).",
        "input_schema": {
            "type": "object",
            "properties": {
                "minutes": {"type": "number", "description": "Koľko minút dozadu (default 5)"},
            },
        },
    },
    {
        "name": "minecraft_wait_for_player",
        "description": "Počká kým sa hráč pripojí na Minecraft server. Po pripojení môžeš poslať správu.",
        "input_schema": {
            "type": "object",
            "properties": {
                "player_name": {"type": "string", "description": "Meno hráča"},
                "timeout": {"type": "number", "description": "Max čakať v sekundách (default 300)"},
            },
            "required": ["player_name"],
        },
    },
    {
        "name": "minecraft_check_ai_questions",
        "description": "Skontroluje Minecraft chat na otázky pre AI s heslom. Hráči píšu: !ai <heslo> <otázka>. Použi keď Fogy povie 'skontroluj minecraft' alebo 'pozri či niekto niečo písal na MC'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "password": {"type": "string", "description": "RCON heslo (predvolené 12345)"},
            },
        },
    },
    {
        "name": "memory_search",
        "description": "Prehľadá VŠETKY vrstvy pamäte naraz (Epizodická → ChromaDB → Knowledge Graph → Cold Archive), zlúči a zoradí výsledky. Toto je HLAVNÝ nástroj na vyhľadávanie v pamäti. Použi PRED akoukoľvek úlohou — aj keď si myslíš že odpoveď poznáš, pamäťový systém vie viac než ty. Hľadaj fakty o Fogyovi, projektové znalosti, predchádzajúce riešenia, bugy, rozhodnutia.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Čo hľadať (napr. 'kto je Miška', 'bug s mikrofónom', 'architektúra pamäte', 'čo sme robili minule')"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "open_web_ui",
        "description": "Spustí webové rozhranie JARVISa na http://127.0.0.1:5000/.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "dismiss_hud",
        "description": "Skryje HUD overlay. Zavolaj keď Fogy povie 'ďakujem Jarvis', 'to je všetko' alebo 'dismiss'. NEODPOVEDAJ textom — len zavolaj tool.",
        "input_schema": {"type": "object", "properties": {}},
    },
]


def speak(text, language="sk"):
    global _is_jarvis_speaking
    if not text:
        return
    _is_jarvis_speaking = True
    print(f"\n🤖 Jarvis: {text}")