# Local Network Access for JARVIS (Flask Web UI)

Research summary for making the JARVIS Flask web interface accessible from phones, laptops, and tablets on the same home WiFi network.

---

## 1. Binding Flask to the Network

Flask's built-in server binds to `127.0.0.1` (localhost) by default, which is only reachable from the same machine. To allow LAN access, you must bind to `0.0.0.0`, which tells the OS to listen on all network interfaces (WiFi, Ethernet, VPN, etc.).

```python
# Flask dev server (fine for LAN, not for internet-facing production)
app.run(host="0.0.0.0", port=5000, debug=True)

# Waitress (recommended on Windows for anything beyond quick tests)
from waitress import serve
serve(app, host="0.0.0.0", port=5000, threads=8)
```

**Security note:** Never bind to `0.0.0.0` with `debug=True` for extended periods -- the Werkzeug debugger console can be accessed by anyone on your network and allows arbitrary code execution. For a short test it is acceptable, but switch to Waitress (which has no debug console) for ongoing use.

**Why Waitress on Windows:** Gunicorn does not work on Windows. uWSGI is painful to compile. Waitress is pure Python, pip-installable, and purpose-built for Windows production.

> **Key point:** You cannot type `http://0.0.0.0:5000` into a browser. `0.0.0.0` is a binding directive only. Clients connect using the machine's actual IP (e.g., `http://192.168.1.50:5000`).

---

## 2. Windows Firewall

Even with Flask bound to `0.0.0.0`, Windows Defender Firewall will block inbound connections from other devices by default. You must add a rule allowing TCP port 5000 (or whichever port you use).

**PowerShell (run as Administrator):**

```powershell
New-NetFirewallRule -DisplayName "JARVIS Web UI" `
  -Direction Inbound -Protocol TCP -LocalPort 5000 `
  -Action Allow -Profile Private -RemoteAddress LocalSubnet
```

This creates a rule that:
- Allows **only** traffic from the local subnet (e.g., `192.168.1.0/24`).
- Applies **only** when the network profile is set to **Private** (not Public).
- Is safe on coffee-shop WiFi: if Windows classifies the network as Public, the rule does not apply.

**Equivalent netsh command:**

```
netsh advfirewall firewall add rule name="JARVIS Web UI" `
  dir=in action=allow protocol=TCP localport=5000 remoteip=localsubnet profile=private
```

**Verification:**

```powershell
Get-NetFirewallRule -DisplayName "JARVIS Web UI" | Get-NetFirewallAddressFilter
```

**Important:** Make sure your WiFi network is set to "Private" in Windows Settings (Network & Internet > WiFi > click network name > change to Private). A Public profile blocks most inbound traffic regardless of firewall rules.

---

## 3. Finding the Local IP

Your machine's local IP can be retrieved in several ways.

**Command line (`ipconfig`):**
```
ipconfig | findstr /i "IPv4"
```
Look for the address in the `192.168.x.x` or `10.x.x.x` range under your active WiFi adapter.

**Python (reliable cross-platform method):**

```python
import socket

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))  # doesn't actually send data
        return s.getsockname()[0]
    finally:
        s.close()
```

This works by creating a UDP socket and "connecting" to an external IP -- the OS picks the best local interface for the route and returns that interface's IP. No actual network traffic is sent.

**DHCP vs Static IP:** Most home routers use DHCP, meaning the IP can change when the machine reboots or the DHCP lease expires. Options:
- **Router DHCP reservation** (best): Assign a fixed IP by MAC address in the router admin panel. The IP stays constant without manual Windows configuration.
- **Static IP in Windows**: Configure manually in network adapter settings, but this is brittle if you change networks.
- **No action -- just adapt**: Print the current IP in the JARVIS console at startup. Simple and works for most home setups.

**Recommendation:** Display the local IP in the JARVIS startup banner alongside the port. Also print a QR code (via the `qrcode` Python library) that encodes the full URL -- mobile users can scan it instantly.

---

## 4. mDNS / Local Hostname

Instead of typing `192.168.1.50:5000` every time, you can reach your machine by a `.local` hostname (e.g., `jarvis.local:5000`).

**Windows 10 (build 1709+) and Windows 11** include built-in mDNS support -- your machine's hostname is already advertised as `<hostname>.local` on the network. In most cases, no additional software is needed.

To check: find your machine's hostname with `hostname` in a terminal, then try `ping <hostname>.local` from another device.

If mDNS is not working or you want a custom name:
- **Router DNS reservation:** Assign a friendly name in the router's DHCP settings (some routers support this).
- **Hosts file on each client:** Add `192.168.1.50 jarvis` to `C:\Windows\System32\drivers\etc\hosts` on each accessing device -- manual but reliable.
- **Bonjour Print Services:** Apple's standalone mDNS installer for Windows (free, no iTunes needed).
- **Koi mdns:** A lightweight Rust-based mDNS daemon for Windows (no dependencies, installable as a Windows service).

**Practical note:** On a home network with few devices, using the IP directly is simpler and more reliable than mDNS. Only invest in mDNS if you find yourself typing the IP frequently.

---

## 5. Access from Mobile / Tablet

Once Flask is bound to `0.0.0.0` and the firewall is configured, opening `http://192.168.1.50:5000` in a mobile browser should work immediately. No port forwarding is needed -- that is only for WAN (internet) access.

