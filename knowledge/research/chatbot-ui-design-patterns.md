# Chatbot UI Design Patterns — Research Summary

> Research compiled June 2026. Sources include ChatGPT, Claude.ai, Perplexity AI, Grok, Gemini, Open WebUI, and community-built chat interfaces.

---

## 1. Layout Patterns

**Two-pane (desktop) / single-column (mobile) is the modern standard.**

- **Desktop**: Left rail for conversation history (280-320px), centered message stream capped at 720-768px max-width, optional right panel for artifacts/code. Claude.ai popularised the no-avatar, centred-content layout where user messages are subtle right-aligned pills and assistant responses flow without bubble backgrounds — a cleaner reading experience.
- **Mobile**: Full-bleed single column, sticky composer docked at the bottom. The sidebar becomes a slide-out drawer triggered by hamburger or swipe gesture.
- **IDE embed** (Cursor, Cline): Chat panel ~400-520px wide beside the code editor.
- **Input-first pattern** (Notion AI, Linear AI): Centred input with suggestion chips, no history visible until the first query.
- **Open WebUI** uses a three-tier client-server architecture (Svelte 5 + FastAPI) with a **message tree** (id, parentId, childrenIds) instead of a flat array — enabling branching, forking, and arena-mode model comparison.

---

## 2. Chat UX — Message Flow & Feedback

| Element | Best Practice |
|---------|---------------|
| **Streaming** | Tokens rendered in real-time. First-token target <800ms. Blinking cursor signals "alive" vs "done". |
| **Auto-scroll** | Only auto-scroll when user is within ~100px of bottom; show a "Jump to latest" floating button otherwise. |
| **Avatars** | Claude.ai removed avatars entirely — messages are distinguished by alignment and subtle background. ChatGPT keeps them. No clear winner; pick one system and be consistent. |
| **Timestamps** | Show on hover or for the first message in a burst (temporal grouping). |
| **Stop button** | Placed near the composer, hidden on completion. |
| **Suggestion chips** | Follow-up prompts shown below each assistant response; click to send without typing. |
| **Thinking indicator** | Collapsible reasoning section (default collapsed) for chain-of-thought transparency — pioneered by Claude. |

**Typing indicator**: A three-dot animated pulse. Important when latency exceeds 1s. On streaming responses, replace the indicator with the first token as soon as it arrives.

---

## 3. Markdown Rendering & Code Blocks

Rendering markdown **during a stream** is a joint engineering + design problem:

- **Incremental parsing**: Parse and render progressively to avoid flicker. Use throttled re-renders (~50ms batch window) — Open WebUI identified full re-render on every token as a known performance issue.
- **Code blocks**: Language label in the top-right corner (e.g., "python", "javascript"), a **copy button** that appears on hover, and syntax highlighting via highlight.js or Prism.js. A "run" button is becoming common (executes in a sandboxed environment).
- **Math**: KaTeX or MathJax for inline LaTeX rendering.
- **Tables**: Rendered as styled HTML tables, not raw markdown pipes.
- **Streaming markdown**: The caret/insertion point stays visible; unfinished code blocks show a dimmed "generating..." overlay until the closing fence is received.
- **Artifact panels** (Claude): Long documents or code get their own side panel with version history, copy-all, and download buttons.

---

## 4. Input Design

The dominant 2026 pattern is a **unified multimodal input bar** — a single cohesive toolbar integrating text, file upload, image paste, and voice recording.

- **Multi-line input**: Auto-resizing textarea (grows to ~6-8 lines, then scrolls). Tiptap-based rich editors (Open WebUI) support markdown shortcuts, `@` mentions, and `#` knowledge-base references.
- **Send button**: Always visible, right-aligned, disabled when empty. Keyboard: Enter to send, Shift+Enter for newline.
- **Attachment handling**:
  - Image thumbnails appear inline above the input bar with an "x" dismiss button.
  - Non-image files (PDF, DOCX) appear as name chips with type-specific icons.
  - Paste from clipboard (screenshots, images) is universally supported.
  - Drag-and-drop onto the chat window.
  - File size limit (10-25 MB) with inline validation.
- **Voice input**: Animated waveform or pulsing mic icon during recording. Keyboard shortcut (e.g., hold Alt to record, release to send). Silence detection and auto-timeout.
- **Slash commands** (`/`) for invoking tools, skills, or model switches inline.

---

## 5. Navigation & History Management

| Feature | Pattern |
|---------|---------|
| **New chat** | Pencil/plus icon at top of sidebar. Opens a fresh session instantly. |
| **Chat history** | Chronological list with the latest conversation title at top. Auto-generated titles from first user message. |
| **Search** | Debounced search input at the top of the sidebar. Filters by title and message content. |
| **Organisation** | Folders / project workspaces with inherited system prompts and knowledge bases (Open WebUI). Drag-and-drop reordering, archiving, cloning, pinning. |
| **Branching** | Message trees allow forking at any point (Open WebUI, Claude). Regeneration creates a sibling branch. |
| **Deletion** | Confirmation dialog (single click vs double-click to delete). Batch delete, archive (soft delete with restore). |
| **Active tasks** | Spinner next to chat items during background processing. |

---

## 6. Theme & Visual Design

