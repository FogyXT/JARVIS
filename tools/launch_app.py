import subprocess
import os
import shutil

# Mapa známych aplikácií → executable alebo URI schéma
APPS = {
    # Prehliadače
    "opera": "opera",
    "opera gx": "opera",
    "chrome": "chrome",
    "google chrome": "chrome",
    "firefox": "firefox",
    "mozilla": "firefox",
    "edge": "msedge",
    "microsoft edge": "msedge",
    "brave": "brave",
    # Komunikácia
    "discord": "discord",
    "whatsapp": "whatsapp",
    "telegram": "telegram",
    "signal": "signal",
    "messenger": "ms-messenger:",
    # Média
    "spotify": "spotify",
    "vlc": "vlc",
    # Vývoj
    "vscode": "code",
    "visual studio code": "code",
    "terminal": "powershell",
    "cmd": "cmd",
    "powershell": "powershell",
    "python": "python",
    # Systémové
    "kalkulačka": "calc",
    "calculator": "calc",
    "poznámkový blok": "notepad",
    "notepad": "notepad",
    "notepad++": "notepad++",
    "prieskumník": "explorer",
    "explorer": "explorer",
    "file explorer": "explorer",
    "task manager": "taskmgr",
    "správca úloh": "taskmgr",
    "nastavenia": "ms-settings:",
    "settings": "ms-settings:",
    "control panel": "control",
    "ovládací panel": "control",
    "príkazový riadok": "cmd",
    "command prompt": "cmd",
    # Hry
    "steam": "steam",
    "epic games": "com.epicgames.launcher",
    "xbox": "xbox",
    "minecraft": "javaw",
    "minecraft server": "java",
}


def _find_exe(name):
    """Nájde cestu k executable v PATH a overí že existuje."""
    found = shutil.which(name)
    return found if (found and os.path.isfile(found)) else None


def launch_app(app_name):
    """Spustí aplikáciu podľa názvu.

    Podporuje: prehliadače, discord, spotify, vscode, terminal,
    calculator, notepad, explorer, steam, atď.
    """
    key = app_name.strip().lower()
    cmd = APPS.get(key)

    if not cmd:
        # Skús priamo ako názov executable
        exe = _find_exe(app_name)
        if exe:
            cmd = exe
        else:
            known = ", ".join(sorted(set(APPS.keys())))
            return f"Neznáma aplikácia: '{app_name}'. Známé: {known}"

    try:
        # URI schémy (končiace dvojbodkou)
        if cmd.endswith(":"):
            subprocess.Popen(["start", "", cmd], shell=True)
        elif _find_exe(cmd):
            subprocess.Popen([cmd])
        else:
            # Fallback cez start
            subprocess.Popen(["start", "", cmd], shell=True)
        return f"Spúšťam: {app_name}"
    except FileNotFoundError:
        return f"Aplikácia '{app_name}' sa nenašla."
    except Exception as e:
        return f"Chyba pri spúšťaní '{app_name}': {e}"
