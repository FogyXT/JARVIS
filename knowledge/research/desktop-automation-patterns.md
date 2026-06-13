# Desktop Automation Patterns & Best Practices

Research summary for the JARVIS project (Python, Windows). Compiled 2026-06-11.

---

## AREA 1: GUI Automation Best Practices

### PyAutoGUI Reliability Patterns

PyAutoGUI is best suited for coordinate-based, screen-resolution-dependent automation. To make it reliable, adopt these practices:

- **Keep the failsafe enabled** (`pyautogui.FAILSAFE = True`). Moving the mouse to any screen corner raises `FailSafeException`, serving as an emergency brake. Never disable this in production.
- **Set a global PAUSE** (`pyautogui.PAUSE = 0.1` to `0.5` seconds) to insert a delay after every call, slowing execution enough that a human can intervene.
- **Constrain image search regions.** Always pass the `region` parameter to `locateOnScreen()` to limit scanning to a small bounding box. This reduces false positives and improves performance significantly.
- **Crop template images tightly.** Remove borders and background from template images — extra context causes false matches when the UI changes. With clean templates, raise `confidence` to `0.99`.
- **Prefer pixel-based detection** (`pyautogui.pixel()`, `pixelMatchesColor()`) when UI elements have distinctive colors — it is faster and more deterministic than image recognition.
- **Cache stationary coordinates.** If a UI element never moves, cache its click coordinates after the first successful match rather than re-searching every cycle.
- **Randomize timing.** Add small random jitter to click delays (e.g., `base_delay +/- 0.03s`) to make automation less detectable and more forgiving of timing variations.

### Browser Automation: webbrowser vs. Selenium vs. Playwright

**`webbrowser` (stdlib):** Not a browser automation tool. It simply opens a URL in the default browser. Useful only for OAuth redirects or showing a page to the user. No interaction, no headless mode, no element access.

**Selenium:** The veteran framework with the widest browser support (Chrome, Firefox, Safari, Edge, IE, Opera, plus mobile via Appium). Its main weaknesses are manual wait management (requires `WebDriverWait` and explicit conditions), HTTP protocol overhead making it slower, and higher flakiness with dynamic content. The ecosystem is mature (20+ years) with the largest community and Stack Overflow presence.

**Playwright (recommended for new projects):** Microsoft's modern framework (2020) with automatic waiting built in — Playwright checks visibility, stability, and actionability before every interaction, dramatically reducing flakiness (60-80% fewer failures reported). It is 30-40% faster than Selenium (persistent WebSocket protocol), includes first-class network interception, trace viewer, video recording, and browser contexts for lightweight isolated sessions. Downsides: no legacy browser support (no IE11), smaller community than Selenium.

**Decision rule for JARVIS:** For simple "open URL" tasks, `webbrowser` + PyAutoGUI for basic interaction is adequate. For any automation requiring reliability, element-level control, or headless operation, Playwright is the default choice.

### Alternative Windows Automation Approaches

Beyond PyAutoGUI, several Windows-native approaches exist:

- **pywinauto** — Wraps Win32 and UIA (UI Automation) accessibility APIs. Enables direct control of native Windows applications without screen coordinates: `find_window()`, `.click()`, `.type_keys()`. Best for MFC, WPF, WinForms, and Qt apps.
- **Python-UIAutomation-for-Windows** — Pure Python wrapper around Microsoft's UIAutomation framework with a standardized Pattern System (InvokePattern for buttons, ValuePattern for text, ExpandCollapsePattern for trees, etc.). More reliable than coordinate-based approaches for accessible controls.
- **robocorp.windows** — Enterprise RPA-oriented, built on UIAutomation with a sophisticated locator system (`name:`, `subname:`, `regex:`, `control:`, `id:`, `class:`) and built-in error handling.
- **AutoHotKey** (external) — Lightweight Windows scripting language. Can be called from Python via subprocess for tasks like hotkey binding, window management, and keystroke automation.
- **COM objects** (`win32com.client`) — Direct OLE Automation interface into Windows apps (Excel, Outlook, Office). Extremely reliable but application-specific.

