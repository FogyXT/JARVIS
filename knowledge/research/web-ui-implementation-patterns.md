# AI Chat Web UI -- Implementation Patterns Research

Research conducted June 2026 for the JARVIS Flask web UI project. Covers ten architectural areas relevant to a single-page AI chat application with a particle background and ~60KB CSS footprint.

---

## 1. Streaming Text Rendering

Rendering LLM token streams is the highest-frequency UI operation and the most common source of jank. Three layered concerns exist:

**DOM update strategy.** For plain text, `element.append(chunk)` is the recommended approach -- it appends a text node without triggering a full innerHTML parse or rebuilding the DOM subtree. For markdown, the naive innerHTML re-parse on every chunk is wasteful; incremental AST-based rendering is preferred. Libraries like `appemd` (npm) use `@lezer/markdown` to build an incremental AST, tracking changes at the block level and applying minimal DOM patches. A simpler alternative: batch incoming tokens with `requestAnimationFrame` (typically every 50-100ms) and replace the content in a single DOM write, trading a little latency for smooth frames.

**Markdown-in-progress rendering.** Streaming markdown produces temporarily invalid syntax (e.g., a partially typed `**bold**`). The renderer should gracefully degrade -- treat open tokens as plain text until they close, or render them with a dimmed/italic style to indicate "in progress." Chrome's developer documentation recommends a dedicated streaming markdown parser (such as `streaming-markdown` on npm) that understands partial tokens.

**Cursor and blink effects.** A blinking caret at the end of the streaming text signals liveness. The simplest implementation is a CSS `@keyframes blink` with 50% opacity toggling, applied to a `::after` pseudo-element. More visually refined: a subtle pulsing vertical bar that fades as text catches up.

---

## 2. Performance for Long Conversations

A chat with 100+ messages of multi-line markdown can easily exceed 10,000 DOM nodes. Two approaches dominate:

**Virtual scrolling (DOM recycling).** Only the visible messages plus a small buffer (3-5 above/below viewport) are in the DOM. As the user scrolls, off-screen elements are recycled (cleared and repositioned) rather than created or destroyed. The core algorithm: calculate the visible slice from `scrollTop`, set `padding-top` to simulate scrolled-off items, and reuse DOM elements from a pool. For variable-height messages (essential for chat), the implementation must measure each item after render and store its height in a lookup table for accurate scroll position calculations. Vanilla JS libraries like `virtual-scroller` and `vanilla-recycler-view` provide this without framework dependency. Expected reduction: ~80-95% fewer DOM nodes.

**Scroll anchoring.** When new content arrives (streaming tokens) or when images/media load asynchronously, the visible position should not jump. The algorithm: find the topmost visible element, store its offset from the viewport top before mutation, then adjust `scrollTop` after mutation to maintain visual position.

**Message pagination.** For sessions exceeding 500+ messages, paginate history server-side and load in batches of 50-100. The virtual scroller can request older messages via the API when the user scrolls past the current window.

---

## 3. Markdown Rendering Libraries

Four libraries dominate the JavaScript markdown landscape, with trade-offs in speed, security, and extensibility:

**marked.js** (~30KB, very fast). Recursive-descent parser that outputs HTML directly. Simple API, full CommonMark and GFM support. Best for straightforward rendering where minimal configuration is desired. However, it has a smaller plugin ecosystem and limited extensibility for custom syntax.

**markdown-it** (~40KB, fast). Token-pipeline architecture that parses to intermediate tokens then renders via rule functions. Huge plugin ecosystem (150+ plugins for emoji, footnotes, containers, mermaid diagrams, math/KaTeX). Best for applications needing custom syntax or rich extensions. Slightly slower than marked on large files in benchmarks but offers far more control.

**showdown** (~50KB, slowest). Regex-based string replacement parser. Simple to extend with regex filters but fragile with nested markdown structures. Does not support CommonMark. Its performance trails significantly on large documents. Best avoided for new projects.

**micromark** (very small, very fast). The parser underlying `remark`. Extremely fast (more than 2x marked on some benchmarks) and fully CommonMark-compliant. Designed as a minimal foundation -- you build rendering on top. Best for performance-critical pipelines where full GFM or plugins are not needed.

**Security note:** None of these libraries sanitize HTML output by default. Every render path must be paired with `DOMPurify.sanitize()` before inserting into the DOM. For LLM output, sanitize the *concatenated* final output, not individual chunks, to catch payloads split across token boundaries.

---

## 4. Real-Time Communication: SSE vs WebSocket

**SSE (Server-Sent Events)** is the recommended default for AI chat streaming. It rides over standard HTTP (`text/event-stream`), works through every CDN and proxy, and the browser `EventSource` API provides automatic reconnection with `Last-Event-ID` headers at no implementation cost. The server sends a `retry:` field to control the reconnection interval (typically 3 seconds). For streaming LLM responses where the flow is unidirectional (server pushes tokens to client), SSE is architecturally simpler and more reliable than WebSocket.

