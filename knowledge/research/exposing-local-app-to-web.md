# Exposing a Local Flask App to the Web Securely

> Research for the JARVIS project: a voice-driven Windows desktop assistant with full desktop access (PowerShell, file system, browser automation, Instagram DM) exposed via a Flask web UI on localhost:5000.

---

## 1. Tunneling Solutions — Head-to-Head

### Cloudflare Tunnel (cloudflared) — RECOMMENDED

**Free tier:** Unlimited tunnels, unlimited bandwidth, unlimited requests, custom domain support, automatic HTTPS, DDoS protection, WAF. The only real cost is owning a domain (~$8-12/year).

**WebSocket:** Full support. Cloudflare Tunnel streams TCP connections over WebSocket under the hood. SSE (Server-Sent Events) works natively — Cloudflare explicitly documents SSE as suitable for streaming AI responses and server-push notifications. No timeout issues for long-lived HTTP connections.

**Latency:** ~15-45ms overhead via Cloudflare's 200+ global PoPs. Benchmark shows ~46 Mbps throughput (vs ngrok's ~8.8 Mbps). Significantly better for streaming.

**Rate limits (free):** None practically. A 100MB single-upload cap exists, but for a text-heavy assistant UI this is irrelevant. ToS technically restricts serving non-HTML content (video/streaming), but an LLM chat interface is squarely within allowed use.

**Persistence:** Built-in `cloudflared service install` registers a native Windows service with auto-start, automatic restart on failure (20-second delay). No NSSM needed.

**Security caveat:** Cloudflare terminates TLS at their edge — they decrypt your traffic. For a tool that runs PowerShell on your desktop, this is a meaningful trust decision. However, Cloudflare is SOC 2 compliant, supports mutual TLS, and Cloudflare Access can add an extra authentication layer (free for up to 50 users).

### ngrok

**Free tier:** 1 tunnel, 1 GB/month bandwidth, 20,000 requests/month, ephemeral random domain (changes each restart), branded interstitial warning page, 4,000 req/min rate limit.

**WebSocket:** Supported, counted against HTTP request rate limits. Works for streaming but the 1 GB cap is restrictive.

**Latency:** ~8.8 Mbps benchmark — roughly 5x slower than Cloudflare Tunnel. Noticeable for streaming responses.

**Custom domain:** Requires paid plan ($8+/month).

**Windows service:** No built-in service installer. Needs NSSM or Task Scheduler wrapper.

**Verdict:** Great for quick demos and debugging (request inspection, traffic replay). Impractical for a permanent assistant due to bandwidth caps and ephemeral URLs on the free tier.

### Tailscale Funnel

**Free tier:** Up to 3 users, 100 devices. Funnel only works on ports 443, 8443, 10000. No custom domain — assigned `[device].[user].ts.net`.

**Latency:** Adds 10-80ms overhead. When direct P2P fails (common behind symmetric NAT), traffic routes through Tailscale's limited DERP relay fleet — throughput can drop to ~2 Mbps at distance. Self-hosted Peer Relays help but add complexity.

**WebSocket:** Supported via the underlying WireGuard tunnel. SSE works.

**Security:** Strongest of all options — true end-to-end encryption via WireGuard. No TLS termination at a third party. However, Funnel opens a port to the *entire internet* with no built-in auth layer. Combine with your own auth middleware.

**Windows service:** Tailscale itself runs as a native Windows service. The Funnel feature is a config toggle, not a separate service.

**Verdict:** Best for personal private access (VPN use case). Less suited for exposing a public-facing assistant because of port restrictions, no custom domain, and variable relay performance.

### localhost.run / serveo.net / bore

Simple SSH-based reverse tunnels. Minimal setup, but: no service mode, no persistence, no custom domains (free tier), no rate limiting but also no SLA. Serveo has been unreliable. These are prototyping tools only — unsuitable for a production assistant.

### Self-Hosted: frp / boringproxy

**frp** is the most mature self-hosted option (100k+ GitHub stars). Supports TCP, UDP, HTTP/HTTPS, QUIC, KCP. Requires a VPS. High performance. Complex multi-file TOML config.

**boringproxy** is easier (no config files, WebUI, REST API) but still in beta.

Both require a VPS ($4-6/month minimum), which cancels the cost advantage of Cloudflare's free tier. You gain full control over TLS termination and zero third-party data exposure.

---

## 2. Reverse Proxy on a VPS (the DIY approach)

Architecture: **VPS (Nginx/Caddy) + WireGuard tunnel -> Windows PC (Flask)**

| Component | Pros | Cons |
|---|---|---|
| **Nginx** | Battle-tested, rich ACL/rate-limiting, cheap VPS ($5/mo Hetzner) | Manual config, manual cert renewal |
| **Caddy** | Automatic HTTPS via Let's Encrypt, simpler config, HTTP/3 support | Less configurable, smaller ecosystem |
| **WireGuard** | Fastest VPN protocol, native Windows client, kernel-level efficiency | Requires routing setup; if VPS is far from user, extra latency |
| **Cloudflare Tunnel + Access** | No VPS needed, free, global CDN, SSO auth layer | TLS terminated at Cloudflare |

