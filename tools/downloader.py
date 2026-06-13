import os
import requests

# Kategórie podľa prípony — rovnaké ako web_ui/app.py
_FILE_CATEGORIES = {
    "images":      {"jpg", "jpeg", "png", "gif", "webp", "bmp", "svg", "ico", "heic", "heif"},
    "documents":   {"pdf", "txt", "rtf", "odt", "doc", "docx", "md"},
    "spreadsheets":{"xls", "xlsx", "csv", "ods"},
    "videos":      {"mp4", "avi", "mkv", "mov", "wmv", "flv", "webm"},
    "audio":       {"mp3", "wav", "ogg", "flac", "aac", "m4a", "wma"},
    "archives":    {"zip", "rar", "7z", "tar", "gz", "bz2", "xz"},
    "code":        {"py", "js", "ts", "html", "css", "php", "java", "cpp", "c", "h", "rs", "go", "swift", "kt"},
}

def _get_category(filename):
    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    for cat, exts in _FILE_CATEGORIES.items():
        if ext in exts:
            return cat
    return "documents"  # default

def _uploads_dir():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "web_ui", "uploads")

def download_file(url, save_path):
    """Stiahne súbor z URL na disk. Auto-kategorizuje do web_ui/uploads/<kategoria>/."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        r = requests.get(url, headers=headers, stream=True, timeout=30)
        r.raise_for_status()

        # Ak save_path je adresár, extrahuj názov z URL
        norm_path = save_path.replace("/", os.sep).replace("\\", os.sep)
        if norm_path.endswith(os.sep) or os.path.isdir(norm_path):
            filename = url.split("/")[-1].split("?")[0] or "downloaded_file"
            save_path = os.path.join(save_path, filename)

        # Ak cesta nemá adresár (len názov súboru) → auto-kategorizuj do uploads/
        parent = os.path.dirname(save_path)
        if not parent or parent == "":
            cat = _get_category(os.path.basename(save_path))
            save_path = os.path.join(_uploads_dir(), cat, os.path.basename(save_path))

        # Vytvor rodičovské adresáre
        parent = os.path.dirname(save_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        with open(save_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=65536):
                f.write(chunk)
        size = os.path.getsize(save_path)
        ctype = r.headers.get("Content-Type", "?")
        return f"Stiahnuté: {save_path} ({size}B, {ctype})"
    except Exception as e:
        return f"Chyba pri sťahovaní: {e}"