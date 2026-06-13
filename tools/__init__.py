import os
import sys
import json
import time
import shutil
import subprocess

def _set_clipboard(text):
    """Pomocná funkcia pre textovú schránku (používaná interne).
    Používa stdin pipe namiesto command-line argumentu, aby fungovali
    špeciálne znaky (nové riadky, úvodzovky, atď)."""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "($input | Out-String).TrimEnd() | Set-Clipboard"],
            input=text,
            text=True,
            capture_output=True, timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


def _set_clipboard_image(image_path):
    """Skopíruje obrázok do schránky pre Ctrl+V vloženie. Podporuje všetky formáty.
    Používa Pillow na konverziu do BMP + PowerShell na vloženie.
    Vráti True ak sa podarilo."""
    try:
        abs_path = os.path.abspath(image_path)
        if not os.path.exists(abs_path):
            print(f"[Clipboard] Súbor neexistuje: {abs_path}")
            return False

        # Skús priamo PowerShell (rýchlejšie pre bežné formáty)
        # Ak zlyhá, skúsime cez Pillow konverziu
        ps_direct = f'''
        Add-Type -AssemblyName System.Drawing
        Add-Type -AssemblyName System.Windows.Forms
        $path = "{abs_path}"
        if (-not (Test-Path $path)) {{ exit 1 }}
        try {{
            $img = [System.Drawing.Image]::FromFile($path)
            [System.Windows.Forms.Clipboard]::SetImage($img)
            $img.Dispose()
            Write-Output "OK"
        }} catch {{ exit 2 }}
        '''
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_direct],
            capture_output=True, text=True, timeout=15
        )
        if "OK" in r.stdout:
            return True

        # Priama cesta zlyhala (napr. WEBP formát) — skús cez Pillow konverziu
        print(f"[Clipboard] Priame vloženie zlyhalo, skúšam cez Pillow...")
        from PIL import Image as PILImage
        import tempfile

        tmp_bmp = os.path.join(tempfile.gettempdir(), f"jarvis_clip_{os.getpid()}.bmp")
        try:
            img = PILImage.open(abs_path)
            if img.mode in ('RGBA', 'LA', 'P', 'PA'):
                img = img.convert('RGB')
            img.save(tmp_bmp, format='BMP')
            img.close()

            # Vlož skonvertovaný BMP do schránky
            ps_bmp = f'''
            Add-Type -AssemblyName System.Windows.Forms
            $path = "{tmp_bmp}"
            $img = [System.Drawing.Image]::FromFile($path)
            [System.Windows.Forms.Clipboard]::SetImage($img)
            $img.Dispose()
            Write-Output "OK"
            '''
            r2 = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_bmp],
                capture_output=True, text=True, timeout=15
            )
            return "OK" in r2.stdout
        finally:
            try:
                if os.path.exists(tmp_bmp):
                    os.remove(tmp_bmp)
            except Exception:
                pass
    except Exception as e:
        print(f"[Clipboard] Chyba: {e}")
        return False

# Importujeme funkcie z pod-modulov v tomto priečinku
from .memory import memory
from .rag_memory import rag_search, rag_save, rag_read, rag_delete
import subprocess as _subprocess
import sys as _sys
import os as _os

def open_web_ui():
    """Spustí Web UI ako samostatný proces (ak ešte nebeží)."""
    import socket
    # Skontroluj či už Web UI nebeží na porte 5000
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect(("127.0.0.1", 5000))
        s.close()
        return "🌐 Web UI už beží — http://127.0.0.1:5000"
    except (ConnectionRefusedError, OSError):
        pass
    finally:
        s.close()

    webui_path = _os.path.join(
        _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
        "run_webui.py"
    )
    try:
        _subprocess.Popen([_sys.executable, webui_path])
        return "🌐 Web UI spustené — http://127.0.0.1:5000"
    except Exception as e:
        return f"Chyba pri spúšťaní Web UI: {e}"
from .file_manager import file_manager
from .downloader import download_file
# Client-side web_search is DEPRECATED — server-side Anthropic built-in handles it.
# Import kept for reference/manual fallback. Do not route to this from _execute_tool.
from .web_search import web_search  # noqa: F401 (deprecated, kept as fallback)
from .image_search import image_search, search_and_download_image, search_and_list_images
from .instagram import instagram_dm
from .browser import control_browser, take_screenshot
from .system import execute_command
from .system_info import system_info
from .launch_app import launch_app
from .news import get_news
from .minecraft import (
    minecraft_command, minecraft_say, minecraft_tell,
    minecraft_list_players, minecraft_recent_chat, minecraft_wait_for_player,
    minecraft_check_ai_questions,
)

def call_developer_agent(target_filename, task_description):
    """
    Developer agent, ktorý dokáže bezpečne prepisovať súbory.
    """
    from anthropic import Anthropic
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return "Chyba: ANTHROPIC_API_KEY nie je nastavený v .env"
    sub = Anthropic(api_key=api_key, base_url="https://api.anthropic.com")
    current_code = ""
    if os.path.exists(target_filename):
        with open(target_filename, "r", encoding="utf-8") as f:
            current_code = f.read()

    print(f"\n🧠 [Dev agent pracuje na: {target_filename}]")

    dev_system = (
        "Si elite Python engineer. Tvoja jediná úloha: vrátiť KOMPLETNÝ upravený obsah "
        "súboru pripravený na priame uloženie. ŽIADNE markdown bloky, ŽIADNE komentáre k zmenám, "
        "ŽIADNE vysvetlenia, ŽIADNE diff. Iba čistý finálny zdrojový kód."
    )

    user_msg = (
        f"Súbor: {target_filename}\n\n"
        f"=== AKTUÁLNY OBSAH ===\n{current_code or '(prázdny)'}\n=== KONIEC ===\n\n"
        f"ÚLOHA: {task_description}\n\n"
        "Vráť celý súbor po úprave."
    )

    try:
        resp = sub.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=8000,
            system=dev_system,
            messages=[{"role": "user", "content": user_msg}],
        )
        new_code = resp.content[0].text.strip()

        for fence in ("```python", "```py", "```"):
            if new_code.startswith(fence):
                new_code = new_code[len(fence):].lstrip("\n")
                break
        if new_code.endswith("```"):
            new_code = new_code[:-3].rstrip()

        if not new_code:
            return "Dev agent nevrátil kód."

        if os.path.exists(target_filename):
            shutil.copy2(target_filename, target_filename + ".bak")

        with open(target_filename, "w", encoding="utf-8") as f:
            f.write(new_code)
        
        # Ak sa zmení Jarvis alebo čokoľvek v tools, reštartujeme
        base = os.path.basename(target_filename)
        if base == "jarvis.py" or "/tools/" in target_filename.replace("\\", "/"):
            print("🔄 Súbor zmenený, automaticky reštartujem proces...")
            time.sleep(0.5)
            os.execv(sys.executable, [sys.executable] + sys.argv)
            
        return f"Súbor '{target_filename}' bol úspešne upravený."
    except Exception as e:
        return f"Chyba Dev agenta: {e}"