**Tradeoff:** The VPS approach gives you full control over TLS termination (end-to-end encryption on your own hardware) at the cost of monthly VPS fees and setup complexity. The Cloudflare approach is free and simpler but requires trusting Cloudflare with decrypted traffic.

---

## 3. Dynamic DNS (DDNS)

If the user has a public IP, DDNS maps a domain to a changing home IP. This avoids any tunnel middleman, but requires opening a firewall port — a security risk for a desktop with full system access.

| Service | Free Tier | Notes |
|---|---|---|
| **DuckDNS** | Was free, **shut down in 2025** without warning | Do not use |
| **Dynu** | 4 free hostnames, no ads, no 30-day confirmation | Best free alternative for DDNS-only use |
| **Cloudflare** | Free (requires own domain ~$8-12/yr) | Best if you already own a domain; API-based IP updates |
| **No-IP** | 3 hostnames, ads, requires 30-day email confirmation | Simple but maintenance burden |

**Recommendation:** If using Cloudflare Tunnel, you already own a domain and DNS is handled automatically. No separate DDNS needed. If going the VPS route, point your domain's A record to the VPS's static IP — again no DDNS needed. DDNS is only relevant for the "open a port on home router" approach, which is not recommended.

---

## 4. WebSocket and SSE Support

| Solution | WebSocket | SSE | Long-lived connections |
|---|---|---|---|
| Cloudflare Tunnel | Full support | Full support, no timeout | Supported (~100s default proxy timeout, configurable) |
| ngrok | Supported | Supported | Supported (2hr session limit on free) |
| Tailscale Funnel | Via WireGuard | Via WireGuard | Supported (no artificial limits) |
| frp (self-hosted) | Full | Full | Full (your VPS, your rules) |
| Nginx VPS | Full (needs config) | Full | Full |

For streaming LLM responses (SSE or streaming JSON), all major solutions work. Cloudflare Tunnel has a ~100-second default proxy read timeout that may need increasing for very long generations. This is configurable in the `config.yml` with `proxyTimeout: 0` for no timeout.

---

## 5. Windows Service Setup

### Flask as a Windows Service

**Recommended: NSSM (Non-Sucking Service Manager)**

```cmd
nssm install JarvisFlask "C:\path\to\venv\Scripts\python.exe" "run.py"
nssm set JarvisFlask directory "C:\path\to\project"
nssm set JarvisFlask Start SERVICE_AUTO_START
```

NSSM handles: auto-start on boot, automatic restart on crash, stdout/stderr logging (with rotation), no console window visible. Simpler than writing a native Windows Service in Python via pywin32.

Alternative: **WinSW** (Windows Service Wrapper) — XML-based config, GitHub-hosted. Comparable to NSSM but less widely documented for Python.

### Tunnel as a Windows Service

**Cloudflare Tunnel:** Built-in `cloudflared service install` registers a native Windows service with auto-start, automatic restart on failure (20s delay), event log integration. No wrapper needed.

**ngrok:** No built-in service support. Wrap with NSSM or Task Scheduler (run at logon).

**Tailscale:** Runs as a native Windows service already. No extra setup.

### Startup coordination

Both services should be set to `SERVICE_AUTO_START`. The Flask service should have a delayed start or the tunnel should retry until the Flask port is available. NSSM's restart-on-failure handles this naturally — the tunnel will restart until Flask is ready.

---

## 6. HTTPS/TLS Handling

| Solution | TLS Termination | Cert Management |
|---|---|---|
| **Cloudflare Tunnel** | At Cloudflare edge (auto) | Automatic, full cert lifecycle managed |
| **ngrok** | At ngrok edge (auto) | Automatic on paid plans; free gets ephemeral cert |
| **Tailscale Funnel** | At Tailscale edge (auto) | Automatic via LetsEncrypt |
| **Caddy (VPS)** | At your VPS | Automatic LetsEncrypt, managed cert renewal |
| **Nginx (VPS)** | At your VPS | Manual certbot or acme.sh setup |

For the JARVIS use case, the critical question is **where decryption happens**:

- **Cloudflare/ngrok/Tailscale Funnel**: A third party sees plaintext traffic between their edge and your PC. For a tool that transmits sensitive data (passwords, file contents, browser state), this matters.
- **VPS with Caddy/Nginx over WireGuard**: TLS terminates at your VPS, traffic between VPS and Windows PC is encrypted by WireGuard. You control all infrastructure.
- **Additional layer**: Regardless of tunnel choice, implement authentication *in your Flask app* (see section 9). The tunnel is transport security; auth is application security.

---

## 7. Latency and Bandwidth — Real-World Impact

| Solution | Typical Overhead | Max Throughput (free) | Notes |
|---|---|---|---|
| Cloudflare Tunnel | 15-45ms | ~46 Mbps | 200+ global PoPs, CDN-cached |
| ngrok | 30-80ms | ~8.8 Mbps | Slower, bandwidth-capped at 1 GB |
| Tailscale Funnel | 10-80ms (P2P) / 200-500ms (DERP relay) | ~2-100 Mbps | Highly variable; P2P best-case is fast, relay path is slow |
| VPS (Hetzner EU) + WireGuard | 2-8ms (proxy) + WireGuard overhead | VPS bandwidth (1 Gbps typical) | Lowest latency, best throughput, costs $5/mo |

