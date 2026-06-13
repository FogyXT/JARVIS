# Advanced Vanilla JavaScript Patterns for Rich SPAs

> Research compiled June 2026. Focus: building single-page applications without React, Vue, or Angular. Concepts and architecture over raw code.

---

## 1. SPA Architecture: Three Paths to Components

There are three viable component approaches, each with trade-offs:

**Web Components (Custom Elements + Shadow DOM)** -- The closest to a "standard" component model. Shadow DOM gives style and markup isolation. Lifecycle hooks (`connectedCallback`, `attributeChangedCallback`) map well to framework thinking. The cost: ceremony (every component is a class extending `HTMLElement`), limited reactivity (no built-in state-to-DOM binding), and Shadow DOM can complicate global styling and accessibility.

**Pure JS Classes** -- Plain constructor functions that own a DOM subtree. Simple, testable, no magic. Each component manages its own `render()` method and internal state. Lighter than Web Components but requires discipline around teardown and memory management.

**Template Literals** -- Functions returning interpolated HTML strings. The entire UI is derived from data -- "re-render" means replacing `innerHTML` (safely, with the Sanitizer API). Works well with reactive stores; the mental model is essentially React's functional approach without virtual DOM diffing.

### Reactivity Without Virtual DOM

Three competing patterns exist:

- **Proxy-based** -- Wrap state objects in `Proxy` with a `set` trap that triggers re-render. Simple and expressive. The trap fires on any property change without explicit wiring. Downside: the proxy returns the proxied object, so nested objects need their own proxies.

- **Observable / Signal pattern** -- Extend `EventTarget` to create signal objects where `.value` getters auto-track dependents and `.value` setters dispatch notifications. This is the conceptual foundation of the TC39 Signals proposal (currently Stage 1) and the mental model behind SolidJS. Fine-grained -- only dependents re-render on change.

- **PubSub (EventTarget)** -- The native `EventTarget` class doubles as a pub/sub bus. `new EventTarget()` gives you `addEventListener` and `dispatchEvent` with zero dependencies. Best for cross-component messaging rather than fine-grained reactive state.

### Routing: History API vs Navigation API

The **History API** (`pushState` + `popstate`) is the established approach. A router intercepts link clicks, calls `pushState` to update the URL, and renders the matching view. `popstate` handles back/forward. It works but requires manual interception of every navigation type.

The **Navigation API** reached Baseline in January 2026 (Chrome, Edge, Firefox 147+, Safari 26.2+). It unifies all navigation -- links, form submissions, programmatic, back/forward -- into a single `navigate` event with an `intercept()` method. The router gets a `navigation.entries()` list of the full history stack and can `traverseTo(key)` to jump to specific entries. This is the future of SPA routing. For now, feature-detect and fall back to the History API.

---

## 2. State Management Patterns

**EventEmitter / PubSub** -- A minimal event bus built on `EventTarget` handles cross-component communication without coupling. Components emit domain events (`user:login`, `data:loaded`) and other components subscribe as needed.

**Finite State Machines** -- Complex UI flows (multi-step forms, media playback, WebSocket connections) benefit from formal state machine modeling. Define states, transitions, and guards explicitly. Even a lightweight implementation (no XState dependency) prevents impossible states and makes edge cases visible.

**Immutable Updates** -- `structuredClone()` (native, available in all modern browsers) deep-clones state snapshots for predictable diffing. Combined with Proxy-based stores, this gives undo/redo and time-travel debugging without middleware.

**IndexedDB for Persistence** -- Browsers ship with a full NoSQL database. Wrap IndexedDB in a thin Promise-based abstraction for schema-based persistent storage. Works for offline-first state, large datasets, and structured data that overflows `localStorage`'s 5MB limit.

**Stale-While-Revalidate (SWR)** -- Show cached data immediately, fetch fresh data in the background, update when the fetch completes. Implementable with IndexedDB cache + a `fetch` wrapper. Essential for perceived performance.

---

## 3. DOM Performance

**DocumentFragment batching** -- Build DOM subtrees in an off-screen `DocumentFragment`, then append once. Triggers a single reflow instead of one per child node.

**requestAnimationFrame scheduling** -- Throttle layout-sensitive operations (scroll handlers, resize callbacks) with `requestAnimationFrame` so they execute before the next paint, not in between paint cycles where they'd trigger layout thrashing.

