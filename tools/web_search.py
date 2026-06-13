import os
import re
import json
import time
import subprocess
import requests
from datetime import datetime
from urllib.parse import quote_plus

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
_UA_FALLBACK = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0"

# Adresár pre ukladanie výsledkov vyhľadávania
WEBSEARCHES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "websearches")


# ──────────────────────────────────────────────
# Storage helpers
# ──────────────────────────────────────────────

def _slug(query):
    """Vytvorí bezpečný názov adresára z query."""
    safe = re.sub(r'[^\w\-_ ]', '_', query)[:60].strip("_ ").lower().replace(" ", "-")
    return safe if safe else f"search_{int(time.time())}"


def _save_search(query, results_text, result_urls, saved_pages):
    """Uloží výsledky vyhľadávania do websearches/<slug>/."""
    slug = _slug(query)
    search_dir = os.path.join(WEBSEARCHES_DIR, slug)
    os.makedirs(search_dir, exist_ok=True)

    # Search results text
    with open(os.path.join(search_dir, "search.txt"), "w", encoding="utf-8") as f:
        f.write(results_text)

    # Metadata
    meta = {
        "query": query,
        "timestamp": datetime.now().isoformat(),
        "urls_found": result_urls,
        "url_count": len(result_urls),
        "pages_saved": len(saved_pages),
    }
    with open(os.path.join(search_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    # Saved pages detail
    if saved_pages:
        with open(os.path.join(search_dir, "pages.json"), "w", encoding="utf-8") as f:
            json.dump(saved_pages, f, ensure_ascii=False, indent=2)

    # Global index
    index_path = os.path.join(WEBSEARCHES_DIR, "index.json")
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            index = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        index = {}
    index[slug] = {
        "query": query,
        "timestamp": datetime.now().isoformat(),
        "url_count": len(result_urls),
        "pages_saved": len(saved_pages),
    }
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    return search_dir


def _fetch_pages(urls, search_dir, max_pages=3):
    """Navštívi výsledky a stiahne HTML stránok."""
    headers = {"User-Agent": _UA, "Accept-Language": "sk-SK,sk;q=0.9,en;q=0.8"}
    saved = []

    for i, url in enumerate(urls[:max_pages]):
        if not url or not url.startswith("http"):
            continue
        try:
            print(f"  ↳ Sťahujem stránku {i+1}: {url[:80]}...")
            r = requests.get(url, headers=headers, timeout=12)
            ct = r.headers.get("Content-Type", "")

            if "text/html" not in ct and "text/plain" not in ct:
                print(f"     Preskočené (Content-Type: {ct})")
                continue

            r.encoding = r.apparent_encoding or "utf-8"
            html = r.text

            # Extrahuj title pre čitateľný názov súboru
            title_match = re.search(r'<title[^>]*>([^<]+)</title>', html, re.I | re.S)
            page_title = title_match.group(1).strip()[:60] if title_match else f"page_{i}"

            # Ulož HTML
            safe_name = re.sub(r'[^\w\-_ ]', '_', page_title)[:50].strip("_ ")
            filename = f"{i}_{safe_name}.html"
            filepath = os.path.join(search_dir, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(html[:150000])  # max 150k znakov

            saved.append({
                "index": i,
                "url": url,
                "title": page_title,
                "file": filename,
                "path": filepath,
                "size": len(html),
                "content_type": ct,
            })
            print(f"     ✓ Uložené: {filename} ({len(html)} znakov)")
        except requests.exceptions.Timeout:
            print(f"     ⏱ Timeout: {url[:60]}")
        except Exception as e:
            print(f"     ✗ Chyba: {e}")

    return saved


def _extract_urls_from_text(text):
    """Extrahuje URL z textu (napr. z browser search výsledkov)."""
    urls = re.findall(r'https?://[^\s<>"\')\]]+', text)
    # Filtruj google/instagram/socialne site a duplicity
    seen = set()
    clean = []
    skip_domains = ("google.com/search", "accounts.google.com", "policies.google",
                    "support.google", "instagram.com")
    for url in urls:
        key = url.split("//")[1].rstrip("/") if "//" in url else url
        if key in seen:
            continue
        seen.add(key)
        if any(d in url for d in skip_domains):
            continue
        # Remove tracking params
        clean_url = url.split("&sa=")[0].split("?sa=")[0]
        clean.append(clean_url)
    return clean


def _extract_urls_from_http_results(http_results):
    """Extrahuje URL z HTTP search výsledkov (list formátovaných stringov)."""
    urls = []
    for line in http_results:
        # Each result looks like "• Title\n  snippet\n  https://..."
        found = re.findall(r'https?://[^\s\n]+', line)
        urls.extend(found)
    return urls


# ──────────────────────────────────────────────
# Search backends
# ──────────────────────────────────────────────

def _search_via_browser(query):
    """Vyhľadá cez Google v Opere — spoľahlivejšie ako HTTP scraping."""
    try:
        import pyautogui
        from tools.browser import open_with_opera
        from tools import _set_clipboard

        search_url = f"https://www.google.com/search?q={quote_plus(query)}&hl=sk"
        print(f"[Browser Search] Otváram Google v Opere...")

        nav_method = open_with_opera(search_url)
        wait = 3.0 if nav_method == "existing_instance" else 6.0
        time.sleep(wait)

        print("[Browser Search] Kopírujem výsledky (Ctrl+A, Ctrl+C)...")
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.3)
        pyautogui.hotkey("ctrl", "c")
        time.sleep(0.3)

        ps_cmd = "Get-Clipboard -Raw -TextFormatType Text"
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True, text=True, errors="replace", timeout=5
        )
        raw_text = (result.stdout or "").strip()

        # Zatvoriť kartu
        pyautogui.hotkey("ctrl", "w")
        print("[Browser Search] Karta zatvorená.")

        if raw_text and len(raw_text) > 50:
            lines = raw_text.split("\n")
            filtered = []
            capture = True
            for line in lines:
                stripped = line.strip()
                if not stripped:
                    continue
                if any(kw in stripped.lower() for kw in ["súvisiace vyhľadávania", "related searches", "z profilu"]):
                    capture = False
                    continue
                if capture and len(stripped) > 20:
                    filtered.append(stripped)

            result_text = "\n".join(filtered[:30]) if filtered else raw_text[:3000]
            return f"[Google via Opera]\n{result_text[:3000]}", raw_text[:5000]
        return None, None
    except Exception as e:
        print(f"[Browser Search] Zlyhalo: {e}")
        return None, None


def _google_search_http(query):
    """HTTP scraping Google vyhľadávania."""
    url = f"https://www.google.com/search?q={quote_plus(query)}&hl=sk&num=10"

    def _try_search(ua):
        headers = {"User-Agent": ua, "Accept-Language": "sk-SK,sk;q=0.9,en;q=0.8"}
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            return None, f"Google HTTP {r.status_code}"
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for g in soup.select("div.g, div.tF2Cxc, div.MjjYud")[:5]:
            title_el = g.select_one("h3")
            snippet_el = g.select_one("div.VwiC3b, span.aCOpRe, div[data-sncf]")
            link_el = g.select_one("a")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""
            link = link_el.get("href", "") if link_el else ""
            results.append(f"• {title}\n  {link}\n  {snippet}".strip())
        return (results, None) if results else (None, "Google bez výsledkov.")

    r, err = _try_search(_UA)
    if r:
        return r, err
    return _try_search(_UA_FALLBACK)


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────

def web_search(query, save_pages=True):
    """Vyhľadá na internete, uloží výsledky a navštívi stránky.

    1. Browser search cez Operu (primárne)
    2. HTTP scraping fallback (Google)
    3. Uloží výsledky do websearches/<query>/
    4. Navštívi top stránky a stiahne ich HTML
    5. Vráti text výsledkov + info o uložených stránkach

    Args:
        query: Vyhľadávací dotaz
        save_pages: Ak True, stiahne HTML top výsledkov (default True)
    """
    result_urls = []
    saved_pages = []
    combined_text = ""

    # 1. Browser search
    browser_text, raw_text = _search_via_browser(query)
    if browser_text:
        combined_text = browser_text
        result_urls = _extract_urls_from_text(raw_text or browser_text)
    else:
        # 2. HTTP fallback
        print("⚠️ Browser search zlyhal, skúšam HTTP...")
        try:
            http_results, err = _google_search_http(query)
            if http_results:
                combined_text = "[Google]\n" + "\n\n".join(http_results)
                result_urls = _extract_urls_from_http_results(http_results)
            else:
                return f"Vyhľadávanie zlyhalo: {err}"
        except Exception as e:
            return f"Chyba pri vyhľadávaní: {e}"

    # 3. Save to websearches/
    try:
        os.makedirs(WEBSEARCHES_DIR, exist_ok=True)
        search_dir = _save_search(query, combined_text, result_urls, [])
    except Exception as e:
        print(f"⚠️ Uloženie výsledkov zlyhalo: {e}")
        search_dir = None

    # 4. Fetch pages
    if save_pages and result_urls and search_dir:
        print(f"📄 Sťahujem HTML stránky výsledkov...")
        saved_pages = _fetch_pages(result_urls, search_dir, max_pages=3)
        # Update meta with saved pages info
        if saved_pages:
            try:
                meta_path = os.path.join(search_dir, "meta.json")
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                meta["pages_saved"] = len(saved_pages)
                with open(meta_path, "w", encoding="utf-8") as f:
                    json.dump(meta, f, ensure_ascii=False, indent=2)
                # Update index
                index_path = os.path.join(WEBSEARCHES_DIR, "index.json")
                with open(index_path, "r", encoding="utf-8") as f:
                    index = json.load(f)
                slug = _slug(query)
                if slug in index:
                    index[slug]["pages_saved"] = len(saved_pages)
                with open(index_path, "w", encoding="utf-8") as f:
                    json.dump(index, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

    # 5. Build response
    response = combined_text
    if search_dir:
        response += f"\n\n📁 Výsledky uložené v: {search_dir}"
    if saved_pages:
        response += f"\n📄 Stiahnuté stránky ({len(saved_pages)}):"
        for p in saved_pages:
            response += f"\n  {p['index']+1}. {p['title'][:60]} → {os.path.basename(p['file'])}"
        response += "\n\nPre čítanie HTML použi file_manager('read', 'cesta/k/suboru.html')"

    return response


def get_saved_searches():
    """Vráti zoznam všetkých uložených vyhľadávaní."""
    index_path = os.path.join(WEBSEARCHES_DIR, "index.json")
    if not os.path.exists(index_path):
        return "Žiadne uložené vyhľadávania."

    try:
        with open(index_path, "r", encoding="utf-8") as f:
            index = json.load(f)
    except Exception as e:
        return f"Chyba čítania indexu: {e}"

    if not index:
        return "Žiadne uložené vyhľadávania."

    lines = ["📁 Uložené vyhľadávania:", ""]
    for slug, info in sorted(index.items(), key=lambda x: x[1].get("timestamp", ""), reverse=True):
        ts = info.get("timestamp", "?")[:19]
        query = info.get("query", slug)
        urls = info.get("url_count", 0)
        pages = info.get("pages_saved", 0)
        lines.append(f"  • {query}")
        lines.append(f"    📅 {ts} | 🔗 {urls} URL | 📄 {pages} stránok")
        lines.append(f"    📂 websearches/{slug}/")
    return "\n".join(lines)
