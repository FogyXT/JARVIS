"""
Instagram DM — používa existujúcu Operu GX cez pyautogui.
Jednoduché, spoľahlivé, žiadne API credentials. Len klikanie ako človek.
"""
import os
import time
import pyautogui
import subprocess
from tools import _set_clipboard, _set_clipboard_image

def _load_contacts():
    """Načíta kontakty z externého JSON súboru (nie je v git repozitári)."""
    import json
    contacts_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "instagram_contacts.json")
    try:
        with open(contacts_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

INSTAGRAM_CONTACTS = _load_contacts()


def _ensure_opera_focused():
    """Aktivuje a maximalizuje existujúce okno Opery."""
    try:
        wins = pyautogui.getWindowsWithTitle("Opera")
        if wins:
            win = wins[0]
            if not win.isMaximized:
                win.maximize()
                time.sleep(0.5)
            win.activate()
            time.sleep(0.5)
            return True
    except Exception:
        pass
    return False


def instagram_dm(target, message, browser=None, attachment_path=None):
    """
    Pošle správu (a voliteľne fotku) cez Instagram DM.
    Používa existujúcu Operu — otvorí novú kartu, pošle, zatvorí.
    """
    try:
        if not target:
            return "Chyba: target je povinný."

        key = target.lower().strip()
        url = INSTAGRAM_CONTACTS.get(key)
        if not url:
            if target.startswith("http"):
                url = target
            elif target.isdigit():
                url = f"https://www.instagram.com/direct/t/{target}/"
            else:
                return f"Neznámy kontakt: {target}"

        # Aktivuj Operu
        if not _ensure_opera_focused():
            return "Chyba: Opera nie je spustená. Otvor Operu a prihlás sa do Instagramu."

        # Otvor DM URL v novej karte
        pyautogui.hotkey("ctrl", "t")
        time.sleep(0.5)
        pyautogui.hotkey("ctrl", "l")
        time.sleep(0.3)
        _set_clipboard(url)
        pyautogui.hotkey("ctrl", "v")
        pyautogui.press("enter")
        print(f"[IG DM] Otvorené: {target}, čakám 4s...")
        time.sleep(4.0)

        # --- Text NAJPRV (kým je chat prázdny, píše sa rýchlejšie) ---
        if message:
            print(f"[IG DM] Píšem: {message[:60]}")
            if _set_clipboard(message):
                pyautogui.hotkey("ctrl", "v")
            else:
                pyautogui.write(message, interval=0.03)
            time.sleep(0.3)

        # --- Fotka ---
        image_sent = False
        if attachment_path:
            resolved = None
            if os.path.isabs(attachment_path) and os.path.exists(attachment_path):
                resolved = attachment_path
            else:
                for base in [os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web_ui")]:
                    candidate = os.path.join(base, attachment_path.lstrip("/").lstrip("\\"))
                    if os.path.exists(candidate):
                        resolved = os.path.abspath(candidate)
                        break
                if not resolved and os.path.exists(attachment_path):
                    resolved = os.path.abspath(attachment_path)

            if resolved:
                print(f"[IG DM] Nahrávam: {os.path.basename(resolved)}")
                if _set_clipboard_image(resolved):
                    time.sleep(0.3)
                    pyautogui.hotkey("ctrl", "v")
                    image_sent = True
                    # Dynamické čakanie: Enter sa nedá stlačiť kým sa fotka nahráva
                    # Počkáme len 1.5s — ak fotka malá, je hotovo; ak veľká, aj tak pošleme
                    print("[IG DM] Čakám na upload...")
                    time.sleep(2.0)
                else:
                    print("[IG DM] Clipboard zlyhalo")
            else:
                print(f"[IG DM] Fotka nenájdená: {attachment_path}")

        # --- Odoslanie (Enter odošle správu aj s fotkou) ---
        print("[IG DM] Odosielam...")
        pyautogui.press("enter")
        time.sleep(1.5)

        # --- Zatvor kartu ---
        pyautogui.hotkey("ctrl", "w")
        print("[IG DM] ✅ Karta zatvorená")

        result = f"Správa odoslaná pre {target} (photo: {'áno' if image_sent else 'nie'})"
        print(f"[IG DM] ✅ {result}")
        return result

    except Exception as e:
        return f"Chyba pri odosielaní IG DM: {e}"
