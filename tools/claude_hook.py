"""
Claude Code auto-memory hook — runs after every interaction.
Maintains JARVIS memory: consolidation, decay, fact extraction.
"""
import sys, os, json, time
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path: sys.path.insert(0, PROJECT_ROOT)

def main():
    try:
        hook_input = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    except: hook_input = {}
    
    try:
        # Periodic consolidation every ~10 calls
        counter_file = os.path.join(PROJECT_ROOT, "auto_memory_counter.json")
        counter = {}
        if os.path.exists(counter_file):
            with open(counter_file) as f: counter = json.load(f)
        calls = counter.get("hook_calls", 0) + 1
        counter["hook_calls"] = calls
        
        if calls % 10 == 0:
            from tools.consolidation import consolidate_quick
            r = consolidate_quick()
            counter["last_consolidation"] = time.time()
        
        os.makedirs(os.path.dirname(counter_file), exist_ok=True)
        with open(counter_file, "w") as f: json.dump(counter, f)
    except Exception: pass
    
    print(json.dumps({"continue": True}))

if __name__ == "__main__": main()
