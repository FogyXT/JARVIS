# JARVIS Web UI: Security Hardening Research

> Research for securing a Flask web interface with full desktop access (PowerShell execution, file modification, browser control, Instagram DM) exposed to the internet. Single user (Fogy), bilingual Slovak/English.

---

## 1. Authentication Methods

### Recommended approach: Password + TOTP 2FA, optionally WebAuthn

For a single-user system with destructive capability, **two-factor authentication is the minimum viable bar**. A single password -- no matter how strong -- is one credential away from total compromise.

**Tier 1 -- Password + TOTP (sweet spot)**
- Single hashed password stored with bcrypt/Argon2 (via Werkzeug's `generate_password_hash` or `flask-bcrypt`).
- TOTP second factor using `pyotp` library. Fogy scans a QR code once with Google Authenticator / Authy / Bitwarden.
- No user database or registration flow needed -- just two environment variables (`JARVIS_PASSWORD_HASH`, `JARVIS_TOTP_SECRET`) and a simple verify endpoint.
- Libraries: `flask-login` for session management (lightweight, single-user compatible).

**Tier 2 -- Password + WebAuthn (hardware key)**
- A YubiKey or platform passkey (Windows Hello, Touch ID) as second factor via Flask-Security's `[webauthn]` extra.
- Phishing-resistant -- a compromised tunnel cannot replay the credential.
- Overkill for most setups, but justifiable given the toolset (PowerShell, file write, Instagram).

**What to avoid**
- OAuth (Google/GitHub login) -- adds third-party dependency, attack surface via OAuth callback, and an internet dependency for auth.
- Flask-Security-Too (full framework) -- too much machinery for one user. Its WebAuthn module is useful, but the full RBAC/registration/password-reset flow is unnecessary.

**IP whitelisting**
- Useful as a secondary layer if Fogy has a static IP (e.g., home ISP, VPN exit node).
- Implemented as Flask `before_request` middleware checking `request.remote_addr`. Falls back to full auth if IP is unrecognised.

---

## 2. Session Management

### Flask configuration checklist

```ini
SECRET_KEY             = <env var, 64+ bytes from os.urandom>
SESSION_COOKIE_SECURE  = True          # HTTPS only
SESSION_COOKIE_HTTPONLY = True         # Inaccessible to JavaScript
SESSION_COOKIE_SAMESITE = 'Lax'        # CSRF mitigation
SESSION_COOKIE_NAME    = 'jarvis_sid'  # Non-default name (obscurity layer)
PERMANENT_SESSION_LIFETIME = 28800     # 8-hour absolute timeout
```

### Key patterns

- **Session regeneration**: Call `session.regenerate()` (Flask 2.3+ / `flask-session`) on every login to prevent session fixation.
- **Idle timeout**: Store `last_activity` timestamp in the session. On each request, check it against a 30-minute threshold. Redirect to login if exceeded.
- **Remember-me pattern**: For a single-user app, "remember me" == skip TOTP for 7 days via a persistent signed cookie (separate from the session cookie). Flask-Login's `remember_me` built-in handles this.
- **CSRF protection**: Use `flask-wtf`'s `CSRFProtect(app)` -- automatically validates a token on every POST/PUT/DELETE. For a JavaScript SPA (no HTML forms), pass the CSRF token via a `X-CSRF-Token` header read from a cookie or a `/api/csrf-token` endpoint.

### Emerging pattern (2025)

Modern browsers send `Sec-Fetch-Site`, `Sec-Fetch-Mode`, `Sec-Fetch-Dest` headers automatically. Validating `Sec-Fetch-Site: same-origin` or `Sec-Fetch-Site: same-site` on state-changing requests provides CSRF protection without token management. This is being adopted by Rails and discussed for Flask core.

---

## 3. API Security

### Session cookies vs Bearer tokens

| Criterion | Session cookie | Bearer token (JWT) |
|---|---|---|
| XSS resilience | High (HttpOnly flag) | Low (JS-accessible in localStorage) |
| CSRF needed | Yes | No |
| Revocation | Instant (server-side session) | Complex (need blacklist or short expiry) |
| Cross-origin | Requires CORS + credentials | Simple (Authorization header) |

**Recommendation: Session cookies for the SPA, with CSRF protection.**

Rationale: Simple architecture, instant revocation, XSS resilience. The SPA is served from the same origin as the Flask backend.

### CORS for tunneled access

When accessed via ngrok / Cloudflare Tunnel, the domain changes per session (ngrok) or is a Cloudflare proxy domain. Configure:

```python
from flask_cors import CORS
CORS(app, supports_credentials=True,
     origins=["https://*.ngrok-free.app", "https://jarvis.yourdomain.com"])
```

Do not use `origins="*"` with credentials -- the browser will reject it anyway.

### Rate limiting per endpoint

Use `flask-limiter` with distinct limits:

| Endpoint | Limit | Rationale |
|---|---|---|
| `/login` | 5 per minute per IP | Brute force |
| `/api/execute_command` | 10 per minute | Expensive/dangerous |
| `/api/file_manager/write` | 20 per minute | Destructive writes |
| `/api/instagram_dm` | 5 per minute | Platform rate limits |
| `/api/browser/control` | 10 per minute | Desktop automation |
| Static/read endpoints | 100 per minute | General usage |

### Request validation

Validate all parameters against schemas using **Pydantic** or **Marshmallow**. Reject unexpected keys, wrong types, and out-of-range values before they reach any tool handler.

---

## 4. Tool Access Control

This is the **most critical design decision** for the web UI. The desktop toolset (PowerShell, file write, browser control, Instagram) is equivalent to giving someone a root shell. The web UI must never expose the full tool surface without restrictions.

### Architecture pattern: Access tiers

```
              ┌──────────────────────┐
              │  Authentication       │
              │  (password + TOTP)    │
              └────────┬─────────────┘
                       │
              ┌────────▼─────────────┐
              │  Session valid?       │
              │  IP whitelisted?      │
              └────────┬─────────────┘
                       │
              ┌────────▼─────────────┐
              │  Tool router module   │
              │  (per-tool policies)  │
              └────────┬─────────────┘
                       │
         ┌─────────────┼─────────────┐
         ▼             ▼             ▼
   Read tools    Dangerous      Destructive
   (list dir,    tools          tools
    read file,   (exec cmd,     (file delete,
    screenshot)   browser)       Instagram DM)
         │             │             │
         ▼             ▼             ▼
   Auto-approve  Confirmation     Password
                 gate (modal)     re-auth
```

### Implementation rules per tool

**execute_command**
- Command allowlist (not blocklist). Allow only known-safe commands: `ipconfig`, `systeminfo`, `tasklist`, `Get-Process`, `Get-Service`, `ping -n 1 <host>`.
- _Never_ allow arbitrary PowerShell. If needed, require a separate "expert mode" toggle that triggers a confirmation gate.
- Prepend `Write-Host "JARVIS: "` to every command so output is clearly demarcated.

**file_manager**
- Restrict operations to `D:/JARVIS/` and its subdirectories. Use canonical path resolution (`pathlib.Path.resolve()`) with containment check via `os.path.commonpath`.
- `write` and `delete` require confirmation modal.
- `read` is auto-approved but content is truncated at 10,000 chars (same as current desktop version).
- Block write to `.env`, `*.key`, `*.pem`, `*secret*` -- Fogy must edit these manually or via a separate authenticated endpoint.

**control_browser**
- Require confirmation for every action sequence (display the planned actions as a list, Fogy approves or rejects).
- No background/headless automation without visible confirmation.

**instagram_dm**
- Require password re-authentication before each send (confirms Fogy is at the keyboard).

**take_screenshot**
- Read-only, auto-approved. The image is shown inline in the UI.

**memory (read/write/delete)**
- `read` auto-approved.
- `write` and `delete` require confirmation.

### Design principle: Confirmation gates

Every confirmation gate should show:
1. The tool being called.
2. The exact parameters (masking secrets like passwords).
3. A "Cancel" button (default, highlighted).
4. A "Confirm" button (requires explicit click, not accidental Enter).
5. Optional: "Approve for N minutes" checkbox to reduce friction during active sessions.

---

## 5. Audit Logging

### What to log

Every API call should log a structured entry:

```json
{
  "timestamp": "2026-06-11T14:30:00Z",
  "ip": "185.xx.xx.xx",
  "session_id": "abc123",
  "tool": "execute_command",
  "params": {"command": "ipconfig"},
  "result_summary": "success / blocked / error",
  "duration_ms": 450
}
```

### Tamper-proofing

Use **tamperloom** (PyPI, 2025) or implement a hash chain manually:
- Each log entry contains SHA-256(current_entry + previous_entry_hash).
- Store the chain head hash in a separate location (or email it to Fogy periodically).
- Verification script detects any insertion, deletion, or modification.

### What to monitor for alerting

- 3+ failed login attempts from the same IP in 5 minutes.
- Any call to a blocked/forbidden tool.
- `execute_command` with `powershell -EncodedCommand` or suspicious flags.
- `file_manager.write` targeting `.py` files outside known project directories.
- Access from an unexpected country (geolocate via Cloudflare or `geoip2`).
- Login from a new IP (compare against a persistent allowlist).

### Alert delivery

- Email (SMTP via `smtplib` or SendGrid API).
- Telegram bot notification for immediate awareness.

---

## 6. Network Security

### Fail2ban equivalent

Flask-Limiter handles per-IP rate limiting in-application. For a network-level block, use:

- **Cloudflare IP Access Rules**: Block IPs after N failed logins (via Cloudflare API or manually after reviewing logs).
- **Windows Firewall**: Script a rule via `netsh advfirewall firewall add rule` on repeated offenders.
- **flask-ratelimit-simple** with escalating block durations (1 min -> 5 min -> 1 hour -> permanent).

### Geoblocking

If Fogy only accesses from Slovakia, block all other countries:

- **Cloudflare WAF**: Create a "Country" rule blocking all except `SK`. Free tier supports this.
- **Application-level**: Use `flask-geoip` or `maxminddb-geolite2` to check `request.remote_addr` against a GeoIP database and reject non-SK traffic (fallback: ask Fogy to whitelist the IP).

### Cloudflare WAF rules (free tier)

1. Block all traffic except from Slovakia (country allowlist).
2. Rate limit: 20 requests per 5 minutes per IP for `/login`.
3. Challenge (JS challenge / CAPTCHA) for any request without a valid session cookie hitting `/api/*`.
4. Block requests with known malicious patterns (SQLi, XSS) -- Cloudflare's OWASP ruleset covers this.

### SSL/TLS

- Cloudflare Tunnel provides automatic, free HTTPS.
- If using a direct server: Let's Encrypt + Certbot + Nginx reverse proxy.
- Set `force_https=True` via Flask-Talisman.
- HSTS header: `max-age=31536000; includeSubDomains` (1 year).
- Minimum TLS version: 1.3 (Cloudflare or Nginx config).

---

## 7. Flask Production Hardening

### WSGI server (Windows)

```text
Client (browser)
    │
    ▼
Cloudflare Tunnel ───┬──→ Nginx (off-box, optional)
    │                 │       │
    └──→ localhost:443        │
                              ▼
                    Waitress (port 5000, threads=8)
                              │
                              ▼
                         Flask app
```

- **Waitress** is the recommended production WSGI server for Windows (Gunicorn is Unix-only).
- Run as a Windows service using `winsw` (Windows Service Wrapper) for auto-start and auto-restart.
- Do not use `flask run` -- it is a development server, single-threaded, and warns about production use.

### Required config

```ini
DEBUG = False                           # Never True in production
SECRET_KEY = <env var, not in code>
ENV = 'production'
PREFERRED_URL_SCHEME = 'https'
MAX_CONTENT_LENGTH = 16 * 1024 * 1024   # 16 MB upload limit
JSONIFY_PRETTYPRINT_REGULAR = False     # Reduce bandwidth
```

### Security headers (Flask-Talisman)

```python
Talisman(app,
    force_https=True,
    strict_transport_security=True,
    content_security_policy={
        'default-src': "'self'",
        'script-src': "'self'",
        'style-src': "'self' 'unsafe-inline'",  # Allow inline for simplicity
        'img-src': "'self' data:",
        'frame-ancestors': "'none'",
    },
    frame_options='DENY',
    referrer_policy='strict-origin-when-cross-origin',
    session_cookie_secure=True,
    session_cookie_http_only=True,
    session_cookie_samesite='Lax',
)
```

### Dependency auditing

- `pip-audit` in CI/CD (or run weekly).
- Dependabot / Renovate for automated PRs.
- Pin versions in `requirements.txt`, but update monthly.

### Error handling

- Custom 404/403/500 pages -- never expose a Flask traceback.
- Log full tracebacks to `jarvis_web.log` (file, not stdout).
- Generic JSON error response for API endpoints: `{"error": "Internal server error"}`.

---

## 8. Backup Access

### Primary: Cloudflare Tunnel (cloudflared)

- Runs as a Windows service.
- Outbound-only connection to Cloudflare's edge -- no open inbound ports.
- Custom domain (e.g., `jarvis.fogy.sk`) with automatic HTTPS.
- If Cloudflare goes down: wait for recovery (rare), or fall back.

### Secondary: Tailscale

- Install Tailscale on the desktop and Fogy's phone/laptop.
- Creates a WireGuard mesh network. Access via `http://jarvis-pc:5000` on the tailnet.
- No public exposure -- only devices on the Tailscale network can connect.
- Free tier supports 100 devices.

### Emergency: Ngrok (tertiary)

- One-command fallback when both Cloudflare and Tailscale are unreachable.
- `ngrok http 5000 --basic-auth="fogy:<hashed-password>"` for built-in auth.
- Free tier gives a random URL -- Fogy checks the local logs for the URL.

### Offline backup

- A static HTML page served on the local network (LAN-only, no tunnel) that shows:
  - Current tunnel status.
  - Instructions to restart `cloudflared` via a local script.
  - Emergency contact instructions.

### Connection health monitoring

- A heartbeat script (runs every 5 minutes via Task Scheduler):
  - Pings the Cloudflare Tunnel URL.
  - If unreachable: attempts Tailscale connectivity.
  - If both fail: sends a Telegram/email alert with the current ngrok URL.
- Display tunnel status in the web UI header (green/yellow/red indicator).

---

## 9. Security Checklist (Prioritized)

### CRITICAL -- Do these first, before any public exposure

- [ ] **Password + TOTP 2FA** implemented and tested.
- [ ] **Secret key** in environment variable, not in code. 64+ random bytes.
- [ ] **Debug mode off** (`FLASK_DEBUG=0`, `ENV=production`).
- [ ] **Flask behind Waitress** (not `flask run`).
- [ ] **HTTPS enforced** (Cloudflare Tunnel or Nginx + Let's Encrypt).
- [ ] **Session cookies configured**: Secure, HttpOnly, SameSite=Lax.
- [ ] **CSRF protection** enabled (Flask-WTF `CSRFProtect`).
- [ ] **Rate limiting** on `/login` endpoint (5 per minute per IP).
- [ ] **execute_command allowlist** implemented (no arbitrary commands).
- [ ] **file_manager path restriction** to `D:/JARVIS/` with canonical path check.
- [ ] **Audit logging** active (all tools, all params).
- [ ] **Dev tunnel (ngrok) never used in production** -- use Cloudflare Tunnel.

### IMPORTANT -- Do next

- [ ] **Confirmation gates** for destructive operations (delete file, Instagram DM, browser control).
- [ ] **Idle timeout** (30 min) and absolute session timeout (8 hours).
- [ ] **Flask-Talisman** with CSP and HSTS headers.
- [ ] **Geoblocking** via Cloudflare WAF (Slovakia-only, or at least non-Slovakia block).
- [ ] **IP-based escalation blocking** (temporary ban after 5 failed logins).
- [ ] **Sensitive file write protection** (block `.env`, `*.key`, `*secret*`).
- [ ] **Plugin for failed-login alert** (Telegram or email).
- [ ] **Tamper-proof log verification** script (run daily).

### NICE-TO-HAVE -- Add when time permits

- [ ] **WebAuthn hardware key** as primary or secondary auth factor.
- [ ] **Command allowlist expansion** with parameter validation per command.
- [ ] **Separate "read-only" session mode** for quick checks (no confirmation needed).
- [ ] **Password re-authentication** for Instagram DM and `execute_command`.
- [ ] **Backup access** (Tailscale) configured and tested.
- [ ] **Connection health monitor** with automatic ngrok failover.
- [ ] **Cloudflare WAF custom rules**: rate limiting, challenge for unauthenticated API calls.
- [ ] **Dependency auditing** automated (pip-audit in cron/Task Scheduler).
- [ ] **Windows Firewall rules** for additional IP blocking.
- [ ] **Panic button**: A UI button that instantly revokes all sessions and disables the tunnel.

---

## Summary of Key Decisions

| Decision | Choice | Why |
|---|---|---|
| Auth library | Flask-Login (custom) | Single user, no bloat |
| 2FA | TOTP (pyotp) | Simple, standard, no hardware cost |
| Session storage | Server-side (Flask-Session + filesystem or Redis) | Instant revocation |
| CSRF | Flask-WTF CSRFProtect | Battle-tested, simple |
| Rate limiting | Flask-Limiter | Most mature, Redis-ready |
| Tunnel | Cloudflare Tunnel (primary), Tailscale (backup) | Free, HTTPS, no open ports |
| WSGI server | Waitress | Only viable option on Windows |
| Security headers | Flask-Talisman | One extension, comprehensive |
| Log tamper-proofing | tamperloom or custom hash chain | Detect post-compromise log cleaning |
| Command restriction | Allowlist + confirmation gate | Prevent arbitrary code execution |
| File restriction | Canonical path + directory allowlist | Prevent path traversal |

The guiding principle: **trust nothing from the browser, treat every API call as potentially hostile, and make destructive actions require Fogy's active, informed consent.**