**IntersectionObserver** -- Replace scroll-event-based lazy loading with `IntersectionObserver`. Configure `rootMargin` to preload content before it enters the viewport. One observer can watch hundreds of targets efficiently. Use `unobserve()` after the element is loaded to prevent memory leaks.

**ResizeObserver** -- Replace `window.resize` + `getBoundingClientRect` hacks with `ResizeObserver`. Fires when any observed element changes size. Essential for responsive components, virtualized lists that adapt to container size, and chart/dashboard layouts.

**MutationObserver** -- Use sparingly. Best for library interop (detecting DOM changes from third-party scripts) and for custom elements that need to react to attribute changes in environments where `attributeChangedCallback` is insufficient.

**Virtual Scrolling** -- Render only visible rows (plus a buffer) in an `overflow:auto` container. Fixed-height rows are simplest: calculate `startIndex` from `scrollTop / rowHeight`, render a slice, and maintain a spacer div for the correct scrollbar size. Variable-height items need pre-computed cumulative offsets and binary search for fast index lookup. Add a buffer of 5-10 extra items above/below the viewport to prevent blanks during fast scrolling. Beyond 100K rows, consider recycling DOM nodes (pooling) instead of recreating them on every render.

---

## 4. Async Patterns

**AbortController** -- The canonical cancellation primitive. Pass `signal` to `fetch()`, event listeners, and streams. Calling `controller.abort()` rejects the promise with `AbortError`. Essential for: cancelling stale requests when the user navigates away, aborting long-polling on component unmount, and clean teardown in Web Workers.

**Promise Pooling / Limiting** -- Batch concurrent async operations (e.g., image uploads, API calls) with a fixed-size pool. Implement a scheduler that tracks in-flight promises and queues excess tasks, dequeuing when a slot opens. Prevents overwhelming the network connection pool or rate limiter.

**Retry with Exponential Backoff** -- Wrap fetch in a retry loop that waits `2^n * baseDelay` between attempts (plus jitter to avoid thundering herd). Max retries of 3-5 is typical. Only retry on server errors (5xx) and network failures, not 4xx client errors.

**Streaming Fetch (ReadableStream)** -- `response.body.getReader()` returns a `ReadableStream` for processing chunks as they arrive. Use `for await...of` with a streaming decoder for LLM-style token-by-token output. Critical for long-running responses where the user should see progress.

**Web Workers** -- Offload CPU-heavy work (parsing large files, image processing, data transformation) to a background thread. Workers communicate via `postMessage()` (structured clone). For ergonomics, wrap in a Promise-based RPC layer. Workers can also use `BroadcastChannel` to talk to other tabs directly.

---

## 5. Error Resilience

**Error Boundaries (Vanilla Pattern)** -- Wrap each major UI region in a `try/catch` during render. On error, render a fallback UI for that region instead of crashing the whole page. Log the error context (component name, state snapshot) to a buffer. This mirrors the React error boundary pattern using simple DOM containment.

**Global Crash Reporting** -- `window.onerror` catches unhandled exceptions, `window.onunhandledrejection` catches unhandled promise rejections. Both should serialize error stacks and application state, then POST to a logging endpoint (with `fetch(..., { keepalive: true })` to survive page unload).

**Offline Queue** -- Intercept fetch failures, serialize the failed request (method, URL, body, headers) to IndexedDB, and replay when `navigator.onLine` transitions from `false` to `true` (listen for the `online` event). Display a queue count to the user and allow cancellation.

**Service Worker Lifecycle** -- The SW goes through: installing -> installed (waiting) -> activating -> activated (controlling pages). Use `self.skipWaiting()` on install and `clients.claim()` on activate to take control immediately. Cache strategies: cache-first for static assets, network-first for API responses, stale-while-revalidate for content that updates gradually. Register a `message` handler so the page can instruct the SW to clear caches or skip waiting.

---

## 6. Event Architecture

**Event Delegation at Scale** -- Attach one listener per event type on a stable ancestor (or `document`). Use `event.target.matches(selector)` or the newer `event.target.closest(selector)` to identify the target. One listener handles all current and future matching children. A single-page delegation map (`click -> { '.open-modal': openModal, '.delete-item': deleteItem }`) keeps dispatch logic centralised.

**Custom Events for Cross-Component Communication** -- `new CustomEvent('app:notify', { detail: {...}, bubbles: true, composed: true })`. Custom events decouple producers from consumers. Use a naming convention like `namespace:event` to avoid collisions. Components expose their public API via events, not direct method calls.

