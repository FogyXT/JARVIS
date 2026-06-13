import os
import json
import time
import subprocess
import pyautogui

# Vypnúť fail-safe aby myš v rohu neprerušila sekvenciu
pyautogui.FAILSAFE = False

def _get_opera_processes():
    """Vráti zoznam (pid, main_window_title) pre všetky Opera procesy."""
    results = []
    try:
        cmd = "@(Get-Process opera -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object Id, MainWindowTitle | ConvertTo-Json -Compress)"
        res = subprocess.run(["powershell", "-NoProfile", "-Command", cmd],
                             capture_output=True, text=True, errors="replace", timeout=5)
        raw = res.stdout.strip()
        if not raw:
            return results
        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]
        for p in data:
            results.append((p.get("Id"), p.get("MainWindowTitle", "")))
    except Exception as e:
        print(f"Chyba Get-Process: {e}")
    return results

def is_opera_running_custom():
    procs = _get_opera_processes()
    return len(procs) > 0

def focus_opera_window():
    """Aktivuje Opera okno. Používa pygetwindow + klik na title bar (fyzický focus)."""
    try:
        import pygetwindow as gw
        opera_wins = gw.getWindowsWithTitle('opera')
        if not opera_wins:
            opera_wins = gw.getWindowsWithTitle('Opera')
        # Filter out empty/blank titles
        opera_wins = [w for w in opera_wins if w.title.strip()]
        if opera_wins:
            win = opera_wins[0]
            print(f"[Focus] Našiel som okno: '{win.title[:40]}'")
            if win.isMinimized:
                win.restore()
                time.sleep(0.3)
            cx = win.left + win.width // 2
            cy = win.top + 5
            pyautogui.click(cx, cy)
            time.sleep(0.2)
            print(f"[Focus] Opera aktivovaná klikom na title bar")
            return True
    except ImportError:
        print("[Focus] pygetwindow nie je k dispozícii")
    except Exception as e:
        print(f"[Focus] pygetwindow chyba: {e}")

    # Fallback: pywinauto
    try:
        from pywinauto import Desktop
        desktop = Desktop(backend="uia")
        for win in desktop.windows():
            title = (win.window_text() or "").lower()
            if "opera" in title or "instagram" in title:
                print(f"[Focus] Aktivujem okno: '{win.window_text()}'")
                win.set_focus()
                return True
    except ImportError:
        pass
    except Exception as e:
        print(f"[Focus] pywinauto chyba: {e}")

    # Fallback: PowerShell (bez Add-Type, priamo cez .NET)
    try:
        cmd = '''
        Add-Type -AssemblyName Microsoft.VisualBasic
        $p = Get-Process opera | Where-Object { $_.MainWindowHandle -ne 0 }
        if ($p) {
            [Microsoft.VisualBasic.Interaction]::AppActivate($p[0].Id)
            return $true
        }
        return $false
        '''
        res = subprocess.run(["powershell", "-NoProfile", "-Command", cmd],
                             capture_output=True, text=True, timeout=5)
        if res.stdout and "True" in res.stdout:
            print("[Focus] Opera aktivovaná cez AppActivate")
            return True
    except Exception as e:
        print(f"[Focus] AppActivate zlyhal: {e}")

    return False

def _get_opera_window_title():
    """Získa názov aktuálneho tabu Opera okna cez PowerShell."""
    try:
        cmd = "$p = Get-Process opera | Where-Object { $_.MainWindowHandle -ne 0 }; if ($p) { $p[0].MainWindowTitle } else { '' }"
        res = subprocess.run(["powershell", "-NoProfile", "-Command", cmd],
                             capture_output=True, text=True, timeout=5)
        return res.stdout.strip()
    except Exception:
        return ""

def switch_to_tab_by_title(substring, max_tabs=20):
    """Skontroluje či aktuálny tab v Opere obsahuje `substring`.
    Vráti True ak áno, False ak nie. Necyklí cez karty."""
    if not isinstance(substring, str) or not substring:
        return False
    focused = focus_opera_window()
    if not focused:
        return False
    time.sleep(0.3)

    title = _get_opera_window_title()
    if substring.lower() in title.lower():
        print(f"[TabSwitch] Aktuálny tab je '{substring}'")
        return True

    print(f"[TabSwitch] Aktuálny tab nie je '{substring}'")
    return False

def open_with_opera(url, new_tab=True):
    """Otvorí URL v Opere.
    new_tab=True (predvolené) → nová karta (Ctrl+T)
    new_tab=False → prepíše aktuálnu kartu (pre IG)
    """
    candidates = [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Opera\opera.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Opera\launcher.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Opera GX\launcher.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Opera GX\opera.exe"),
        r"C:\Program Files\Opera\opera.exe",
        r"C:\Program Files\Opera GX\opera.exe"
    ]
    opera_bin = None
    for p in candidates:
        if os.path.exists(p):
            opera_bin = p
            break

    from tools import _set_clipboard

    if is_opera_running_custom():
        focused = focus_opera_window()
        if focused:
            print("[Opera Nav] Opera beží, prepisujem URL v existujúcom tabe...")
            time.sleep(0.5)
            if new_tab:
                pyautogui.hotkey("ctrl", "t")
                time.sleep(0.5)
            pyautogui.hotkey("ctrl", "l")
            time.sleep(0.3)
            _set_clipboard(url)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.3)
            pyautogui.press("enter")
            return "existing_instance"

    print("[Opera Nav] Spúšťam novú inštanciu Opery...")
    try:
        if opera_bin:
            subprocess.Popen([opera_bin, url])
        else:
            import webbrowser
            webbrowser.open(url)
    except Exception as e:
        print(f"[Opera Nav] Chyba: {e}. Otváram cez defaultný prehliadač.")
        import webbrowser
        webbrowser.open(url)
    return "new_instance"

pyautogui.PAUSE = 0.15

def control_browser(actions):
    """Spustí sekvenciu nízkoúrovňových GUI akcií v prehliadači."""
    from tools import _set_clipboard
    log = []
    for step in actions:
        action = step.get("action")
        value = step.get("value", "")
        try:
            if action == "open_url":
                open_with_opera(value)
                time.sleep(2.5)
            elif action == "type":
                if _set_clipboard(value):
                    pyautogui.hotkey("ctrl", "v")
                else:
                    pyautogui.write(value)
            elif action == "press":
                pyautogui.press(value)
            elif action == "hotkey":
                keys = [k.strip() for k in value.split("+")]
                pyautogui.hotkey(*keys)
            elif action == "click_at":
                parts = value.split(",")
                if len(parts) == 2:
                    x = int(parts[0].strip())
                    y = int(parts[1].strip())
                    pyautogui.click(x, y)
            elif action == "scroll":
                amount = int(value) if value else -100
                pyautogui.scroll(amount)
            elif action == "wait":
                time.sleep(float(value))
            log.append(f"OK: {action}")
        except Exception as e:
            log.append(f"FAIL: {action} ({e})")
    return "\n".join(log)

def take_screenshot():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "screenshot.png")
    # Podpora viacerých monitorov — zachytí všetky obrazovky
    try:
        import PIL.ImageGrab
        # Windows: all_screens=True pre multi-monitor
        img = PIL.ImageGrab.grab(all_screens=True)
    except Exception:
        img = pyautogui.screenshot()
    img.save(path)
    return os.path.abspath(path)