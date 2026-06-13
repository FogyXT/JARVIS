import xml.etree.ElementTree as ET
import requests
import datetime

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

FEEDS = {
    "sk": [
        ("SME", "https://www.sme.sk/rss/"),
        ("Aktuality", "https://www.aktuality.sk/rss/"),
    ],
    "en": [
        ("BBC World", "https://feeds.bbci.co.uk/news/rss.xml"),
        ("Reuters", "https://www.rss-bridge.org/bridge01/?action=display&bridge=FilterBridge&url=https%3A%2F%2Fwww.reuters.com&content_filter=&content_filter_type=text&title_filter=&title_filter_type=text&inverse=on&case_insensitive=on&fix_encoding=on&format=Rss"),
    ],
}


def _parse_rss(url, max_items=5):
    """Stiahne a parsuje RSS feed. Vráti zoznam (title, link)."""
    try:
        r = requests.get(url, headers={"User-Agent": _UA}, timeout=10)
        r.raise_for_status()
        root = ET.fromstring(r.content)

        items = []
        # RSS 2.0: rss/channel/item
        for item in root.findall(".//item")[:max_items]:
            title = item.findtext("title", "")
            link = item.findtext("link", "")
            if title:
                items.append((title.strip(), link.strip()))
        return items
    except Exception as e:
        return []


def get_news(language="sk", count=5):
    """Získa aktuálne novinky z RSS feedov.

    language: 'sk' (SME, Aktuality) alebo 'en' (BBC, Reuters)
    count: počet správ na feed (default 5)
    """
    feeds = FEEDS.get(language, FEEDS["sk"])
    results = []

    for source_name, feed_url in feeds:
        items = _parse_rss(feed_url, count)
        if items:
            results.append(f"\n📰 {source_name}:")
            for i, (title, link) in enumerate(items, 1):
                results.append(f"  {i}. {title}")
                results.append(f"     {link}")

    if not results:
        return "Nepodarilo sa načítať novinky."

    return "Aktuálne novinky:" + "\n".join(results)
