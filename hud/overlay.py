"""
JARVIS HUD — System Tray + Overlay (Iron Man štýl).
Jednoduchý, animovaný, jednotný dizajn bez viditeľných predelov.
"""

import sys
import json
import os
import time
import threading
import subprocess
from datetime import datetime

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
_JARVIS_PATH = os.path.join(_PROJECT_ROOT, "jarvis.py")
_WEBUI_PATH = os.path.join(_PROJECT_ROOT, "run_webui.py")
_SESSIONS_DIR = os.path.join(_PROJECT_ROOT, "web_ui", "sessions")

from PySide6.QtWidgets import (QApplication, QWidget, QLabel, QMenu, QPushButton,
                                QSystemTrayIcon, QVBoxLayout, QHBoxLayout, QScrollArea, QFrame)
from PySide6.QtCore import Qt, QTimer, QThread, Signal, Property, QEasingCurve, QPropertyAnimation
from PySide6.QtGui import QFont, QPainter, QPainterPath, QBrush, QColor, QPen, QRadialGradient


# ── Colors ──────────────────────────────────────────────────────────────
CYAN     = "#00D4FF"
CYAN_DIM = "#0088AA"
WHITE    = "#F0F4F8"
GRAY     = "rgba(180,195,210,0.55)"
BG       = QColor(0, 10, 22, 215)
BORDER   = QColor(0, 180, 240, 70)

# ── Helpers ─────────────────────────────────────────────────────────────

def get_system_info():
    try:
        import psutil
        return psutil.cpu_percent(interval=0.1), psutil.virtual_memory().percent, datetime.now().strftime("%H:%M")
    except ImportError:
        return 0, 0, datetime.now().strftime("%H:%M")

def _load_recent_sessions(limit=8):
    if not os.path.isdir(_SESSIONS_DIR):
        return []
    files = [f for f in os.listdir(_SESSIONS_DIR) if f.endswith(".json")]
    files.sort(key=lambda f: os.path.getmtime(os.path.join(_SESSIONS_DIR, f)), reverse=True)
    return [{"id": f[:-5], "modified": datetime.fromtimestamp(
        os.path.getmtime(os.path.join(_SESSIONS_DIR, f))).strftime("%m/%d %H:%M")} for f in files[:limit]]


# ── Pulsing dot (inline reactor) ────────────────────────────────────────

class PulseDot(QWidget):
    """Malý pulzujúci cyan kruh — jadro HUD."""

    def __init__(self, size=28):
        super().__init__()
        self.setFixedSize(size, size)
        self._pulse = 1.0
        self._anim = None

    def start_pulse(self, speed="normal"):
        speeds = {"slow": 2200, "normal": 1200, "fast": 600}
        dur = speeds.get(speed, 1200)
        if self._anim:
            self._anim.stop()
        self._anim = QPropertyAnimation(self, b"pulse")
        self._anim.setDuration(dur)
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(2.0)
        self._anim.setEasingCurve(QEasingCurve.InOutSine)
        self._anim.setLoopCount(-1)
        self._anim.start()

    def stop_pulse(self):
        if self._anim:
            self._anim.stop()
            self._anim = None
        self._pulse = 1.0
        self.update()

    def get_pulse(self): return self._pulse

    def set_pulse(self, v):
        self._pulse = v
        self.update()

    pulse = Property(float, get_pulse, set_pulse)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = self.rect().center()
        r = (min(self.width(), self.height()) / 2 - 2) * self._pulse

        # Outer glow
        g = QRadialGradient(c, r * 3)
        g.setColorAt(0, QColor(0, 212, 255, 70))
        g.setColorAt(0.5, QColor(0, 160, 220, 15))
        g.setColorAt(1, QColor(0, 0, 0, 0))
        p.setBrush(QBrush(g))
        p.setPen(Qt.NoPen)
        p.drawEllipse(c, r * 3, r * 3)

        # Core
        g2 = QRadialGradient(c, r)
        g2.setColorAt(0, QColor(120, 240, 255, 220))
        g2.setColorAt(0.6, QColor(0, 200, 240, 120))
        g2.setColorAt(1, QColor(0, 140, 200, 30))
        p.setBrush(QBrush(g2))
        p.drawEllipse(c, r, r)

        # Inner bright
        g3 = QRadialGradient(c, r * 0.3)
        g3.setColorAt(0, QColor(220, 248, 255, 240))
        g3.setColorAt(1, QColor(0, 200, 255, 0))
        p.setBrush(QBrush(g3))
        p.drawEllipse(c, r * 0.3, r * 0.3)

        # Ring
        pen = QPen(QColor(CYAN), 1.2)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(c, r, r)
        p.end()