For streaming LLM responses (token-by-token SSE), latency matters more than throughput. Cloudflare's global edge network provides good latency in most regions. A well-placed VPS is the best option. Tailscale Funnel via DERP relay is the worst — its throughput can drop below what's comfortable for real-time streaming.

---

## 8. Free vs Paid — Summary Table

| Feature | Cloudflare Tunnel (free) | ngrok (free) | Tailscale Funnel (free) | VPS + Caddy (paid) |
|---|---|---|---|---|
| Monthly cost | $0 (+ domain $8-12/yr) | $0 | $0 | $4-6/mo |
| Bandwidth | Unlimited | 1 GB | Unlimited | VPS-dependent (1+ TB) |
| Custom domain | Yes | No | No | Yes |
| Tunnels | Unlimited | 1 | 3 ports | Unlimited |
| WebSocket | Yes | Yes | Yes | Yes |
| Auth layer | Cloudflare Access (up to 50 users free) | No | No | DIY |
| Control of TLS | Third-party | Third-party | Third-party | Full |
| Auto-start (Windows) | Built-in service | NSSM needed | Built-in service | NSSM for tunnel + Flask |
| Rate limits | None practical | 20K req/mo, 1 GB | None | None |
| ToS restrictions | Media streaming restricted | None explicit | None | None |

---

## 9. Security Hardening — Critical for JARVIS

This is not optional. The JARVIS Flask UI has desktop-level access. A compromised web session is a compromised machine.

**Mandatory measures:**

1. **Authentication:** Every request must be authenticated. Options:
   - **Flask-Login** with session-based auth and a strong password
   - **Flask-HTTPAuth** (HTTP Basic Auth) over HTTPS — simpler but less flexible
   - **Token-based auth** (Flask-JWT-Extended) — best for programmatic/API access
   - **Cloudflare Access** as a pre-auth layer before traffic reaches your Flask app (free for up to 50 users, SSO/Google/GitHub login)

2. **Rate limiting:** Flask-Limiter to prevent brute-force attacks on login endpoints.

3. **CSRF protection:** Flask-WTF `CSRFProtect` if using cookie-based sessions. Not needed if using token-based auth (no cookies) or Cloudflare Access (auth happens before reaching Flask).

4. **Security headers:** Content-Security-Policy, X-Frame-Options (DENY), HSTS, X-Content-Type-Options via response headers.

5. **Network isolation:** Bind Flask to `127.0.0.1` (not `0.0.0.0`). Only the tunnel daemon (cloudflared/ngrok) should connect to localhost. The tunnel is the only vector in.

6. **Session management:** HttpOnly, Secure, SameSite=Lax cookies. Session timeout (e.g., 30 min of inactivity). Session regeneration on login.

7. **Least privilege:** The Flask app should run as a *limited user account*, not the primary desktop user. This limits damage if the web UI is compromised.

8. **Input validation:** All user input from the web UI must be validated. The `execute_command` and `file_manager` tools should remain server-side only (Claude API), not exposed as Flask endpoints unless absolutely needed and heavily sandboxed.

---

## 10. Recommendation for JARVIS

**Primary choice: Cloudflare Tunnel** (cloudflared)

Rationale:
- Free, unlimited bandwidth, fast global edge network
- Full WebSocket/SSE support for streaming LLM responses
- Built-in Windows service with auto-start and crash recovery
- Cloudflare Access layer adds SSO auth before traffic hits Flask
- ~20 minute setup: install cloudflared, authenticate, create tunnel, point domain, install service

**Security stack:**
- Cloudflare Tunnel for transport
- Cloudflare Access for pre-auth (SSO with Google/GitHub)
- Flask-HTTPAuth or Flask-Login for app-level auth (belt-and-suspenders)
- Flask-Limiter for brute-force protection
- Bind Flask to `127.0.0.1` only
- Run Flask under a restricted Windows user account
- Session timeout, HttpOnly cookies, HSTS headers

**Alternative (if self-hosting is preferred):**
- VPS ($5/mo Hetzner) running Caddy as reverse proxy with automatic LetsEncrypt
- WireGuard tunnel from VPS to Windows PC
- Flask behind NSSM as Windows service
- Same app-level security measures

**Not recommended:**
- Opening a port on the home router (DDNS approach) — too much attack surface for a tool with full system access
- ngrok free tier — too restrictive (1 GB, ephemeral domain, session limits)
- Tailscale Funnel — port-restricted, no custom domain, relay performance is unreliable
- SSH-based tunnels (localhost.run, serveo) — no persistence, no service mode, unreliable uptime

---

*Sources: Cloudflare Tunnel docs, ngrok pricing/limits, Tailscale documentation, NSSM project page, awesome-tunneling-tools GitHub, HN discussions on TLS-terminating proxies, Flask security best practices.*
