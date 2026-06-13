"""
Cold Archive — dlhodobé komprimované úložisko spomienok (Tier 5).

Najpomalšia, najlacnejšia, najväčšia vrstva pamäte.
Pre spomienky ktoré sú staré, zriedka používané, ale stále hodnotné.

Funkcie:
- archive(items)    — ulož spomienky do filesystemu (JSON, organizované podľa YYYY/MM)
- thaw(key/query)   — obnov spomienku z archívu späť do aktívnej pamäte
- list(year, month) — vypíš archivované spomienky
- search(query)     — full-text search v archíve (brute-force, lebo je to zriedkavé)
- compact()         — zlúč veľmi staré spomienky do sumárov
- stats()           — štatistiky archívu

Integrácia:
- consolidation._stage_archive() používa ColdArchive namiesto raw JSON write
- Automaticky pri consolidate_full() ak sú spomienky staršie ako 90 dní

Path: D:/JARVIS/archive/memories/YYYY/MM/archive_YYYYMMDD_HHMMSS.json
"""

import os
import json
import time
import glob
from typing import Optional, Any

from tools.jarvis_logging import log


# ── Config ────────────────────────────────────────────────────────────────

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCHIVE_DIR = os.path.join(PROJECT_ROOT, "archive", "memories")

# Age thresholds
ARCHIVE_AGE = 90 * 24 * 3600       # 90 days — candidate for archiving
COMPACT_AGE = 365 * 24 * 3600      # 365 days — compact into summaries

# Max search results from archive (brute-force, keep low)
MAX_ARCHIVE_SEARCH = 20


# ── Cold Archive ──────────────────────────────────────────────────────────