**WebSocket** becomes necessary when bidirectional communication is required -- for example, mid-stream interruptions ("stop generating"), tool call approvals sent back to the server while a response is in progress, or multi-agent coordination. WebSocket has no built-in reconnection; you must implement exponential backoff manually (e.g., `min(1000 * 2^attempt, 30000)` ms). It also requires special proxy/CDN configuration and does not benefit from HTTP/2 multiplexing.

**The emerging durable session pattern** layers persistent state (stored server-side) on top of WebSocket transport, enabling offset-based replay -- the client can reconnect and resume from token N rather than restarting the generation. This is the most resilient pattern for long-running agent tasks.

**Cancellation.** Whether using SSE or WebSocket, the client should use `AbortController` to abort in-flight requests when the user sends a new message, preventing stale responses.

---

## 5. Desktop-Quality Web UI (PWA)

A Flask-based single-page app can achieve desktop-level integration through Progressive Web App patterns:

**Install prompt.** Capture the `beforeinstallprompt` event, call `preventDefault()` to suppress the browser's automatic banner, and surface a custom install button. Check `navigator.getInstalledRelatedApps()` to hide the button if already installed. The manifest must declare `display: standalone`, provide icons at 192x192 and 512x512 (with maskable variants), and set an appropriate scope.

**Offline support.** A service worker using a hybrid caching strategy: precache the app shell (HTML/CSS/JS), use cache-first for static assets, and network-first for API routes with a 3-second timeout falling back to a cached offline page. Workbox remains the production standard for managing these strategies declaratively.

**Window controls overlay.** For desktop PWA installs, the `window-controls-overlay` display override lets CSS extend into the title bar region (`titlebar-area-x`, `titlebar-area-y`, etc.), creating a frameless native look similar to Electron. The drag region is defined with `-webkit-app-region: drag` on the top bar.

**System tray integration** is not available in standard PWAs and requires a native wrapper (Tauri or Electron) that exposes a system tray API to the web renderer via a bridge.

---

## 6. Animation & Micro-Interactions

All animations should target CSS `transform` and `opacity` only (GPU-composited properties) and respect `prefers-reduced-motion`.

**Message appear/disappear.** A `fadeIn` keyframe: opacity 0 to 1, translateY 10px to 0, over 300ms with `ease-out` cubic timing. Messages are staggered by 50-100ms delay per message for sequential appearance. Disappear uses reverse with 200ms.

**Typing dots animation.** Three dots with staggered animation delays (0s, 0.2s, 0.4s) using a 1.2s cycle. Each dot bounces vertically ~4px with opacity pulsing. CSS-only, no JavaScript.

**Smooth scroll to bottom.** On new message arrival, animate `container.scrollTop` to `container.scrollHeight` with a 300ms CSS `scroll-behavior: smooth`. If the user has scrolled up (not at bottom), show a "scroll to bottom" floating button instead of stealing their position.

**Theme transitions.** CSS custom properties make theme switching trivial: change `--bg-color`, `--text-color`, `--bubble-user`, `--bubble-ai` on the `:root` or a wrapper element, and every property transition applies automatically with `transition: background-color 350ms ease, color 350ms ease`.

---

## 7. Copy/Paste & Clipboard

**Copy code button.** Every code block should render with a "copy" button (top-right corner, icon-only). On click: `navigator.clipboard.writeText(codeContent)`. Provide visual feedback -- change the icon to a checkmark for 1.5 seconds, then revert. Wrap in try/catch for `NotAllowedError` (user gesture required).

**Copy entire message.** A hover-reveal button on each assistant message copies the full rendered text via `navigator.clipboard.writeText()`. Strip markdown formatting before copying (or copy the raw markdown source, depending on preference).

**Paste images from clipboard.** Use the Async Clipboard API: `navigator.clipboard.read()` returns a `ClipboardItem` array. Check for image MIME types and create a `Blob` for upload. This is gated by the `clipboard-read` permission and requires a user gesture (paste event or button click).

**Drag-and-drop file upload.** The standard HTML5 Drag and Drop API (`dragenter`, `dragover`, `drop` on the message input area) handles files via `event.dataTransfer.files`. A drop zone overlay with visual feedback (border highlight, "drop here" text) should appear during drag. For images, generate a thumbnail preview before upload.

---

## 8. Voice Integration in Web UI

The browser provides all necessary primitives through the MediaStream Recording API and Web Audio API, requiring no external libraries.

**Recording.** `navigator.mediaDevices.getUserMedia({ audio: true })` obtains the microphone stream. A `MediaRecorder` instance captures audio chunks (`ondataavailable`) which are collected into a `Blob` and sent to the server for transcription (e.g., Whisper API or Google Speech). The `dataavailable` event fires every `timeslice` ms (recommended: 250ms for real-time feedback).

