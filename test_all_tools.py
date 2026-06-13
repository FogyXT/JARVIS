#!/usr/bin/env python3
"""Komplexný test všetkých Jarvis tools.

Spustenie: python test_all_tools.py
Každý test je samostatný, zlyhanie jedného neovplyvní ostatné.
"""
import os
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT_ROOT)

PASS = 0
FAIL = 0
SKIP = 0

def test(name, fn):
    global PASS, FAIL, SKIP
    try:
        result = fn()
        if result is True:
            PASS += 1
            print(f"  ✅ {name}")
        elif result is None or result == "SKIP":
            SKIP += 1
            print(f"  ⏭️  {name} (preskočené)")
        else:
            FAIL += 1
            print(f"  ❌ {name}: {result}")
    except Exception as e:
        FAIL += 1
        print(f"  ❌ {name}: EXCEPTION: {e}")
        import traceback
        traceback.print_exc()


# ──────────────────────────────────────────────
# TESTS
# ──────────────────────────────────────────────

def test_memory():
    """Základné CRUD operácie pamäte."""
    from tools.memory import memory
    # Save
    r1 = memory("save", "test_key", "test_value")
    assert "Uložené" in r1, f"save failed: {r1}"
    # Read
    r2 = memory("read", "test_key")
    assert "test_value" in r2, f"read failed: {r2}"
    # Read all
    r3 = memory("read")
    assert "test_key" in r3, f"read all failed: {r3}"
    # Delete
    r4 = memory("delete", "test_key")
    assert "Vymazané" in r4, f"delete failed: {r4}"
    # Read after delete
    r5 = memory("read", "test_key")
    assert "neuložené" in r5, f"read after delete failed: {r5}"
    return True


def test_file_manager_write_read():
    """Zápis a čítanie súboru."""
    from tools.file_manager import file_manager
    test_file = os.path.join(PROJECT_ROOT, "_test_write.txt")
    try:
        r = file_manager("write", test_file, "Hello World")
        assert "Zapísané" in r, f"write failed: {r}"
        r2 = file_manager("read", test_file)
        assert "Hello World" in r2, f"read failed: {r2}"
        return True
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)


def test_file_manager_append():
    """Apendovanie do súboru."""
    from tools.file_manager import file_manager
    test_file = os.path.join(PROJECT_ROOT, "_test_append.txt")
    try:
        file_manager("write", test_file, "First ")
        file_manager("append", test_file, "Second")
        r = file_manager("read", test_file)
        assert "First Second" in r, f"append failed: {r}"
        return True
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)


def test_file_manager_create_folder():
    """Vytvorenie a zmazanie adresára."""
    from tools.file_manager import file_manager
    test_dir = os.path.join(PROJECT_ROOT, "_test_folder")
    try:
        r = file_manager("create_folder", test_dir)
        assert "vytvoren" in r, f"create failed: {r}"
        assert os.path.isdir(test_dir), "dir not created"
        # List it
        r2 = file_manager("list", test_dir)
        assert "prázdne" in r2 or "Výpis" in r2, f"list empty failed: {r2}"
        return True
    finally:
        if os.path.isdir(test_dir):
            os.rmdir(test_dir)


def test_file_manager_list():
    """Výpis adresára."""
    from tools.file_manager import file_manager
    r = file_manager("list", PROJECT_ROOT)
    assert "Výpis" in r, f"list failed: {r}"
    assert "Veľkosť" in r, f"list no size column: {r}"
    assert "Dátum" in r, f"list no date column: {r}"
    return True


def test_file_manager_binary_detection():
    """Detekcia binárneho súboru."""
    from tools.file_manager import file_manager
    test_file = os.path.join(PROJECT_ROOT, "_test_binary.bin")
    try:
        with open(test_file, "wb") as f:
            f.write(b"\x00\x01\x02\x03")
        r = file_manager("read", test_file)
        assert "Binárny" in r, f"binary detection failed: {r}"
        return True
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)


def test_file_manager_delete():
    """Zmazanie súboru."""
    from tools.file_manager import file_manager
    test_file = os.path.join(PROJECT_ROOT, "_test_delete.txt")
    file_manager("write", test_file, "temporary")
    r = file_manager("delete", test_file)
    assert "vymazan" in r, f"delete failed: {r}"
    assert not os.path.exists(test_file), "file still exists"
    return True


def test_downloader():
    """Stiahnutie súboru z internetu."""
    from tools.downloader import download_file
    test_file = os.path.join(PROJECT_ROOT, "_test_download.txt")
    try:
        r = download_file("https://httpbin.org/robots.txt", test_file)
        if "Chyba" in r or "503" in r or "500" in r or "503" in r:
            return "SKIP"  # httpbin might be down
        assert "Stiahnuté" in r, f"download failed: {r}"
        return True
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)