# ── Subprocess mgr ──────────────────────────────────────────────────────

class ProcMgr(QThread):
    status = Signal(str)

    def __init__(self):
        super().__init__()
        self.proc = None
        self._keep = []  # udržuje referenciu na subprocess

    def run(self):
        try:
            self.proc = subprocess.Popen(
                [sys.executable, _JARVIS_PATH], cwd=_PROJECT_ROOT,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
            self._keep.append(self.proc)
            self.status.emit("running")
            self.proc.wait()
            self.status.emit("stopped")
        except Exception as e:
            self.status.emit(f"error: {e}")

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            time.sleep(0.4)
            if self.proc.poll() is None:
                self.proc.kill()

    @property
    def ok(self):
        return self.proc is not None and self.proc.poll() is None


# ── WebSocket ───────────────────────────────────────────────────────────

class WSClient(QThread):
    msg = Signal(dict)

    def __init__(self, port=9876):
        super().__init__()
        self.port = port
        self._on = True

    def run(self):
        import asyncio as _asyncio
        loop = _asyncio.new_event_loop()
        _asyncio.set_event_loop(loop)
        loop.run_until_complete(self._loop())

    async def _loop(self):
        import asyncio, websockets
        while self._on:
            try:
                async with websockets.connect(f"ws://127.0.0.1:{self.port}") as ws:
                    print(f"[HUD] ws://{self.port}")
                    while self._on:
                        self.msg.emit(json.loads(await ws.recv()))
            except Exception as e:
                print(f"[HUD] ws: {e}")
                await asyncio.sleep(2)

    def stop(self):
        self._on = False


# ── HUD Window ──────────────────────────────────────────────────────────

class HUD(QWidget):

    def __init__(self):
        super().__init__()
        self.setObjectName("hud")
        self.setWindowTitle("JARVIS")
        self.setFixedSize(380, 340)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Drag state
        self._drag_pos = None

        # Breathing animation (integrovaná do pozadia — žiadne orezávanie)
        self._breath = 1.0
        self._breath_anim = None
        self._start_breath("slow")

        self._sys = QTimer(self)
        self._sys.timeout.connect(self._refresh_sys)
        self._sys.start(2000)

        self._init_ui()
        self._pos()

        # Fade in
        self._fade_step = 0
        self.setWindowOpacity(0.0)
        self._ft = QTimer(self)
        self._ft.timeout.connect(self._fade)
        self._ft.start(25)

    # ── Drag to move ─────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() == Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = None
            event.accept()

    # ── Breathing animation ──────────────────────────────────────────

    def get_breath(self): return self._breath
    def set_breath(self, v):
        try:
            self._breath = v
            self.update()
        except Exception:
            pass  # Ctrl+C počas shutdownu — ignoruj

    breath = Property(float, get_breath, set_breath)

    def _start_breath(self, speed="normal"):
        speeds = {"slow": 2200, "normal": 1200, "fast": 600}
        dur = speeds.get(speed, 1200)
        if self._breath_anim:
            self._breath_anim.stop()
        self._breath_anim = QPropertyAnimation(self, b"breath")
        self._breath_anim.setDuration(dur)
        self._breath_anim.setStartValue(0.6)
        self._breath_anim.setEndValue(1.0)
        self._breath_anim.setEasingCurve(QEasingCurve.InOutSine)
        self._breath_anim.setLoopCount(-1)
        self._breath_anim.start()

    # ── Paint background + breathing glow ────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()

        # Glass panel
        path = QPainterPath()
        path.addRoundedRect(3, 3, w - 6, h - 6, 14, 14)
        p.fillPath(path, QBrush(BG))

        # Breathing glow — integrovaný do pozadia, žiadne orezanie
        cx, cy = 36, 32  # pozícia glow-u (ľavý horný roh)
        br = 22 * self._breath  # pulzujúci radius

        g = QRadialGradient(cx, cy, br * 2.5)
        g.setColorAt(0, QColor(0, 212, 255, 55))
        g.setColorAt(0.5, QColor(0, 160, 220, 12))
        g.setColorAt(1, QColor(0, 0, 0, 0))
        p.setBrush(QBrush(g))
        p.setPen(Qt.NoPen)
        p.drawEllipse(cx - br * 2.5, cy - br * 2.5, br * 5, br * 5)

        # Jadro (malý svetlý bod)
        g2 = QRadialGradient(cx, cy, br * 1.2)
        g2.setColorAt(0, QColor(140, 245, 255, 180))
        g2.setColorAt(0.5, QColor(0, 200, 240, 80))
        g2.setColorAt(1, QColor(0, 100, 180, 0))
        p.setBrush(QBrush(g2))
        p.drawEllipse(cx - br, cy - br, br * 2, br * 2)

        # Rám
        pen = QPen(BORDER, 1.2)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(4, 4, w - 8, h - 8, 13, 13)
        p.end()

    # ── UI ───────────────────────────────────────────────────────────

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 16, 22, 12)
        root.setSpacing(8)

        # Top: status + close button (glow je v pozadí, nie widget)
        top = QHBoxLayout()
        # Pridáme odsadenie zľava aby text neprekrýval glow
        top.setContentsMargins(42, 0, 0, 0)
        top.setSpacing(12)

        self.status = QLabel("⚡ JARVIS")
        self.status.setFont(QFont("Segoe UI", 16, QFont.Bold))
        self.status.setStyleSheet(f"color: {CYAN}; background: transparent;")
        top.addWidget(self.status)
        top.addStretch()

        # Web UI button
        self.web_btn = QPushButton("🌐")
        self.web_btn.setFixedSize(24, 24)
        self.web_btn.setFont(QFont("Segoe UI", 11))
        self.web_btn.setToolTip("Otvoriť Web UI v Opere")
        self.web_btn.setStyleSheet(
            "QPushButton { color: rgba(255,255,255,0.5); background: transparent; border: none; }"
            "QPushButton:hover { color: #00D4FF; background: rgba(0,212,255,0.15); border-radius: 12px; }"
        )
        self.web_btn.clicked.connect(self._do_webui)
        top.addWidget(self.web_btn)

        # X close button
        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(22, 22)
        self.close_btn.setFont(QFont("Segoe UI", 10))
        self.close_btn.setStyleSheet(
            "QPushButton { color: rgba(255,255,255,0.4); background: transparent; border: none; }"
            "QPushButton:hover { color: #FF4444; background: rgba(255,50,50,0.15); border-radius: 10px; }"
        )
        self.close_btn.clicked.connect(self.hide)
        top.addWidget(self.close_btn)

        root.addLayout(top)

        # Response — scrollable pre dlhšie odpovede
        self.resp = QLabel("")
        self.resp.setWordWrap(True)
        self.resp.setFont(QFont("Segoe UI", 11))
        self.resp.setStyleSheet(f"color: {WHITE}; background: transparent; padding: 4px 0;")
        self.resp.setMinimumHeight(40)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(self.resp)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { background: rgba(0,0,0,0.3); width: 6px; border-radius: 3px; }"
            "QScrollBar::handle:vertical { background: rgba(0,180,240,0.4); border-radius: 3px; min-height: 20px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )
        root.addWidget(self.scroll, stretch=1)
        root.addStretch(0)

        # Bottom: sysinfo + indicator
        bot = QHBoxLayout()
        self.info = QLabel("CPU --%  |  RAM --%  |  --:--")
        self.info.setFont(QFont("Consolas", 9))
        self.info.setStyleSheet(f"color: {GRAY}; background: transparent;")
        bot.addWidget(self.info)
        bot.addStretch()
        self.ws_dot = QLabel("●")
        self.ws_dot.setStyleSheet("color: rgba(255,90,90,0.5); font-size: 7px; background: transparent;")
        bot.addWidget(self.ws_dot)
        root.addLayout(bot)

    def _pos(self):
        s = QApplication.primaryScreen()
        if s:
            g = s.availableGeometry()
            self.move(g.right() - self.width() - 14, g.top() + 8)

    def _fade(self):
        self._fade_step += 1
        self.setWindowOpacity(min(0.88, self._fade_step * 0.05))
        if self._fade_step >= 18:
            self._ft.stop()

    def _refresh_sys(self):
        cpu, ram, now = get_system_info()
        self.info.setText(f"CPU {cpu:4.0f}%  |  RAM {ram:4.0f}%  |  {now}")

    # ── Events ───────────────────────────────────────────────────────

    def on_msg(self, d: dict):
        t = d.get("type", "")
        if t == "listening":
            self.status.setText("🎤 Počúvam...")
            self.resp.setText("")
            self._start_breath("fast")
            self.ws_dot.setStyleSheet(f"color: {CYAN}; font-size: 7px; background: transparent;")
            self._show()
        elif t == "thinking":
            self.status.setText("🧠 Premýšľam...")
            self._start_breath("fast")
            self._show()
        elif t == "speaking":
            self.status.setText("🔊 Hovorím...")
            self._start_breath("normal")
            self._show()
        elif t == "response":
            txt = d.get("text", "")
            if txt.startswith("[SK]") or txt.startswith("[EN]"):
                txt = txt[4:].strip()
            self.resp.setText(txt[:180])
            self.status.setText("⚡ JARVIS")
            self._start_breath("slow")
            self._show()
        elif t == "tool":
            self.status.setText(f"⚙️ {d.get('name', '?')}")
            self._start_breath("fast")
            self._show()
        elif t == "dismiss":
            self.hide()
            self._start_breath("slow")
        elif t == "command":
            a = d.get("action", "")
            if a in ("open_webui", "web_ui"):
                self._do_webui()
        elif t == "idle":
            self.status.setText("⚡ JARVIS")
            self._start_breath("slow")
        elif t == "shutdown":
            self.status.setText("🔌 Vypínam...")
            self._breath_anim = None
            self._breath = 1.0
            self.update()
            self._show()
        elif t == "error":
            self.resp.setText(f"⚠️ {d.get('text', '')[:180]}")
            self._show()

    def _show(self):
        self.show()
        self.raise_()

    def _do_webui(self):
        try:
            # Spusti Web UI server
            p = subprocess.Popen([sys.executable, _WEBUI_PATH], cwd=_PROJECT_ROOT)
            self._webui_proc = p  # udržať referenciu

            # Otvor v Opere (alebo default browsri ak Opera nie je)
            url = "http://127.0.0.1:5000"
            time.sleep(0.8)  # nech server nabehne

            opera_paths = [
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\Opera\opera.exe"),
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\Opera GX\opera.exe"),
                r"C:\Program Files\Opera\opera.exe",
                r"C:\Program Files\Opera GX\opera.exe",
            ]
            opera_bin = None
            for path in opera_paths:
                if os.path.exists(path):
                    opera_bin = path
                    break

            if opera_bin:
                subprocess.Popen([opera_bin, url])
                self.status.setText("🌐 Web UI v Opere")
            else:
                import webbrowser
                webbrowser.open(url)
                self.status.setText("🌐 Web UI spustené")

            self._show()
        except Exception as e:
            print(f"[HUD] webui: {e}")


