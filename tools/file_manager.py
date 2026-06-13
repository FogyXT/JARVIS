import os
import shutil
import time
from datetime import datetime


def file_manager(action, path, content=None):
    """Správa súborov a adresárov na lokálnom disku.

    action: 'read' | 'write' | 'append' | 'create_folder' | 'delete' | 'list'
    pre 'read' automaticky detekuje binárne súbory a vráti varovanie.
    pre 'list' zobrazí veľkosť a dátum modifikácie.
    """
    # Bezpečnosť: blokuj path traversal
    if ".." in path.replace("\\", "/").split("/"):
        return "Chyba: path traversal (..) nie je povolený."
    # Blokuj zápis/mazanie do kritických systémových ciest
    _critical_roots = [r"C:\Windows", r"C:\Program Files", r"C:\Program Files (x86)"]
    if action in ("write", "append", "delete", "create_folder"):
        try:
            abs_path = os.path.abspath(path)
            for cr in _critical_roots:
                if abs_path.lower().startswith(cr.lower()):
                    return f"Chyba: zápis do {cr} nie je povolený."
        except Exception:
            pass
    try:
        if action == "read":
            if not os.path.isfile(path):
                return f"Súbor neexistuje: '{path}'"

            # Detekcia binárneho súboru — skúsime prvých 1024 bajtov
            try:
                with open(path, "rb") as f:
                    head = f.read(1024)
                # Ak obsahuje null byte, je to binárny súbor
                if b"\x00" in head:
                    size = os.path.getsize(path)
                    return f"[Binárny súbor: {path}, {size}B. Na čítanie použite iný nástroj.]"
            except Exception:
                pass

            with open(path, "r", encoding="utf-8", errors="replace") as f:
                data = f.read()
            if len(data) <= 10000:
                return data
            return data[:10000] + f"\n... [orezané, celkom {len(data)} znakov]"

        if action == "write":
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            text = content or ""
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            return f"Zapísané: '{path}' ({len(text)} znakov)"

        if action == "append":
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(content or "")
            return f"Pripojené k '{path}' ({len(content or '')} znakov)"

        if action == "create_folder":
            os.makedirs(path, exist_ok=True)
            return f"Zložka vytvorená: '{path}'"

        if action == "delete":
            if not os.path.exists(path):
                return f"Cesta neexistuje: '{path}'"
            if os.path.isdir(path):
                shutil.rmtree(path)
                return f"Zložka vymazaná: '{path}'"
            else:
                os.remove(path)
                return f"Súbor vymazaný: '{path}'"

        if action == "list":
            if not os.path.exists(path):
                return f"Cesta neexistuje: '{path}'"
            if not os.path.isdir(path):
                return f"Nie je adresár: '{path}'"

            entries = []
            # Hlavička
            entries.append(f" Výpis adresára: {path}")
            entries.append(f" {'Názov':40} {'Veľkosť':>10} {'Dátum':20}")
            entries.append("-" * 75)

            for name in sorted(os.listdir(path)):
                full = os.path.join(path, name)
                try:
                    stat = os.stat(full)
                    size = stat.st_size
                    mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
                except OSError:
                    size = 0
                    mtime = "?"

                if os.path.isdir(full):
                    size_str = "DIR".rjust(10)
                elif size < 1024:
                    size_str = f"{size}B".rjust(10)
                elif size < 1024 ** 2:
                    size_str = f"{size/1024:.1f}KB".rjust(10)
                else:
                    size_str = f"{size/1024**2:.1f}MB".rjust(10)

                entries.append(f" {name[:38]:40} {size_str} {mtime}")

            return "\n".join(entries)

        return f"Neznáma akcia: {action}"
    except PermissionError:
        return f"Chyba: prístup odmietnutý pre '{path}'"
    except Exception as e:
        return f"Chyba file_manager({action}, {path}): {e}"