**Audio visualization during recording.** Connect the stream to a Web Audio pipeline: `AudioContext` -> `createMediaStreamSource(stream)` -> `AnalyserNode`. The analyser provides `getByteFrequencyData()` for a frequency-domain VU meter or `getByteTimeDomainData()` for a waveform. Run the visualization loop via `requestAnimationFrame`. Canvas-based rendering is the standard approach, but CSS-based bar meters (using `transform: scaleY()` on div bars) work well for simpler VU meters.

**Silence detection.** The `AnalyserNode` can also detect silence: set `analyser.minDecibels = -45` as a threshold, then check if `getByteFrequencyData()` returns all zeros over a sliding window of ~1.5 seconds. When silence exceeds the threshold, automatically stop recording. This removes the need for a manual "stop" button.

**Speech-to-text alternatives.** The Web Speech API (`SpeechRecognition`) provides built-in browser transcription but has significant limitations: Chrome-only, no language switching mid-stream, and no punctuation. For production quality, upload audio to a server-side STT engine (Whisper, Google Cloud Speech-to-Text).

---

## 9. State Management

For a single-page chat app without a JavaScript framework, a custom state management layer is lightweight and sufficient.

**Session persistence.** IndexedDB (via the Dexie.js wrapper for ergonomic queries) is the recommended storage for chat messages and conversation threads. localStorage should be reserved for lightweight preferences (theme, language, last-selected thread ID). IndexedDB handles large datasets (megabytes of message content), supports structured data queries, and survives storage pressure better than localStorage.

**Optimistic updates.** When the user sends a message, immediately add it to the UI state (and IndexedDB) with a `pending` status flag. When the API responds, update the message status (e.g., from `pending` to `sent` or `failed`). This eliminates perceived latency.

**Multi-tab synchronization.** Use the BroadcastChannel API to propagate state changes across open tabs. When one tab sends a message or receives a response, broadcast a `{ type: "new-message", threadId, message }` event. Other tabs listen and update their IndexedDB-local state accordingly. BroadcastChannel is simpler than SharedWorker and covers all modern browsers. Fall back to the `storage` event for older browsers (limited to localStorage changes only).

**Conflict resolution.** For local-first architectures, use an immutable event model (each message has a unique ID and cannot be modified, only appended). This eliminates edit conflicts. For more complex scenarios, last-writer-wins with server timestamps is the simplest viable approach.

---

## 10. Security

**XSS prevention in markdown rendering.** This is the single most critical security concern in an AI chat UI. The rendering pipeline must be: (1) parse markdown to HTML via a safe parser (marked.js or markdown-it with `html: false`), (2) sanitize the HTML output through DOMPurify before inserting into the DOM. DOMPurify's whitelist-based approach strips all non-allowlisted tags and attributes, including event handlers (`onclick`, `onerror`, `onload`), `javascript:` URLs, and `<script>` tags. Sanitize the concatenated final output, not individual stream chunks, to catch payloads split across token boundaries.

**CSP headers.** Content Security Policy provides a critical second layer of defense. Minimum configuration: `default-src 'self'`, `script-src 'self'`, `style-src 'self' 'unsafe-inline'` (for dynamic styles), `img-src 'self' data: https:`, `object-src 'none'`, `base-uri 'self'`. This prevents execution of injected scripts even if sanitization fails. Enable CSP violation reporting via `report-uri` or `report-to` for monitoring.

**Sanitizing user input.** User-provided text (message input) should be HTML-escaped before rendering in the UI. Never insert raw user text into the DOM via `innerHTML`. The escape is typically handled by the markdown parser when paired with DOMPurify, but plain-text fallback paths must also escape.

**Secure file upload handling.** Validate file type on both client (MIME type check) and server (magic bytes inspection). Reject executable files and scripts. Set a maximum file size (e.g., 10MB for images, 50MB for audio). Store uploaded files outside the web root or serve them through a handler that sets `Content-Disposition: attachment` and `X-Content-Type-Options: nosniff`.

**Rate limiting.** API endpoints should implement rate limiting (per IP and per session) to prevent abuse. For WebSocket/SSE endpoints, limit concurrent connections per client.

---

## Sources

- Chrome Developers -- "Best Practices to Render Streamed LLM Responses" (January 2025)
- DataStax -- "How Using Fetch with the Streams API Gets You Faster UX with GenAI Apps" (August 2025)
- Hivenet -- "Streaming for LLM Apps: SSE vs WebSockets" (October 2025)
- WebSocket.org -- "WebSockets and AI: Why LLMs Are Moving Beyond SSE"
- Railway Guides -- "Choose Between SSE and WebSockets"
- GotharTech -- "Ship the App, Keep the Web -- A 2025 PWA Field Guide"
- W3C -- "Clipboard API and Events" (2025 Working Draft)
- MDN Web Docs -- "Using the MediaStream Recording API"
- Smashing Magazine -- "Audio Visualization with JavaScript and GSAP"
- npm-compare -- "markdown-it vs marked vs micromark vs remark vs showdown"
- OWASP XSS Prevention Cheat Sheet
- forta.chat -- "Local-First Architecture" (pocketnetteam/vtchat)