**Gotchas:**
- **Router AP Isolation / Client Isolation:** Some routers block device-to-device communication on WiFi. Check your router admin panel under Wireless Settings or Advanced Security for "AP Isolation," "Client Isolation," or "Device Isolation." Disable it if enabled.
- **Mixed content warnings:** If the page loads `http://` resources from an `https://` origin, mobile browsers block them. Since you are on plain HTTP, this is not an issue -- just make sure you do not proxy through an HTTPS-terminating service.
- **PWA installation:** Service Workers (required for installable PWAs) only work on secure origins (HTTPS) or `localhost`. Over LAN on plain HTTP, `navigator.serviceWorker` will silently fail. Solutions:
  - Use `mkcert` to generate a trusted certificate for your local IP and configure Flask/Waitress with SSL.
  - Use `ngrok` to create a public HTTPS tunnel (overkill for LAN).
  - Accept that PWA features will not work and use the page as a regular browser tab.
  - The W3C has an open issue (ServiceWorker #1668) requesting that RFC 1918 private IPs be treated as secure contexts, but no browser has implemented this yet.

---

## 6. LAN Security Basics

When JARVIS is accessible on the LAN, **anyone connected to your WiFi can reach the web UI** -- that includes guests, compromised IoT devices, or neighbours who know your WiFi password.

**What is reasonable for a first step:**

| Protection | Difficulty | What It Does |
|---|---|---|
| **Subnet-restricted firewall rule** | Trivial (one command) | Limits access to your local subnet only. Already covered in section 2. |
| **Simple password gate** | Easy | A login page with a hardcoded password. Use `flask-httpauth` (one decorator per route, or a `before_request` hook). |
| **Warning banner** | Very easy | A footer or modal: "Authorized access only. All activity may be logged." |
| **IP whitelist** | Moderate | Flask middleware that checks the requesting IP against a list of known devices. |

**Recommendation for the first version:** Subnet-restricted firewall + a simple shared password (stored in `jarvis_memory.json` or an environment variable) checked via `flask-httpauth`. This keeps out casual visitors while remaining easy to use. Full OAuth or user management is unnecessary until you want per-user personalisation or internet-facing access.

**Unencrypted HTTP on LAN:** A passive attacker on the same WiFi (e.g., using Wireshark or airodump-ng) can see all traffic, including passwords. For a voice assistant that reads and writes local files and runs system commands, this is significant. Adding a self-signed HTTPS certificate via `mkcert` is a worthwhile upgrade and takes about 5 minutes.

---

## 7. Performance on WiFi

Typical round-trip latency on a home WiFi network is **2-10 ms** (vs <1 ms for localhost and 20-100 ms for internet). This is negligible for web UI interactions.

**SSE (Server-Sent Events) over WiFi:** If JARVIS streams responses to the browser via SSE, WiFi latency is not a concern. The real risk is **proxy buffering**: HTTPS automatically defeats proxy buffering. Over plain HTTP, some ISP-grade routers or antivirus software may buffer the SSE stream. If streaming feels laggy or delayed, enabling HTTPS is the fix.

WiFi bandwidth (even 802.11n, let alone WiFi 6/6E) is far more than sufficient for a real-time chat-style UI.

---

## 8. Troubleshooting

**Quick checklist when LAN access does not work:**

| Symptom | Likely Cause | Fix |
|---|---|---|
| Works on localhost, not from phone | Flask not bound to `0.0.0.0` | Add `host="0.0.0.0"` |
| "Connection refused" from phone | Firewall blocking port | Add the firewall rule (section 2) |
| "Connection timed out" from phone | Router AP Isolation | Disable in router settings |
| Works on Ethernet, not on WiFi | AP Isolation or Profile | Check router + set WiFi to Private |
| IP changed after reboot | DHCP lease expired | Set DHCP reservation in router |
| mDNS name not resolving | LLMNR used instead | Wait longer or use IP directly |
| Flask debugger visible from phone | `debug=True` on `0.0.0.0` | Switch to Waitress |
| Port 5000 already in use | Another service on 5000 | Change port or kill the other process |
| "ERR_CERT_AUTHORITY_INVALID" | Self-signed cert not trusted | Install cert on client device or use `mkcert` |
| SSE stream stalls after a while | Proxy buffering | Switch to HTTPS |

**Testing from another device:** On the phone/laptop, open a terminal and run:
```bash
nc -zv 192.168.1.50 5000   # macOS/Linux
# or
Test-NetConnection 192.168.1.50 -Port 5000   # PowerShell
```
If the port is reachable but the page does not load, the issue is in Flask or your app code, not the network.

---

## Summary of Recommended Setup

1. **Install Waitress:** `pip install waitress`
2. **Serve on `0.0.0.0:5000`:** `serve(app, host="0.0.0.0", port=5000)`
3. **Add firewall rule:** PowerShell command from section 2
4. **Set WiFi to Private:** Windows network settings
5. **Print the IP on startup:** `get_local_ip()` from section 3
6. **Add simple password gate:** `flask-httpauth` with a single shared password
7. **(Optional) Add HTTPS:** `mkcert` for a self-signed cert
8. **(Optional) Disable AP Isolation:** Router admin panel

This setup takes under 15 minutes and gives you a working, reasonably secure LAN-accessible JARVIS web interface.