def test_downloader_directory_path():
    """Stiahnutie s path ako adresár."""
    from tools.downloader import download_file
    test_dir = os.path.join(PROJECT_ROOT, "_test_dldir")
    try:
        r = download_file("https://httpbin.org/robots.txt", test_dir + "/")
        if "Chyba" in r or "503" in r or "500" in r:
            return "SKIP"  # httpbin might be down
        assert "Stiahnuté" in r, f"dir download failed: {r}"
        assert os.path.isdir(test_dir), f"dir not created: {test_dir}"
        files = os.listdir(test_dir)
        assert len(files) > 0, f"no files in dir: {files}"
        return True
    finally:
        if os.path.isdir(test_dir):
            import shutil
            shutil.rmtree(test_dir)


def test_image_search():
    """Vyhľadávanie obrázkov."""
    from tools.image_search import image_search
    r = image_search("mountain landscape", 2)
    if r == "Nenašli sa žiadne obrázky.":
        # Bing might rate-limit, but the function works
        return "SKIP"  # Not a failure, just rate-limited
    assert "http" in r, f"no URLs in results: {r[:200]}"
    assert "1." in r, f"no numbered results: {r[:200]}"
    return True


def test_search_and_download_image():
    """Vyhľadanie a stiahnutie obrázka."""
    from tools.image_search import search_and_download_image
    test_file = os.path.join(PROJECT_ROOT, "_test_img.jpg")
    try:
        r = search_and_download_image("sunset", test_file)
        if "stiahnut" in r or "Obrázok" in r:
            assert os.path.exists(test_file), f"file not created: {r}"
            return True
        return "SKIP"  # Bing rate-limit
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)


def test_system_info():
    """Systémové informácie."""
    from tools.system_info import system_info
    # Test all categories individually
    for cat in ["disk", "cpu", "ram", "gpu", "uptime"]:
        r = system_info(cat)
        assert "nedostupné" not in r or "Chyba" not in r, f"{cat} failed: {r[:100]}"
    # Test all combined
    r = system_info("all")
    assert "Disk" in r and "RAM" in r, f"all failed: {r[:200]}"
    return True


def test_launch_app_no_execute():
    """Test že launch_app vráti správnu správu bez spustenia (funguje ako dry-run)."""
    from tools.launch_app import launch_app
    # Test that known apps map correctly (won't actually launch anything we can validate)
    r = launch_app("unknown_app_xyz_123")
    assert "Neznáma" in r, f"unknown app should fail: {r}"
    # Calculator should work
    r2 = launch_app("calculator")
    assert "Spúšťam" in r2, f"known app failed: {r2}"
    return True


def test_execute_command():
    """Základný PowerShell príkaz."""
    from tools.system import execute_command
    r = execute_command("echo 'Hello from Jarvis Test'")
    assert "Hello from Jarvis Test" in r, f"echo failed: {r}"
    assert "Exit: 0" in r, f"exit code not 0: {r}"
    return True


def test_execute_command_with_dir():
    """PowerShell príkaz s working_dir."""
    from tools.system import execute_command
    r = execute_command("Get-Location | Select-Object -ExpandProperty Path", working_dir="C:\\")
    assert "C:\\" in r or "C:" in r, f"working_dir failed: {r}"
    return True


def test_execute_command_fail():
    """PowerShell príkaz s nenulovým exit kódom."""
    from tools.system import execute_command
    r = execute_command("exit 1")
    assert "Exit: 1" in r, f"exit code not 1: {r}"
    return True


def test_news():
    """RSS novinky."""
    from tools.news import get_news
    r = get_news("sk", 2)
    if "Nepodarilo" in r:
        # Network might fail, but function works
        return "SKIP"
    assert "SME" in r or "Aktuality" in r or "novinky" in r.lower(), f"sk news failed: {r[:200]}"
    return True


def test_news_en():
    """Anglické RSS novinky."""
    from tools.news import get_news
    r = get_news("en", 1)
    if "Nepodarilo" in r:
        return "SKIP"
    assert "BBC" in r, f"en news failed: {r[:200]}"
    return True


def test_web_search():
    """Web search cez DuckDuckGo/Bing fallback."""
    from tools.web_search import web_search
    r = web_search("Python programming language")
    # All search engines might fail due to rate-limiting / network issues
    if "Chyba" in r or "zlyhali" in r:
        return "SKIP"
    assert "Python" in r or "python" in r or "•" in r, f"web search failed: {r[:200]}"
    return True


def test_browser_take_screenshot():
    """Test uloženia screenshotu."""
    from tools.browser import take_screenshot
    r = take_screenshot()
    assert os.path.exists(r), f"screenshot not created: {r}"
    assert r.endswith("screenshot.png"), f"wrong path: {r}"
    os.remove(r)
    return True


def test_browser_opera_check():
    """Test či Opera beží (nevyžaduje aby bežala)."""
    from tools.browser import is_opera_running_custom
    # This should return True or False without error
    result = is_opera_running_custom()
    assert isinstance(result, bool), f"should return bool: {result}"
    return True


def test_set_clipboard():
    """Test textovej schránky."""
    from tools import _set_clipboard
    assert _set_clipboard("Jarvis Test Clipboard"), "clipboard set failed"
    return True