**Preferred order of approaches:** UIA/Win32 APIs (most reliable) -> coordinate-based PyAutoGUI (good for games/custom controls) -> image recognition / OpenCV (last resort for legacy apps with no accessibility support).

### Handling Flaky UI Automation

- **Retry with exponential backoff.** Implement a loop that retries failed operations 3-5 times with increasing wait times. Distinguish between "temporarily unavailable" and "task impossible."
- **Screenshot on failure.** Always capture what the screen looked like at the moment of failure for post-mortem debugging.
- **Wait conditions are non-negotiable.** Never `sleep()` a fixed amount. Instead, poll for the expected condition (element visible, window title matches, pixel color changes). Use explicit wait loops with timeouts.
- **Validate after action.** After clicking, verify the expected outcome occurred (new window opened, text changed, dialog appeared) before proceeding.
- **The clipboard method for text extraction.** Instead of fragile OCR, select text via `pyautogui.tripleClick()` and `Ctrl+C`, then read with `pyperclip.paste()`. Nearly 100% accurate and fast.

### Security Concerns for Desktop Automation

Running automation on the user's real desktop means:
- Automation runs with the user's full permissions — any malicious action (file deletion, credential theft, unwanted purchases) executes with real authority.
- PyAutoGUI controls mouse and keyboard globally. A bug can click the wrong thing, type destructive commands, or interfere with other applications.
- **Mitigations:** Keep FAILSAFE enabled, log every action, prefer accessibility APIs over coordinate clicking, test in isolated environments before running on the real desktop, and never accept untrusted automation scripts.

---

## AREA 2: System Interaction Patterns

### PowerShell Execution from Python

**Security first:** Never construct PowerShell commands via string interpolation with user input — this invites command injection. Escape single quotes by doubling them (`'` -> `''`), and validate or sanitize any dynamic parameters before interpolation.

**Approaches ranked by reliability:**

1. **`subprocess.run()` with explicit args** — Pass the command list as a sequence, not a string, to avoid shell injection. Use `subprocess.run(["powershell", "-NoProfile", "-Command", command], capture_output=True, timeout=30)`. Always use `-NoProfile` to skip user profile loading (faster, more predictable).

2. **Persistent sessions (`py-pwsh-session`)** — Spawns `pwsh -NoExit -Command -` and communicates over stdin/stdout. Better for multi-command workflows: the session state (variables, drive mounts, modules) persists across commands. Includes built-in `sanitize()` for injection prevention, ANSI escape stripping, and JSON parsing.

3. **Timeout handling** — Always set a timeout. Without it, a hung PowerShell process (waiting on network, user prompt, or infinite loop) blocks Python indefinitely. On timeout, `subprocess.TimeoutExpired` is raised; terminate the process tree via `taskkill /F /T /PID`.

**Output capture:** Read both stdout and stderr. PowerShell errors go to stderr by default. Use `ConvertTo-Json` and pipe through `-Json` for structured output, or parse the text output. Strip ANSI escape sequences if the output contains color codes.

### File System Operations

**Atomic writes (crash-safe file saving):** The canonical pattern is write-to-temp-then-rename:
1. Create a temporary file in the same directory as the target (same filesystem, so `rename` works).
2. Write the data, `flush()`, and `fsync()` the file descriptor to ensure the OS has flushed buffers to disk.
3. Call `os.replace(tmpname, filename)` to atomically swap the temp file over the original.
4. On failure, delete the temp file and optionally restore from backup.

This guarantees the target file is never partially written — it either has the old content or the complete new content.