**Passive Event Listeners** -- For `touchstart`, `touchmove`, `wheel`, and `scroll`, add `{ passive: true }`. This tells the browser you will NOT call `preventDefault()`, allowing it to optimise scrolling on the compositor thread without waiting for your handler. Modern browsers default touch events to passive, but explicit is better.

**Debounce / Throttle** -- Debounce (executes after a quiet period) for autocomplete search, resize end, and form validation on input. Throttle (executes at most once per interval) for scroll position tracking and progress events. Both are ~10-line functions using `setTimeout` and timestamp comparison.

**Pointer Events** -- Use `pointerdown/pointermove/pointerup` instead of separate mouse and touch handlers. `pointerevents` unify mouse, touch, and stylus into a single API with `pointerType` for differentiation. Set `touch-action: none` on draggable elements to prevent the browser from competing with your gesture handling.

---

## 7. Module Organization

**ES Modules** -- Native `import`/`export` work in all modern browsers without a bundler. Use `<script type="module" src="index.js">` as the entry point. Modules are deferred by default (no need for `defer` attribute). Export a public API, keep internals private.

**Dynamic Import** -- `import('./routes/dashboard.js')` returns a promise of the module namespace. Load route-level code on demand, triggered by the router. Use for: route components, heavy third-party libraries (charting, markdown parsers), and "show more" sections.

**Import Maps** -- `<script type="importmap">` maps bare specifiers to URLs, enabling npm-style imports (`import _ from 'lodash'`) without a bundler. Combine with an import map shim (`es-module-shims`) for older browsers.

**Code Splitting Without a Bundler** -- Structure the app so each route, modal, and "heavy" component is its own module file. The router calls `import()` only when the route activates. This is the simplest and most effective performance optimisation -- no bundler config needed.

**Dependency Injection (Vanilla Style)** -- Import a registry object that maps interface names to implementations. Modules import the registry, not the concrete dependency. Swap implementations for testing or feature flags by changing the registry entry. No decorators, no containers -- just object maps and factory functions.

---

## 8. Browser APIs You Should Use

| API | Use Case | Notes |
|---|---|---|
| **IntersectionObserver** | Lazy loading, infinite scroll, animation triggers | Single observer, many targets. `rootMargin` preloads before visibility. |
| **MutationObserver** | Interop with non-JS frameworks, DOM change detection | High overhead. Use sparingly. Prefer custom elements when possible. |
| **ResizeObserver** | Responsive containers, chart resizing, virtual scroll adaptivity | Fires per-element, not just window-level. |
| **BroadcastChannel** | Multi-tab sync (auth state, preferences, cache invalidation) | Same-origin only. No persistence. Use with IndexedDB for cross-tab state. |
| **Page Visibility API** (`document.visibilityState`) | Pause/resume animations, throttling when tab is backgrounded, analytics heartbeat | Reduces CPU/battery waste. Critical for background-tab performance. |
| **Navigation API** | SPA routing (successor to History API) | Baseline January 2026. Feature-detect and fall back to History API. |
| **Sanitizer API** (`Element.setHTML()`) | Safe HTML injection without DOMPurify | Not yet cross-browser stable. Use with a polyfill or Jitbit HtmlSanitizer for production. |
| **AbortController** | Cancelling fetch, streams, event listeners | The universal cancellation primitive in modern JS. |
| **structuredClone()** | Deep cloning state for immutable updates | Native, fast, handles circular references. Replaces `JSON.parse(JSON.stringify(obj))` hacks. |

---

## Architectural Philosophy

The overarching theme across all eight areas is: **browsers have caught up.** Every capability that once required a framework -- reactive state, component encapsulation, routing, code splitting, async flow control -- is now addressable with native APIs. The cost of "vanilla" is no longer the absence of features but the absence of opinionated tooling. The payoff is drastically smaller payloads (10-25KB vs 250-800KB), faster Time-to-Interactive, and zero dependency risk.

The recommended architecture for a medium-complexity SPA is: ES modules for code organisation, Proxy + EventTarget for reactivity, IntersectionObserver for performance, AbortController for async hygiene, custom events for component communication, and the Navigation API for routing with an IndexedDB-backed SWR layer for data persistence. All of these ship in the browser. No npm install required.
