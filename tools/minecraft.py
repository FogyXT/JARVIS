"""
Minecraft RCON tool — pripojenie k lokálnemu Minecraft serveru.

Vyžaduje:
1. V server.properties: enable-rcon=true, rcon.port=25575, rcon.password=<heslo>
2. .env premenné: MC_RCON_PASSWORD=<heslo> (voliteľne MC_RCON_HOST, MC_RCON_PORT)
3. Voliteľne MC_SERVER_DIR=cesta/k/serveru/ pre čítanie logov
"""
import os
import re
import time
import struct
import socket
import threading
from datetime import datetime

# Načítaj .env ak nie je (pre priame volanie python -c)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
except ImportError:
    pass

# ── Konfigurácia z .env ──────────────────────────────────────────────
RCON_HOST = os.environ.get("MC_RCON_HOST", "127.0.0.1")
RCON_PORT = int(os.environ.get("MC_RCON_PORT", "25575"))
RCON_PASSWORD = os.environ.get("MC_RCON_PASSWORD", "")
MC_SERVER_DIR = os.environ.get("MC_SERVER_DIR", "")
_LOG_FILE = os.path.join(MC_SERVER_DIR, "logs", "latest.log") if MC_SERVER_DIR else ""


# ── RCON protokol ────────────────────────────────────────────────────