**Backup before overwrite:** Before writing, copy the original to `<filename>.bak` via `os.replace(filename, backup_name)` (or `shutil.copy2` to preserve metadata). On failure, restore the backup. For self-modifying agents (like JARVIS's `call_developer_agent`), this is a critical safety net.

**Permission handling on Windows:** Temp files created via `tempfile.mkstemp()` have restricted permissions (0600). After the atomic swap, the file may need `os.chmod()` to match the original's permissions. Standard user accounts under Windows do not have permission to write to `C:\Program Files` or system directories — always run with appropriate privileges or write to user-writable locations.

### Clipboard Manipulation

- **Text only:** `pyperclip` is the most popular cross-platform library. Simple `pyperclip.copy("text")` / `pyperclip.paste()`.
- **Images:** `pyperclip` does not support images. Use `PIL.ImageGrab.grabclipboard()` to read images from the clipboard on Windows. For writing images, use `pyperclipimg` or `jaraco.clipboard`.
- **Binary data:** `pyperclip3` supports arbitrary binary clipboard data. For reading clipboard from a remote or headless context, no clipboard API works — the clipboard is a per-session Windows concept.

### Process Management

**Launching apps:** Use `subprocess.Popen()` for non-blocking application launch. Set `creationflags=subprocess.CREATE_NO_WINDOW` for silent background processes.

**Tracking and cleanup** is the hard part. On Windows, child processes are not automatically cleaned up when the parent dies — they become orphans.

**Three reliable approaches:**

1. **Windows Job Objects (WinJobster)** — Groups all spawned processes into a Job. When you call `job.terminate()`, the entire process tree is killed. This is the idiomatic Windows solution.
2. **`psutil` with recursive termination** — Enumerate and kill children via `psutil.Process(pid).children(recursive=True)`, killing deepest children first.
3. **`taskkill /F /T /PID`** — The blunt hammer. Works from any context, kills the entire process tree including grandchildren.

For the JARVIS model, the simplest reliable pattern is: launch with `subprocess.Popen`, capture the PID, and on cleanup call `taskkill /F /T /PID` to guarantee no orphan processes remain.

---

## AREA 3: Social Media Automation

### Instagram Automation Patterns

Instagram's anti-bot systems in 2025 are aggressive. The core principles for safe automation:

**Rate limiting is mandatory.** Use randomized delays (not fixed intervals) between actions. Suggested safe limits: 10 DMs/hour (50/day), 20-30 likes/hour, 10-15 comments/hour. Implement exponential backoff on HTTP 429 responses (start with 30-60 second retry delays, scaling by attempt number).

**Detection avoidance requires human-like behavior.** Before performing an action, visit the homepage, sometimes browse the explore page (30% probability), and always simulate realistic timing. Rotate User-Agent strings and use residential proxies (not datacenter IPs, which are flagged immediately).

**Session persistence matters.** Save cookies to disk via `pickle` after login and reuse them across runs. This avoids repeated logins which trigger security checks.

**For messaging specifically:** Check for existing conversations before sending to avoid duplicates. Track sent messages persistently so no user receives duplicates. Validate target profiles exist before attempting to DM. Use character substitution (e.g., `l` -> `I`) to bypass simple spam filters.

**API alternatives (preferred when possible):**
- **Official Instagram Graph API** — Compliant, but heavily restricted for DMs (requires approved use case, limited to business accounts).
- **Third-party API services** — Handle anti-detection infrastructure for you, at a cost.
- **Direct scraping / unofficial API wrappers** (instagrabi, instaloader) — Most flexible but highest risk of account blocks.

**Key mistakes that trigger blocks:** Fixed timing intervals, missing session cookies, datacenter proxies, headless browser defaults, high request volume per minute, and identical repeated actions.

---

## Architectural Insights for JARVIS

1. **Layered automation approach.** Start with the most reliable method for any task: UIA/Win32 APIs for native Windows apps -> Playwright for web -> PyAutoGUI as fallback. Each level trades off reliability for universality.

2. **Atomic writes with backups.** The existing `call_developer_agent` backup pattern (`.bak` before overwrite) is exactly right. Extend it to all file writes from `file_manager` for consistency.

3. **Process cleanup discipline.** Every launched subprocess must be tracked (PID + Job Object) and guaranteed a cleanup path. Orphan processes accumulate and waste system resources.

4. **Parameterized wait conditions.** Never hardcode sleep durations. Abstract waits behind a polling function with timeout and condition check, so the system adapts to machine speed and load.

5. **Fail visible, not silent.** Screenshot on automation failure, log the full element tree if available, and surface actionable error messages. Silent failures in desktop automation are dangerous because the script can continue operating on the wrong state.

6. **Rate-limit social actions aggressively.** For any social platform integration, treat 10-20 actions per hour as the ceiling, add randomized jitter, and throttle on any 429/403 response.