class ColdArchive:
    """Dlhodobé filesystemové úložisko spomienok."""

    def __init__(self, base_dir: str = ARCHIVE_DIR):
        self.base_dir = base_dir
        self._index: dict[str, dict] = {}  # key → {file, index_in_file, ...}
        self._index_loaded = False

    # ── Internal ───────────────────────────────────────────────────────

    def _month_dir(self, timestamp: float = None) -> str:
        """Vráť cestu k adresáru pre daný mesiac."""
        ts = timestamp or time.time()
        month_str = time.strftime("%Y-%m", time.gmtime(ts))
        return os.path.join(self.base_dir, month_str)

    def _ensure_dir(self, path: str):
        os.makedirs(path, exist_ok=True)

    def _load_index(self):
        """Lenivé načítanie indexu — prehľadá všetky archívne súbory."""
        if self._index_loaded:
            return
        self._index = {}
        if not os.path.isdir(self.base_dir):
            self._index_loaded = True
            return

        for fpath in glob.glob(os.path.join(self.base_dir, "**", "*.json"), recursive=True):
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    for i, item in enumerate(data):
                        key = item.get("key", "")
                        if key:
                            self._index[key] = {"file": fpath, "index": i, "item": item}
                elif isinstance(data, dict) and data.get("type") == "compact":
                    # Compacted summary
                    key = data.get("summary_key", "")
                    if key:
                        self._index[key] = {"file": fpath, "index": 0, "item": data}
            except Exception as e:
                log.debug(f"Archive index skip {fpath}: {e}", module="archive")

        self._index_loaded = True
        log.debug(f"Archive index: {len(self._index)} keys from disk", module="archive")

    # ── Archive ────────────────────────────────────────────────────────

    def archive(self, items: list[dict]) -> int:
        """Ulož spomienky do archívu. Vráti počet archivovaných.

        Args:
            items: [{"key": ..., "value": ..., "timestamp": ..., ...}, ...]
        """
        if not items:
            return 0

        self._ensure_dir(self.base_dir)
        month_dir = self._month_dir(items[0].get("timestamp", time.time()))
        self._ensure_dir(month_dir)

        fname = f"archive_{time.strftime('%Y%m%d_%H%M%S')}.json"
        fpath = os.path.join(month_dir, fname)

        archive_data = []
        for item in items:
            archive_data.append({
                "key": item.get("key", "unknown"),
                "value": item.get("value", ""),
                "timestamp": item.get("timestamp", time.time()),
                "last_access": item.get("last_access", time.time()),
                "access_count": item.get("access_count", 0),
                "importance": item.get("importance", 0.5),
                "current_score": item.get("current_score", 0),
                "tags": item.get("tags", []),
                "archived_at": time.time(),
            })
            # Update index
            key = item.get("key", "")
            if key:
                self._index[key] = {"file": fpath, "index": len(archive_data) - 1,
                                    "item": archive_data[-1]}

        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(archive_data, f, ensure_ascii=False, indent=2)

        log.info(f"Archived {len(items)} memories → {fpath}", module="archive")
        return len(items)

    # ── Thaw ───────────────────────────────────────────────────────────

    def thaw(self, key: str = None, query: str = None, max_items: int = 5) -> list[dict]:
        """Obnov spomienky z archívu späť do aktívnej pamäte.

        Args:
            key: Presný kľúč
            query: Full-text vyhľadávanie v archivovaných hodnotách
            max_items: Max počet na obnovenie

        Returns:
            List[dict] — spomienky pripravené na re-store
        """
        self._load_index()

        thawed = []

        if key:
            entry = self._index.get(key)
            if entry:
                thawed.append(entry["item"])

        elif query:
            query_lower = query.lower()
            for key, entry in self._index.items():
                item = entry["item"]
                text = f"{key}: {item.get('value', '')}".lower()
                if query_lower in text:
                    thawed.append(item)
                if len(thawed) >= max_items:
                    break

        # Re-store thawed items do aktívnej pamäte
        restored = 0
        for item in thawed:
            try:
                from tools.memory import memory
                memory("save", item["key"], item["value"])
                restored += 1
                log.info(f"Thawed: {item['key']}", module="archive")
            except Exception as e:
                log.warn(f"Thaw failed for {item['key']}: {e}", module="archive")

        return thawed

    # ── List ───────────────────────────────────────────────────────────

    def list_archived(self, year: int = None, month: int = None) -> list[dict]:
        """Vypíš archivované spomienky, voliteľne filtrované podľa roku/mesiaca."""
        self._load_index()

        results = []
        for key, entry in self._index.items():
            item = entry["item"]
            ts = item.get("timestamp", 0)
            if ts:
                t = time.gmtime(ts)
                if year and t.tm_year != year:
                    continue
                if month and t.tm_mon != month:
                    continue
            results.append({
                "key": key,
                "value": item.get("value", "")[:100],
                "timestamp": ts,
                "file": entry["file"],
            })

        results.sort(key=lambda x: x["timestamp"], reverse=True)
        return results

    # ── Search ─────────────────────────────────────────────────────────

    def search(self, query: str, max_results: int = MAX_ARCHIVE_SEARCH) -> list[dict]:
        """Full-text vyhľadávanie v archíve (brute-force cez index)."""
        self._load_index()

        query_lower = query.lower()
        results = []

        for key, entry in self._index.items():
            item = entry["item"]
            text = f"{key}: {item.get('value', '')}".lower()
            if query_lower in text:
                results.append({
                    "key": key,
                    "value": item.get("value", "")[:200],
                    "timestamp": item.get("timestamp", 0),
                    "importance": item.get("importance", 0),
                    "file": entry["file"],
                })
                if len(results) >= max_results:
                    break

        return results

    # ── Compact ────────────────────────────────────────────────────────

    def compact(self) -> dict:
        """Zlúč veľmi staré (>1 rok) spomienky do sumárov.

        Pre každý mesiac vytvorí jeden compact.json s kľúčovými info.
        """
        self._load_index()

        now = time.time()
        compacted = 0

        # Group old items by month
        old_by_month: dict[str, list] = {}
        for key, entry in self._index.items():
            item = entry["item"]
            age = now - item.get("timestamp", 0)
            if age > COMPACT_AGE:
                ts = item.get("timestamp", now)
                month_str = time.strftime("%Y-%m", time.gmtime(ts))
                if month_str not in old_by_month:
                    old_by_month[month_str] = []
                old_by_month[month_str].append(item)

        for month_str, items in old_by_month.items():
            if len(items) < 2:
                continue

            month_dir = os.path.join(self.base_dir, month_str)
            self._ensure_dir(month_dir)

            # Create summary
            summary = {
                "type": "compact",
                "summary_key": f"archive_summary_{month_str}",
                "month": month_str,
                "total_items": len(items),
                "compacted_at": time.time(),
                "key_points": [],
                "oldest": min(i.get("timestamp", 0) for i in items),
                "newest": max(i.get("timestamp", 0) for i in items),
            }

            # Extract key points (najdôležitejšie spomienky)
            items_sorted = sorted(items, key=lambda x: x.get("importance", 0), reverse=True)
            for item in items_sorted[:10]:
                summary["key_points"].append({
                    "key": item.get("key", ""),
                    "value": item.get("value", "")[:150],
                    "importance": item.get("importance", 0),
                })

            fpath = os.path.join(month_dir, f"compact_{month_str}.json")
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)

            self._index[summary["summary_key"]] = {"file": fpath, "index": 0, "item": summary}
            compacted += len(items)

            log.info(f"Compacted {len(items)} items → {fpath}", module="archive")

        return {"compacted_items": compacted, "months": len(old_by_month)}

    # ── Stats ──────────────────────────────────────────────────────────

    def stats(self) -> dict:
        """Štatistiky archívu."""
        self._load_index()

        total_size = 0
        file_count = 0
        years = set()
        months = set()

        if os.path.isdir(self.base_dir):
            for fpath in glob.glob(os.path.join(self.base_dir, "**", "*.json"), recursive=True):
                file_count += 1
                try:
                    total_size += os.path.getsize(fpath)
                except OSError:
                    pass

        # Extract years/months from paths
        for fpath in glob.glob(os.path.join(self.base_dir, "*"), recursive=False):
            if os.path.isdir(fpath):
                parts = os.path.basename(fpath).split("-")
                if len(parts) == 2:
                    years.add(parts[0])
                    months.add(f"{parts[0]}-{parts[1]}")

        return {
            "total_keys": len(self._index),
            "total_files": file_count,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "years": sorted(years),
            "months": len(months),
            "base_dir": self.base_dir,
        }