# ── Tray App ────────────────────────────────────────────────────────────

class App(QApplication):

    def __init__(self, argv):
        super().__init__(argv)
        self.setApplicationName("JARVIS")
        self.setQuitOnLastWindowClosed(False)

        self.hud = HUD()
        self.mgr = ProcMgr()
        self._webui_proc = None

        self._mk_tray()
        self._ws = WSClient()
        self._ws.msg.connect(self.hud.on_msg)
        self._ws.start()

        self._t = QTimer(self)
        self._t.timeout.connect(self._tick)
        self._t.start(3000)

    # ── Tray icon + menu ─────────────────────────────────────────────

    def _mk_tray(self):
        from PySide6.QtGui import QPixmap
        pm = QPixmap(32, 32); pm.fill(Qt.transparent)
        p = QPainter(pm); p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QBrush(QColor(CYAN))); p.setPen(Qt.NoPen)
        p.drawEllipse(2, 2, 28, 28)
        p.setBrush(QBrush(QColor(0, 18, 38))); p.drawEllipse(5, 5, 22, 22)
        p.setBrush(QBrush(QColor(CYAN))); p.drawEllipse(9, 9, 14, 14)
        p.end()

        self.tray = QSystemTrayIcon(pm, self)
        self.tray.setToolTip("JARVIS — AI Assistant")

        m = QMenu()
        self._tray_status = m.addAction("⚡ JARVIS — Neaktívny"); self._tray_status.setEnabled(False)
        m.addSeparator()
        m.addAction("▶ Spustiť JARVIS").triggered.connect(self._start)
        m.addAction("⏹ Zastaviť JARVIS").triggered.connect(self._stop)
        m.addSeparator()
        m.addAction("🌐 Otvoriť Web UI").triggered.connect(self._webui)
        m.addSeparator()
        sm = m.addMenu("💬 Nedávne")
        self._sm = sm
        self._refresh_sm(sm)
        m.addSeparator()
        m.addAction("👁 Zobraziť HUD").triggered.connect(self.hud.show)
        m.addSeparator()
        m.addAction("❌ Ukončiť").triggered.connect(self._quit)

        self.tray.setContextMenu(m)
        self.tray.show()
        self.tray.activated.connect(lambda reason: self.hud._show() if reason == QSystemTrayIcon.Trigger else None)

    def _make_icon(self):
        from PySide6.QtGui import QPixmap
        pm = QPixmap(32, 32); pm.fill(Qt.transparent)
        p = QPainter(pm); p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QBrush(QColor(CYAN))); p.setPen(Qt.NoPen); p.drawEllipse(4, 4, 24, 24)
        p.end(); return pm

    def _refresh_sm(self, m):
        m.clear()
        ss = _load_recent_sessions()
        if not ss:
            m.addAction("(žiadne)").setEnabled(False)
        for s in ss:
            sid = s['id']
            a = m.addAction(f"{s['id']}  ({s['modified']})")
            a.triggered.connect(lambda checked, x=sid: subprocess.Popen(
                [sys.executable, _WEBUI_PATH], cwd=_PROJECT_ROOT,
                env={**os.environ, "JARVIS_SESSION": x}))

    # ── Actions ──────────────────────────────────────────────────────

    def _start(self):
        if not self.mgr.ok:
            self.mgr.status.connect(self._on_js)
            self.mgr.start()
            self._tray_status.setText("⚡ Spúšťam...")
            self.hud.status.setText("🔄 Spúšťam...")
            self.hud._start_breath("fast")
            self.hud._show()

    def _stop(self):
        if self.mgr.ok:
            self.mgr.stop()
            self._tray_status.setText("⚡ Zastavený")
            self.hud.status.setText("⚡ JARVIS (vypnutý)")
            self.hud._breath_anim = None; self.hud._breath = 1.0; self.hud.update()
            self.hud._show()

    def _webui(self):
        self._webui_proc = subprocess.Popen([sys.executable, _WEBUI_PATH], cwd=_PROJECT_ROOT)
        self.hud.status.setText("🌐 Web UI → http://127.0.0.1:5000")
        self.hud._show()

    def _on_js(self, s):
        if s == "running":
            self._tray_status.setText("⚡ JARVIS — Aktívny")
            self.hud.status.setText("⚡ JARVIS ONLINE")
            self.hud._start_breath("slow")
        elif s == "stopped":
            self._tray_status.setText("⚡ JARVIS — Zastavený")
            self.hud.status.setText("⚡ JARVIS (vypnutý)")
            self.hud._breath_anim = None; self.hud._breath = 1.0; self.hud.update()
        else:
            self._tray_status.setText(f"⚡ {s}")

    def _tick(self):
        self._tray_status.setText("⚡ JARVIS — Aktívny" if self.mgr.ok else "⚡ JARVIS — Neaktívny")
        self._refresh_sm(self._sm)

    def _quit(self):
        self.hud._breath_anim = None  # zastav animáciu pred shutdownom
        if self.mgr.ok: self.mgr.stop()
        self.hud.hide()
        self.quit()


