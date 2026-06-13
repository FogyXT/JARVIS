#!/usr/bin/env python
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="pygame")
"""Spusti Jarvis Web UI - lokalny webovy chat s dvomi modmi.

Usage:
    python run_webui.py          # Spusti na http://127.0.0.1:5000
    python run_webui.py --port 8080  --host 0.0.0.0
"""
import sys
sys.path.insert(0, r"D:\JARVIS")

from web_ui.app import main

if __name__ == "__main__":
    # Parse --port and --host from args
    port = 5000
    host = "127.0.0.1"
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--port" and i + 1 < len(args):
            port = int(args[i + 1])
        elif arg == "--host" and i + 1 < len(args):
            host = args[i + 1]

    import os
    os.environ["WEBUI_PORT"] = str(port)
    os.environ["WEBUI_HOST"] = host
    main()