# ── Singleton ─────────────────────────────────────────────────────────────

_archive: Optional[ColdArchive] = None


def get_archive() -> ColdArchive:
    """Získaj singleton ColdArchive."""
    global _archive
    if _archive is None:
        _archive = ColdArchive()
    return _archive


# ── Quick Self-Test ───────────────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile

    print("=== COLD ARCHIVE SELF-TEST ===\n")

    with tempfile.TemporaryDirectory() as tmpdir:
        ca = ColdArchive(base_dir=tmpdir)

        # Archive
        items = [
            {"key": "old_memory_1", "value": "This is an old Python memory",
             "timestamp": time.time() - 400*24*3600, "importance": 0.3, "tags": ["tech"]},
            {"key": "old_memory_2", "value": "Fogy used to like green before blue",
             "timestamp": time.time() - 200*24*3600, "importance": 0.2, "tags": ["personal"]},
        ]
        n = ca.archive(items)
        print(f"Archived: {n} items")

        # Stats
        s = ca.stats()
        print(f"Stats: {s}")

        # Search
        results = ca.search("Python")
        print(f"Search 'Python': {len(results)} results")
        for r in results:
            print(f"  - {r['key']}: {r['value'][:60]}")

        # List
        all_items = ca.list_archived()
        print(f"List all: {len(all_items)} items")

        # Thaw
        thawed = ca.thaw(key="old_memory_1")
        print(f"Thawed: {len(thawed)} items")

        # Compact
        compact_result = ca.compact()
        print(f"Compact: {compact_result}")

    print("\n=== SELF-TEST COMPLETE ===")
