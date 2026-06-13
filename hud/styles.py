"""
Iron Man štýl — farby, fonty, CSS pre HUD overlay.
"""

# Hlavná téma (cyan/modrá ako Arc Reactor)
ARC_CYAN = "#00BFFF"
ARC_BLUE = "#0088CC"
ARC_DARK = "#002233"
GOLD = "#D4AF37"
WHITE = "#E0E8F0"
RED_ALERT = "#FF3333"
GREEN_OK = "#33FF99"
BG_GLASS = "rgba(0, 15, 30, 0.85)"

# Fonty (s fallbackmi)
FONT_TITLE = "Segoe UI, Arial, sans-serif"
FONT_MONO = "JetBrains Mono, Consolas, monospace"

# CSS pre QLabel a iné widgety
STYLE_MAIN = f"""
    QWidget#hudMain {{
        background: transparent;
    }}
"""

STYLE_STATUS = f"""
    QLabel#statusLabel {{
        color: {ARC_CYAN};
        font-family: {FONT_TITLE};
        font-size: 18px;
        font-weight: bold;
        background: transparent;
    }}
"""

STYLE_RESPONSE = f"""
    QLabel#responseLabel {{
        color: {WHITE};
        font-family: {FONT_TITLE};
        font-size: 14px;
        background: transparent;
        padding: 8px;
    }}
"""

STYLE_REACTOR = f"""
    QWidget#reactorWidget {{
        background: transparent;
    }}
"""

STYLE_SYSINFO = f"""
    QLabel#sysInfoLabel {{
        color: rgba(200, 210, 220, 0.7);
        font-family: {FONT_MONO};
        font-size: 11px;
        background: transparent;
    }}
"""