class RCONClient:
    """Jednoduchý RCON klient pre Minecraft."""

    PACKET_LOGIN = 3
    PACKET_COMMAND = 2

    def __init__(self, host="127.0.0.1", port=25575, password=""):
        self.host = host
        self.port = port
        self.password = password
        self.sock = None
        self.request_id = 1

    def connect(self):
        """Pripojí sa a autentizuje. Vráti True ak ok."""
        if not self.password:
            return False
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(5)
            self.sock.connect((self.host, self.port))

            # Login packet
            self._send_packet(self.PACKET_LOGIN, self.password)
            resp_id, resp_type, resp_data = self._recv_packet()

            if resp_id == -1:
                self.sock.close()
                self.sock = None
                return False
            return True
        except Exception as e:
            self.sock = None
            return False

    def disconnect(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def command(self, cmd):
        """Pošle príkaz na server a vráti odpoveď."""
        if not self.sock:
            return "RCON nie je pripojený."
        try:
            self._send_packet(self.PACKET_COMMAND, cmd)
            resp_id, resp_type, data = self._recv_packet()
            return data.strip()
        except Exception as e:
            self.disconnect()
            return f"Chyba RCON: {e}"

    def _send_packet(self, ptype, payload):
        payload_bytes = payload.encode("utf-8")
        length = 4 + 4 + len(payload_bytes) + 2  # id + type + payload + padding
        packet = struct.pack("<li", length, self.request_id) + struct.pack("<i", ptype) + payload_bytes + b"\x00\x00"
        self.sock.sendall(packet)
        self.request_id += 1

    def _recv_packet(self):
        data = self._recv_exact(4)
        length = struct.unpack("<i", data)[0]
        data = self._recv_exact(length)
        resp_id = struct.unpack("<i", data[:4])[0]
        resp_type = struct.unpack("<i", data[4:8])[0]
        resp_data = data[8:-2].decode("utf-8", errors="replace")
        return resp_id, resp_type, resp_data

    def _recv_exact(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("RCON spojenie stratene")
            buf += chunk
        return buf


# ── Čítanie MC logov ─────────────────────────────────────────────────

def _find_log_file():
    """Nájde latest.log v známych umiestneniach.

    Skúša:
    1. Priamu cestu z MC_SERVER_DIR (rovnaký PC)
    2. UNC cestu \\\\host\\C$\\... (ak je server na inom PC v sieti)
    3. Project root /mc_server/ (lokálna kopija)
    """
    candidates = [_LOG_FILE]

    # UNC fallback: ak cesta zacina C:\ a pozname host, skus \\host\C$\...
    if MC_SERVER_DIR and MC_SERVER_DIR.startswith(("C:", "D:", "E:")) and RCON_HOST not in ("127.0.0.1", "localhost"):
        drive = MC_SERVER_DIR[0]
        rest = MC_SERVER_DIR[2:].replace("\\", "/").lstrip("/")
        unc = f"\\\\{RCON_HOST}\\{drive}${rest}\\logs\\latest.log"
        candidates.append(unc)

    # Projektový fallback
    candidates.append(
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mc_server", "logs", "latest.log")
    )

    for p in candidates:
        if p and os.path.exists(p):
            return p
    return None


def _parse_chat_from_log(line):
    """Extrahuje chat správu z log riadku.
    Príklad: [12:34:56] [Server thread/INFO] [CHAT] <Player> ahoj
    """
    # Vanilla/Paper/Spigot formát
    m = re.search(r"<\s*([^>]+)\s*>\s*(.+)", line)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    # /say formát: [Server: ahoj všetci]
    m = re.search(r"\[Server:\s*(.+)\]", line)
    if m:
        return "Server", m.group(1).strip()
    # Join/quit
    m = re.search(r"(\w+)\s+(joined|left) the game", line)
    if m:
        return None, f"{m.group(1)} {'sa pripojil' if m.group(2) == 'joined' else 'sa odpojil'}"
    return None, None


def _read_recent_log(minutes=5):
    """Prečíta recentné riadky z MC logu a vráti zoznam (timestamp, player, message)."""
    log_path = _find_log_file()
    if not log_path:
        return []

    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception:
        return []

    # Ber posledných N riadkov (približne za X minút)
    max_lines = minutes * 60  # ~1 riadok/sec
    relevant = lines[-max_lines:] if len(lines) > max_lines else lines

    entries = []
    for line in relevant:
        line = line.strip()
        # Skús extrahovať timestamp
        ts_match = re.match(r"\[(\d{2}:\d{2}:\d{2})\]", line)
        timestamp = ts_match.group(1) if ts_match else ""
        # Odstráň timestamp pre parsing
        content = re.sub(r"^\[\d{2}:\d{2}:\d{2}\]\s*\[\w+.*?\]\s*", "", line)
        player, msg = _parse_chat_from_log(content)
        if player or msg:
            entries.append((timestamp, player, msg))

    return entries


# ── Verejné API ───────────────────────────────────────────────────────

def _get_client():
    """Vytvorí a pripojí RCON klienta."""
    if not RCON_PASSWORD:
        return None
    client = RCONClient(RCON_HOST, RCON_PORT, RCON_PASSWORD)
    if client.connect():
        return client
    return None


def minecraft_command(command):
    """Odošle ľubovoľný Minecraft príkaz cez RCON.

    Príklady: 'list', 'say Ahoj všetci', 'tell Fogy Vitaj',
              'weather clear', 'time set day'
    """
    client = _get_client()
    if not client:
        return "❌ RCON nedostupný. Skontroluj MC_RCON_PASSWORD v .env a či je server spustený s enable-rcon=true"
    try:
        result = client.command(command)
        return result if result else "(príkaz vykonaný bez výstupu)"
    finally:
        client.disconnect()


def minecraft_say(message):
    """Odošle správu do Minecraft chatu (ako server)."""
    return minecraft_command(f"say {message}")


def minecraft_tell(player, message):
    """Odošle súkromnú správu hráčovi."""
    return minecraft_command(f"tell {player} {message}")


def minecraft_list_players():
    """Vráti zoznam online hráčov na serveri."""
    result = minecraft_command("list")
    if "❌" in result or "Chyba" in result or "nedostupný" in result:
        return result
    # Parsovanie: "There are 2 of max 20 players online: player1, player2"
    players = []
    m = re.search(r"players online:\s*(.*)", result)
    if m:
        raw = m.group(1).strip()
        if raw:
            players = [p.strip() for p in raw.split(",")]
    if not players:
        return "Na serveri nie sú žiadni hráči."
    return f"👥 Online hráči ({len(players)}): {', '.join(players)}"


def minecraft_recent_chat(minutes=5):
    """Prečíta recentné správy z Minecraft logu.

    Args:
        minutes: koľko minút dozadu (default 5)
    Returns:
        formátovaný string správ
    """
    entries = _read_recent_log(minutes)
    if not entries:
        log_path = _find_log_file()
        if log_path:
            return f"Log nájdený ale žiadne chat správy za posledných {minutes} min."
        return "❌ Minecraft log nenájdený. Nastav MC_SERVER_DIR=cesta/k/serveru/ v .env"

    lines = [f"💬 Správy z Minecraftu (posledných {minutes} min):"]
    for ts, player, msg in entries[-20:]:  # max 20 správ
        if player:
            lines.append(f"  [{ts}] <{player}> {msg}")
        else:
            lines.append(f"  [{ts}] {msg}")
    return "\n".join(lines)


def minecraft_wait_for_player(player_name, timeout=300):
    """Počká kým sa hráč pripojí a pošle mu správu.

    Použitie (z AI): najprv zavoláš minecraft_wait_for_player("Fogy", 120)
    a ak sa pripojí, odošle mu správu.

    POZNÁMKA: Toto je blokujúce volanie. timeout v sekundách.
    """
    client = _get_client()
    if not client:
        return "❌ RCON nedostupný."
    try:
        start = time.time()
        while time.time() - start < timeout:
            result = client.command("list")
            if player_name.lower() in result.lower():
                return f"✅ Hráč {player_name} je online! Môžeš mu poslať správu cez minecraft_tell."
            time.sleep(3)
        return f"⏱ Hráč {player_name} sa nepripojil do {timeout}s."
    finally:
        client.disconnect()


def minecraft_check_ai_questions(password="12345"):
    """Skontroluje Minecraft chat na otázky pre AI s heslom.

    Hráči píšu: !ai <heslo> <otázka>
    Napr: !ai 12345 aký je dnes dátum?

    Ak sa heslo zhoduje, vráti otázky. Ak nie, ignoruje ich.
    Toto slúži ako ochrana — bez správneho hesla AI neodpovedá.
    """
    entries = _read_recent_log(minutes=10)
    if not entries:
        return None

    questions = []
    for ts, player, msg in entries:
        if not player or not msg:
            continue
        # Hľadáme !ai <password> <otázka>
        m = re.match(r"!ai\s+(\S+)\s+(.+)", msg, re.I)
        if m:
            provided_pw = m.group(1)
            question = m.group(2).strip()
            if provided_pw == password:
                questions.append((ts, player, question))
            # Ak je zlé heslo, ignorujeme — neprezrádzame prečo

    if not questions:
        return None

    lines = ["🎮 Otázky z Minecraftu (overené heslom):"]
    for ts, player, q in questions[-10:]:
        lines.append(f"  [{ts}] <{player}> {q}")
    lines.append("\nOdpovedať môžeš cez minecraft_tell(player, odpoved) alebo minecraft_say(odpoved)")
    return "\n".join(lines)