- **Dark mode is the default**: 82% of users prefer dark mode at night, 47% keep it always-on. Use deep navy/slate greys (e.g., `#0f172a`) instead of pure black. Reduce brand accent saturation by 10-15% in dark mode.
- **Semantic colour tokens**: Name colours by purpose (`surface-1`, `surface-2`, `accent-strong`) not by value — design light and dark tokens together from the start.
- **Glassmorphism**: Now used responsibly — applied to overlays, modals, sidebars, and message bubbles, not entire interfaces. Pair frosted glass with solid-colour text containers to maintain WCAG contrast. Key pattern: `backdrop-filter: blur(12px)` + `border: 1px solid rgba(255,255,255,0.1)`.
- **Micro-interactions**: Subtle, fast (150-300ms for feedback, 400-600ms for layout transitions). Every interactive element needs 4 states: default, hover, active, success/error. Use cubic-bezier easing. Always respect `prefers-reduced-motion`.
- **Bento grid layouts** are becoming popular for organising feature showcases and dashboards within chat apps.

---

## 7. Mobile Responsiveness

The **three-position bottom sheet** is the most sophisticated mobile pattern (2025-2026):

| Position | Height | Purpose |
|----------|--------|---------|
| PEEK | 20px | Only drag handle visible |
| INPUT | 96px | Handle + input bar (default) |
| HISTORY | 75vh | Full scrollable history + input |

Behaviour: Dragging upward always commits to HISTORY (never snaps back). Peek bubbles appear inline during generation. Spring animation (`cubic-bezier(0.32, 0.72, 0, 1)`). Backdrop overlay at HISTORY position; tap to collapse.

**Breakpoint strategy**: `<768px` = bottom sheet, `768-1023px` = right side panel (320-400px), `1024px+` = right panel (400-480px). All heights computed from `window.innerHeight` for dynamic viewport consistency. Touch targets >=44px minimum.

---

## 8. Multi-Modal UI Patterns

- **Image input**: Three supported methods — paste from clipboard, drag-and-drop, or file picker (paperclip icon). Validation: allowed MIME types (PNG, JPG, GIF, WEBP), max dimensions (4096x4096 px), max file size.
- **File attachments**: Shown as chips with type icons before sending. After sending, visible as inline previews or download links in the conversation.
- **Camera capture**: Mobile-only. Button next to the input bar opens the native camera. Used for real-world object recognition or document scanning.
- **Voice recording**: Animated waveform, keyboard shortcut toggle (Alt hold-to-record), silence detection, auto-timeout. Multiple backends: Web Speech API, Whisper API, Realtime API.
- **Inline previews**: Images render directly in the conversation; code renders in syntax-highlighted blocks; PDFs render as embedded viewers or download buttons.

---

## 9. Accessibility

- **WCAG 2.2 AA minimum**: 4.5:1 text contrast, 3:1 for UI components. One in five users experiences interfaces differently — design for inclusion from the start.
- **Keyboard navigation**: Every interactive element reachable by Tab. Visible focus indicators. Skip-to-content links. Shortcuts: Ctrl/Cmd+Enter to send, Ctrl/Cmd+Shift+C to copy last response, Ctrl/Cmd+N for new chat, Escape to close modals and stop generation, Arrow keys for navigating history.
- **Screen readers**: ARIA labels on all controls. Semantic HTML structure. Announce streaming start/end. Announce attachment uploads and errors.
- **High contrast mode**: Dedicated high-contrast theme that overrides glassmorphism blur effects.
- **Reduced motion**: Respect `prefers-reduced-motion` — disable all animations and transitions.

---

## 10. Error States & Resilience Patterns

| Error | UX Treatment |
|-------|--------------|
| **Rate limited (429)** | Auto-retry countdown with visible timer ("Rate limit hit — retrying in 29s..."). Respect `Retry-After` headers. |
| **Invalid/missing API key (401)** | Redirect to settings with a clear action button. |
| **Server error (5xx)** | Retry button + friendly message. Preserve user's last message. |
| **Network / connection lost** | Non-blocking banner between message list and input. Auto-retry on reconnect. |
| **Streaming interrupted** | Show partial response with a "Connection lost — tap to retry" indicator. |
| **Timeout** | Preserve partial response. Offer manual retry. |

**Key principles**: Never crash — every error has a pathway back. Be transparent (show *why*). Every error offers a next step (retry, dismiss, settings). Never lose the user's message or conversation context. Use exponential backoff with visible progress for automatic retries (1s -> 2s -> 4s -> max 3-4 attempts).

---

## 11. Synthesis — What Works for a Glassmorphism Project

For a burgundy/gold glassmorphism AI chat UI, the most applicable patterns are:

1. **Two-pane layout** with a conversation sidebar and centred chat stream
2. **No-avatar message flow** (Claude-style) with right-aligned user bubbles
3. **Unified input bar** with text + file + voice in one cohesive element
4. **Glassmorphism on sidebar and header** with solid-background message bubbles for contrast
5. **Three-position bottom sheet** for mobile (<768px)
6. **Semantic colour tokens** with burgundy (`#800020` range) as primary accent and gold (`#D4AF37` range) as secondary
7. **Incremental markdown rendering** with syntax-highlighted code blocks and copy buttons
8. **Inline numbered citations** (Perplexity-style) for any search-backed response
9. **Collapsible thinking sections** for chain-of-thought transparency
10. **Non-blocking error banners** with retry actions and input preservation
