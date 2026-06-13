"""
Arc Reactor widget — pulzujúci kruh v štýle Iron Man.
Používa QPainter na kreslenie glow efektu a pulz animáciu.
Centered drawing — všetko relatívne k veľkosti widgetu.
"""

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QTimer, QPointF, Property, QEasingCurve, QPropertyAnimation
from PySide6.QtGui import QPainter, QBrush, QColor, QRadialGradient, QPen

from hud.styles import ARC_CYAN, ARC_BLUE


class ArcReactor(QWidget):
    """Animovaný Arc Reactor — kruh s glow efektom a pulzom."""

    def __init__(self, parent=None, size=80):
        super().__init__(parent)
        self.setObjectName("reactorWidget")
        self.setFixedSize(size, size)
        self._pulse = 1.0
        self._animation = None
        self._is_active = False
        self._speed = 1500

    def start_pulse(self, speed="normal"):
        """Spustí pulzovanie. speed: 'slow', 'normal', 'fast'."""
        speeds = {"slow": 2500, "normal": 1500, "fast": 700}
        self._speed = speeds.get(speed, 1500)
        self._is_active = True
        if self._animation:
            self._animation.stop()
        self._animation = QPropertyAnimation(self, b"pulse")
        self._animation.setDuration(self._speed)
        self._animation.setStartValue(1.0)
        self._animation.setEndValue(1.6)
        self._animation.setEasingCurve(QEasingCurve.InOutSine)
        self._animation.setLoopCount(-1)
        self._animation.start()

    def stop_pulse(self):
        self._is_active = False
        if self._animation:
            self._animation.stop()
            self._animation = None
        self._pulse = 1.0
        self.update()

    def get_pulse(self):
        return self._pulse

    def set_pulse(self, value):
        self._pulse = value
        self.update()

    pulse = Property(float, get_pulse, set_pulse)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        center = QPointF(w / 2, h / 2)
        base_radius = min(w, h) * 0.22  # ~18px pri 80px widgete
        radius = base_radius * self._pulse

        # 1. Vonkajší glow (široký, jemný)
        glow_outer = QRadialGradient(center, radius * 2.8)
        glow_outer.setColorAt(0, QColor(0, 180, 255, 50))
        glow_outer.setColorAt(0.5, QColor(0, 140, 220, 15))
        glow_outer.setColorAt(1, QColor(0, 0, 0, 0))
        p.setBrush(QBrush(glow_outer))
        p.setPen(Qt.NoPen)
        p.drawEllipse(center, radius * 2.8, radius * 2.8)

        # 2. Stredný glow
        glow_mid = QRadialGradient(center, radius * 1.4)
        glow_mid.setColorAt(0, QColor(0, 220, 255, 140))
        glow_mid.setColorAt(0.6, QColor(0, 160, 220, 40))
        glow_mid.setColorAt(1, QColor(0, 80, 180, 10))
        p.setBrush(QBrush(glow_mid))
        p.drawEllipse(center, radius * 1.4, radius * 1.4)

        # 3. Hlavný kruh
        main_glow = QRadialGradient(center, radius)
        main_glow.setColorAt(0, QColor(0, 235, 255, 200))
        main_glow.setColorAt(0.5, QColor(0, 180, 220, 100))
        main_glow.setColorAt(1, QColor(0, 120, 200, 30))
        p.setBrush(QBrush(main_glow))
        p.drawEllipse(center, radius, radius)

        # 4. Vnútorný svetlý bod (core)
        inner = QRadialGradient(center, radius * 0.35)
        inner.setColorAt(0, QColor(200, 245, 255, 230))
        inner.setColorAt(1, QColor(0, 200, 255, 0))
        p.setBrush(QBrush(inner))
        p.drawEllipse(center, radius * 0.35, radius * 0.35)

        # 5. Tenký okraj
        pen = QPen(QColor(ARC_CYAN), 1.5)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(center, radius, radius)

        # 6. Horizontálne a vertikálne linky (Iron Man štýl)
        line_pen = QPen(QColor(0, 160, 220, 60), 0.5)
        p.setPen(line_pen)
        # Horizontálna
        p.drawLine(
            int(center.x() - radius * 1.3), int(center.y()),
            int(center.x() + radius * 1.3), int(center.y())
        )
        # Vertikálna
        p.drawLine(
            int(center.x()), int(center.y() - radius * 1.3),
            int(center.x()), int(center.y() + radius * 1.3)
        )

        p.end()