# ── Entry point ─────────────────────────────────────────────────────────

def main():
    app = App(sys.argv)
    standalone = "--standalone" in sys.argv
    hidden = "--hidden" in sys.argv

    # Windows startup
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                           r"Software\Microsoft\Windows\CurrentVersion\Run",
                           0, winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE)
        cmd = f'"{sys.executable}" "{os.path.join(_PROJECT_ROOT, "hud", "overlay.py")}" --hidden'
        try:
            ex, _ = winreg.QueryValueEx(k, "JARVIS_HUD")
            if ex != cmd:
                winreg.SetValueEx(k, "JARVIS_HUD", 0, winreg.REG_SZ, cmd)
        except FileNotFoundError:
            winreg.SetValueEx(k, "JARVIS_HUD", 0, winreg.REG_SZ, cmd)
        winreg.CloseKey(k)
    except Exception:
        pass

    if standalone:
        app.hud.status.setText("⚡ JARVIS — DEMO")
        app.hud.resp.setText("Povedz 'Hey Jarvis' alebo klikni na ikonu v systray.")
        app.hud.show()
    elif hidden:
        app.tray.showMessage("⚡ JARVIS", "JARVIS je v system tray.\nPovedz 'Hey Jarvis' alebo klikni na ikonu.",
                             QSystemTrayIcon.Information, 3000)
    else:
        # Normálne spustenie — ukáž HUD, potom auto-spusti jarvis.py
        app.hud._show()
        # Po 1.5s automaticky spusti jarvis.py (wake word začne počúvať)
        QTimer.singleShot(1500, app._start)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
