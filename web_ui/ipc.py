import os
import json
import time

IPC_DIR = os.path.dirname(os.path.abspath(__file__))

INBOX = os.path.join(IPC_DIR, ".coding_inbox.json")
OUTBOX = os.path.join(IPC_DIR, ".coding_outbox.json")

def write_inbox(message, images=None):
    """Write user message to inbox for Claude Code to process."""
    entry = {
        "id": str(time.time()),
        "message": message,
        "images": images or [],
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(INBOX, "w", encoding="utf-8") as f:
        json.dump(entry, f, ensure_ascii=False)
    return entry["id"]

def read_outbox(msg_id, timeout=120):
    """Poll outbox for response with matching ID."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.exists(OUTBOX):
            try:
                with open(OUTBOX, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("id") == msg_id and data.get("status") == "done":
                    os.remove(OUTBOX)
                    return data.get("response", "")
            except (json.JSONDecodeError, KeyError):
                pass
        time.sleep(0.5)
    return None  # timeout