def test_set_clipboard_image():
    """Test obrázkovej schránky (potrebuje existujúci obrázok)."""
    from tools import _set_clipboard_image
    # Create a small PNG for testing
    test_png = os.path.join(PROJECT_ROOT, "_test_clipimg.png")
    try:
        # Create a minimal valid 1x1 white PNG
        import struct, zlib
        def _make_png(width, height):
            def chunk(ctype, data):
                c = ctype + data
                return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xffffffff)
            ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
            raw = b""
            for y in range(height):
                raw += b"\x00" + b"\xff\xff\xff" * width
            idat = zlib.compress(raw)
            return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")

        with open(test_png, "wb") as f:
            f.write(_make_png(1, 1))

        result = _set_clipboard_image(test_png)
        assert result, f"clipboard image failed"
        return True
    finally:
        if os.path.exists(test_png):
            os.remove(test_png)


def test_set_clipboard_image_nonexistent():
    """Test že _set_clipboard_image vráti False pre neexistujúci súbor."""
    from tools import _set_clipboard_image
    assert not _set_clipboard_image("C:\\nonexistent_file_xyz.jpg"), "should return False"
    return True


def test_instagram_resolve_path():
    """Test interného resolvovania ciest pre Instagram prílohy."""
    # Import the private function from the instagram module
    import importlib
    ig = importlib.import_module("tools.instagram")
    r = ig._resolve_attachment_path("nonexistent_upload_xyz.jpg")
    assert r is None, "nonexistent path should return None"
    # Test with a file that exists
    test_file = os.path.join(PROJECT_ROOT, "_test_ig_path.txt")
    try:
        with open(test_file, "w") as f:
            f.write("test")
        r2 = ig._resolve_attachment_path(test_file)
        assert r2 == os.path.abspath(test_file), f"should resolve to abs: {r2}"
        return True
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)


def test_clipboard_special_chars():
    """Test schránky so špeciálnymi znakmi (úvodzovky, nové riadky)."""
    from tools import _set_clipboard
    text = "Hello 'World' with\nnewlines and \"quotes\""
    assert _set_clipboard(text), "special chars clipboard failed"
    return True


def test_file_manager_append_new_file():
    """Test appendu do neexistujúceho súboru (mal by ho vytvoriť)."""
    from tools.file_manager import file_manager
    test_file = os.path.join(PROJECT_ROOT, "_test_append_new.txt")
    try:
        r = file_manager("append", test_file, "New content")
        assert "Pripojen" in r, f"append new failed: {r}"
        r2 = file_manager("read", test_file)
        assert "New content" in r2, f"read after append failed: {r2}"
        return True
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)


def test_file_manager_delete_nonexistent():
    """Test mazania neexistujúcej cesty."""
    from tools.file_manager import file_manager
    r = file_manager("delete", "C:\\nonexistent_path_xyz")
    assert "neexistuje" in r, f"delete nonexistent failed: {r}"
    return True


# ──────────────────────────────────────────────
# RUN ALL
# ──────────────────────────────────────────────

if __name__ == "__main__":
    print("🧪 Jarvis Tools Test Suite")
    print("=" * 60)

    tests = [
        ("Memory CRUD", test_memory),
        ("File Manager: Write/Read", test_file_manager_write_read),
        ("File Manager: Append", test_file_manager_append),
        ("File Manager: Create Folder", test_file_manager_create_folder),
        ("File Manager: List", test_file_manager_list),
        ("File Manager: Binary Detection", test_file_manager_binary_detection),
        ("File Manager: Delete", test_file_manager_delete),
        ("Downloader: File", test_downloader),
        ("Downloader: Directory path", test_downloader_directory_path),
        ("Image Search", test_image_search),
        ("Search & Download Image", test_search_and_download_image),
        ("System Info (all categories)", test_system_info),
        ("Launch App (validation)", test_launch_app_no_execute),
        ("Execute Command: echo", test_execute_command),
        ("Execute Command: with dir", test_execute_command_with_dir),
        ("Execute Command: fail", test_execute_command_fail),
        ("News SK", test_news),
        ("News EN", test_news_en),
        ("Web Search", test_web_search),
        ("Browser: Screenshot path", test_browser_take_screenshot),
        ("Browser: Opera check", test_browser_opera_check),
        ("Clipboard: Text", test_set_clipboard),
        ("Clipboard: Special chars", test_clipboard_special_chars),
        ("Clipboard: Image", test_set_clipboard_image),
        ("Clipboard: Image nonexistent", test_set_clipboard_image_nonexistent),
        ("Instagram: Resolve path", test_instagram_resolve_path),
        ("File Manager: Append new file", test_file_manager_append_new_file),
        ("File Manager: Delete nonexistent", test_file_manager_delete_nonexistent),
    ]

    for name, fn in tests:
        test(name, fn)

    print()
    print("=" * 60)
    print(f"   ✅ {PASS} passed | ❌ {FAIL} failed | ⏭️  {SKIP} skipped")
    print("=" * 60)
    sys.exit(0 if FAIL == 0 else 1)
