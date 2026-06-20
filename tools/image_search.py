"""
Image search via DuckDuckGo API — no browser, no scraping, no pyautogui.
Uses duckduckgo_search library (free, no API key, rate-limited to ~20 req/min).
"""
import os
import re
from ddgs import DDGS


def _describe_image_for_rename(filepath):
    """
    Calls local AI vision (Ollama) to get a 3-5 word description of the image.
    Returns a sanitized string suitable for use as a filename.
    Falls back to 'image_description' if local AI is not available.
    """
    try:
        from tools.local_ai import describe_image

        desc, err = describe_image(
            filepath,
            prompt=(
                "Describe this image in 3-5 words. "
                "Use only lowercase English words separated by underscores. "
                "No punctuation, no articles. "
                "Example: 'smiling_man_in_suit' or 'red_sports_car'. "
                "Reply with ONLY the description, nothing else."
            ),
        )
        if err or not desc:
            return None

        raw = desc.strip()
        sanitized = re.sub(r"[^\w]", "_", raw.lower())
        sanitized = re.sub(r"_+", "_", sanitized).strip("_")
        sanitized = sanitized[:50]

        if len(sanitized) < 3:
            return None
        return sanitized

    except Exception as e:
        print(f"[ImageSearch] _describe_image_for_rename failed: {e}")
        return None
        return sanitized if sanitized else None

    except Exception as e:
        print(f"[ImageSearch] _describe_image_for_rename failed: {e}")
        return None


def image_search(query, count=5):
    """Vyhľadá obrázky cez DuckDuckGo a vráti URL (až 5)."""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.images(query, max_results=count))
        if not results:
            return "Nenašli sa žiadne obrázky."
        urls = [r["image"] for r in results if r.get("image")]
        lines = [f"{i+1}. {url}" for i, url in enumerate(urls)]
        return "Výsledky hľadania obrázkov:\n" + "\n".join(lines)
    except Exception as e:
        return f"Chyba pri hľadaní obrázkov: {e}"


def _default_image_dir():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dldir = os.path.join(base, "web_ui", "uploads", "images")
    os.makedirs(dldir, exist_ok=True)
    return dldir


def search_and_download_image(query, save_path=None, index=0):
    """
    Vyhľadá obrázky cez DuckDuckGo API a stiahne výsledok na disk.
    Ak index=0 (default), stiahne PRVÝ výsledok.
    Ak index>=1, stiahne konkrétny výsledok (1-indexed).
    Po stiahnutí premenuje súbor podľa AI popisu obsahu obrázka.
    """
    from .downloader import download_file

    try:
        print(f"[ImageSearch] Hľadám: {query}")
        with DDGS() as ddgs:
            results = list(ddgs.images(query, max_results=5, type_image="photo"))

        if not results:
            return f"Nenašli sa žiadne obrázky pre: {query}"

        # Vyber výsledok podľa indexu
        idx = max(0, index - 1) if index >= 1 else 0
        if idx >= len(results):
            idx = 0  # fallback na prvý

        chosen = results[idx]
        img_url = chosen.get("image")
        title = chosen.get("title", query)
        if not img_url:
            return f"URL nenájdená pre výsledok č.{idx + 1}."

        # Determine initial save path (temporary name based on title)
        user_provided_path = save_path is not None
        if not save_path:
            safe_name = re.sub(r'[^\w\-_ ]', '_', title)[:50].strip("_ ")
            save_path = os.path.join(_default_image_dir(), f"{safe_name}.jpg")

        result = download_file(img_url, save_path)
        print(f"[ImageSearch] Stiahnuté: {save_path} ({chosen.get('source', '?')})")

        # Attempt AI-based renaming only when we control the path
        if not user_provided_path and os.path.isfile(save_path):
            description = _describe_image_for_rename(save_path)
            if description:
                ext = os.path.splitext(save_path)[1] or ".jpg"
                new_filename = f"{description}{ext}"
                new_path = os.path.join(os.path.dirname(save_path), new_filename)

                # Avoid overwriting an existing file
                if new_path != save_path and os.path.exists(new_path):
                    counter = 1
                    base_new = os.path.splitext(new_path)[0]
                    while os.path.exists(new_path):
                        new_path = f"{base_new}_{counter}{ext}"
                        counter += 1

                if new_path != save_path:
                    os.rename(save_path, new_path)
                    print(f"[ImageSearch] Premenovaný na: {new_path}")
                    # Update result string to reflect new path
                    result = result.replace(save_path, new_path) if isinstance(result, str) else new_path
                    save_path = new_path
            else:
                print("[ImageSearch] AI popis zlyhol, ponechávam pôvodný názov.")

        return result

    except Exception as e:
        return f"Chyba pri sťahovaní obrázka: {e}"


def search_and_list_images(query, max_results=5):
    """
    Vyhľadá obrázky a vráti ZOZNAM s detailmi (pre výber používateľom).
    Vráti formátovaný string s očíslovanými výsledkami.
    """
    try:
        with DDGS() as ddgs:
            results = list(ddgs.images(query, max_results=max_results, type_image="photo"))

        if not results:
            return "Nenašli sa žiadne obrázky."

        lines = [f"📷 Výsledky pre: \"{query}\" — vyber číslo:", ""]
        for i, r in enumerate(results):
            title = r.get("title", "?")[:70]
            source = r.get("source", "?")
            size = f"{r.get('width', '?')}x{r.get('height', '?')}"
            url = r.get("image", "")
            lines.append(f"[{i + 1}] {title}")
            lines.append(f"    URL: {url}")
            lines.append(f"    {source} | {size}")
        return "\n".join(lines)
    except Exception as e:
        return f"Chyba: {e}"