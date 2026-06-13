# AI Coding Assistant UI/UX Design Patterns

> Research compiled June 2026. Covers Cursor, GitHub Copilot, Continue.dev, Aider, Replit, Claude Code, Lovable/Bolt/v0, and Cody.

---

## 1. Code Display

The industry has converged on three diff visualization strategies, each with tradeoffs:

**Inline diff (gutter decorations).** Cursor's classic editor and Copilot's inline suggestions show additions/removals directly in the editor gutter (green/red bars). Users strongly prefer this for granular review -- it maps to the muscle memory of reviewing a colleague's PR. Cursor's 2026 shift to a session-level "Review" button (showing only a bulk `+1181 -413` summary) was met with user backlash, confirming that per-change inline diff is table stakes.

**Split diff panel.** A dedicated side-by-side or unified diff panel (old vs. new) is standard for reviewing multi-file edits. Cody's `DiffCell` component, the JetBrains Copilot redesign, and Cursor's Agent Window all implement this pattern. The key differentiator is whether each chunk has individual Accept/Reject controls or only a global apply button.

**Syntax-highlighted code blocks in chat.** The simplest pattern: code is rendered as monospace blocks with syntax highlighting and copy buttons inside the chat transcript. This is the baseline for Continue.dev, Cody, and chat-only Copilot mode. All tools support line numbers, and most support click-to-navigate-to-file.

**Code folding** is surprisingly absent from most AI coding UIs -- only the native editor (VS Code / JetBrains) provides folding in the diff view. AI-specific panels generally show full files without folding controls.

---

## 2. Edit Workflows

The core tension is **preview vs. autonomy**. Three patterns emerge:

**Apply-on-accept (safe).** The AI generates changes, shows a diff, and waits for the user to click "Apply" or "Discard" per chunk. Cursor's classic editor, Copilot's inline chat, and Continue.dev's `/edit` all follow this model. Users want Undo/Redo support baked into the diff panel -- currently only supported via git (undo = `git checkout`) rather than an in-app history slider.

**Auto-apply with review surface.** The AI writes changes directly to disk, but a review panel accumulates all modifications for post-hoc approval. Cursor's Agent Window and Claude Code's agent mode default to this. The tradeoff: speed during writing, but risk of unseen damage. Copilot's JetBrains plugin offers individual toggles for Agent mode vs. Coding Agent to let users choose.

**Plan-then-edit.** Cursor's "Plan Mode" and Aider's `/architect` separate the workflow into two phases: the AI creates a plan (no file changes), the user reviews it, then the AI executes. This is becoming the dominant pattern for complex multi-file tasks where the user wants a spec before committing.

**Multi-file edit visualization** remains a weak point across all tools. No tool yet provides a clean "table of contents" view showing which files were changed, with a summary per file, before the user reviews individual diffs. Claude Code's session summary and Cursor's Agent Window attempt this but fall short.

---

## 3. Context Management

Context is the single most important UX differentiator for AI coding tools. The patterns are:

**@-mention / slash-command picker.** The de facto standard pioneered by Continue.dev and adopted by Cody, Copilot, and Claude Code. Typing `@` brings up a fuzzy-search palette where you can add files (`@file`), folders (`@folder`), search results (`@search`), docs (`@docs`), terminal output (`@terminal`), or git context (`@git`). Continue.dev has the richest ecosystem with 15+ built-in context providers.

**Context pills/chips.** Once added, context items appear as removable chips or pills above or inside the input box. This gives the user a persistent visual reminder of what the AI can "see." Cody's web UI and Copilot's chat panel both use this pattern. The chips typically show file name, line range, and an X button to remove.

**File picker sidebar.** A secondary sidebar or panel for browsing the project tree and adding files to context with a single click. Cursor and Continue.dev implement this. The file picker often shows git status indicators (modified, new, deleted) so the user can quickly add changed files.

**Token usage display.** A small counter showing estimated context consumption (e.g., "4.2k / 128k tokens") is present in Claude Code, Aider, and Cody. This helps users understand when they are approaching context limits. The display is typically placed near the input box or in the status bar. Only Claude Code and Aider show it prominently -- most IDE extensions bury it in a settings panel.

**Automatic context gathering.** Cody's "Agentic Chat" (2025) and Cursor's agent mode proactively gather context by searching the codebase, reading related files, and even browsing the web -- without explicit user direction. This shifts context from user-manual to AI-managed, with the tradeoff of unpredictable token consumption and latency.

---

## 4. Agent vs. Chat Mode

Every major tool now distinguishes between "simple chat" and "autonomous agent" modes. The UI patterns for this differentiation are:

**Mode selector (dropdown/toggle).** A visible control at the top of the chat panel to switch between modes. Copilot uses a dropdown agent picker (`Ctrl+Alt+I`). Cursor uses a Plan / Agent toggle. The visual distinction is usually color-coded (blue for chat, purple/orange for agent) and accompanied by a brief description of what the mode does.

**Agent picker dropdown.** Copilot's latest pattern replaces `@agent-name` mentions with a dropdown selector. Keyboard shortcut `Ctrl+Alt+I` opens the chat panel. This reduces syntax friction for non-power-users.

**Status indicator pill.** A compact colored dot or badge that encodes the agent's state: orange = needs input, green = working, grey-green = idle with pending changes, grey = idle. Copilot's 2026 Anvil redesign collapses the entire toolbar into three visual groups with this pill as the central state indicator.

**Granularity slider.** Some tools (Cursor, Claude Code) let users tune how autonomous the agent is: "ask every time" vs. "auto-approve reads" vs. "full autonomy." This is rendered as a stepped control or a permission-level selector.

**Chat is for intent, canvases are for state.** A 2026 consensus emerging across the industry: chat transcripts are bad at showing agent state. Structured work surfaces (canvases, panels, task dashboards) are replacing flat chat for agent output. Copilot's Canvases, Cursor's Agents Window, and Replit's Design Canvas all embody this shift.

---

## 5. Tool Execution Visibility

Users consistently report anxiety when the AI "goes silent" during multi-step tasks. The solutions:

**Collapsible tool call cards.** Claude Code and Cody render each tool call as an expandable card that shows: tool name, truncated arguments (not raw JSON), and status (queued / in-progress / completed / error). By default, cards are collapsed so the user sees a high-level timeline without noise.

**Risk-based styling.** Read-only tool calls (file reads, searches) are shown with neutral styling. Write operations (file writes, commands) get warning colors. Destructive operations (delete, install) are highlighted prominently. Claude Code and Cody both implement this. The visual treatment helps users spot dangerous actions at a glance.

**Streaming output in tool cards.** When a tool produces output (terminal command, file read), the output streams into the card line by line. This gives the user a sense of progress. Bolt.new and Replit show this in their browser IDE terminal pane.

**Approval dialogs for dangerous actions.** Claude Code's permission system uses tabbed modals with Normal / Plan / Auto-Accept modes. Aider and Claude Code both require explicit user confirmation before executing shell commands. The modal typically shows the exact command, a brief explanation of why it is needed, and Accept / Reject / Always Accept buttons.

**Tool timeline.** A vertical timeline of tool calls on the right side of the chat panel, showing the sequence of operations. This is present in Cursor's Agent Window and Claude Code's Agent View. Each entry shows timestamp, tool name, and duration.

**Progress bars for long operations.** For tasks expected to take >30 seconds (package install, build, deploy), a progress bar or indeterminate spinner is shown inside the tool card. Replit's Agent and Bolt.new use this pattern extensively.

---

## 6. Terminal / Console Integration

**Embedded terminal in IDE.** Copilot, Cody, and Continue.dev can inject terminal output into the AI's context via an `@terminal` context provider. The terminal is the actual IDE terminal (node-pty), not a simulation. The AI can see command history, errors, and output.

**Proposed-command display.** Before executing, the AI shows the exact command in a code block with an "Execute" button. Claude Code and Aider do this. The user can edit the command before approving it. This bridges the gap between suggestion and execution.

**Error highlight + fix flow.** A common pattern: when a terminal command fails, the error output is automatically sent back to the AI as context, and the AI suggests a fix. Cody and Copilot both implement automatic error-to-AI feedback loops.

**Bolt.new's browser terminal.** Bolt.new runs a real Node.js runtime (WebContainer) in the browser with a visible terminal pane. The terminal is not simulated -- it is a real shell with live output, file system, and package manager. This is unique among AI app builders and is a key differentiator.

**Claude Code's TUI terminal integration.** Claude Code does not embed a terminal -- it operates in the user's existing terminal. Output from commands it runs (via `execute_command`) appears as tool cards in the scrollback. The user never leaves their terminal session. The 2026 redesign uses an inline viewport (fixed bottom input + status bar) while all output stays in the normal terminal buffer, preserving native scrollback, search, and selection.

---

## 7. File Tree Integration

**Workspace-aware sidebar.** Cursor, Continue.dev, and Copilot all show the project file tree in a sidebar. Files modified by the AI are highlighted (usually with a dot or color change). Clicking a file opens it in the editor with the AI's changes inline.

**Open files tabs.** The AI can access the content of files open in editor tabs via an `@open` context provider (Continue.dev) or automatic context gathering (Cody). This is a zero-effort way for the AI to know what the user is working on.

**Git status indicators.** Files with uncommitted changes, new files, or conflicts are marked in the file tree. Cursor and Copilot both inherit this from VS Code. The AI can use `@git` (Continue.dev) or automatic diff context to see staged and unstaged changes.

**Context boundary visualization.** A pattern still emerging: showing the user which files are "in context" (being actively tracked by the AI) vs. "out of context" (known to the project but not loaded into the AI's window). Continue.dev's `@codebase` search and Aider's `RepoMap` are early implementations.

---

## 8. Collaboration Features

Collaboration in AI coding tools is still primitive compared to traditional IDEs, but patterns are forming:

**Share session / export.** Continue.dev has a `/share` slash command that exports the chat to markdown. Claude Code sessions can be shared via the Supervisor process (v2.1.139+). Most tools have a "Copy chat as markdown" or "Share link" button. The industry standard is markdown export with code blocks preserved.

**Conversation history.** Cursor, Copilot, and Continue.dev store chat history in the sidebar. Users can scroll back through previous turns, edit past messages, or start fresh threads. Cursor's history is tied to the project workspace.

**Replit's shared Kanban.** Replit Agent 4 introduced a shared Kanban board (Drafts / Active / Ready / Done) for team collaboration. This is the most structured collaboration pattern among AI coding tools -- it goes beyond chat history into project management.

**Git sync.** Most tools integrate with git for version history. Cursor's new Diffs View lets users stage, commit, and manage PRs. Lovable has automatic two-way GitHub sync. Copilot uses `@git` context to understand branch state. The pattern is: git is the source of truth for version history, not the AI tool itself.

---

## 9. Onboarding & Empty States

**Character-led welcome.** Claude Code's GitHub issue #8536 proposes replacing the blank initial screen with a welcome featuring the "Clawd" mascot. This follows GitHub's successful Octocat pattern -- a friendly visual character reduces the intimidation of a blank terminal.

**Outcome-focused empty state copy.** The 2025 design consensus: instead of "Chat with AI," use "Create your first feature" or "Fix that bug." Explain what the screen does (1-2 sentences), guide the next step (one primary CTA), and reassure ("Takes 2 minutes, you can rename it anytime").

**Structured first prompts.** Continue.dev and Cody display example prompts on first load: "Explain this code," "Add error handling," "Write tests for this function." These reduce the "blank page problem" for new users. v0 starts with a prompt input and an example that users can remix.

**Three onboarding paths.** Tools increasingly offer Create-first (blank project), Import-first (bring existing code), and Template-first (start from a project template) as distinct paths. Replit and Bolt.new implement all three.

**Scaffolded guidance for novices.** A 2025 University of Nebraska study found that novice programmers strongly benefit from structured, scaffolded first experiences. The pattern is: high structure on day one, gradually fading to open-ended chat as the user gains confidence.

**No competing CTAs.** The empty state should offer one primary action. Secondary actions (import, settings) are visually subdued. Long forms before the first "win" are anti-patterns -- ask for the minimum information to get started.

---

## Cross-Cutting Themes

**TUI vs. GUI convergence.** Claude Code, Aider, and Codex CLI prove that terminal-first AI coding is viable. They use an inline viewport pattern (fixed bottom input bar, output in normal terminal buffer) rather than fullscreen TUI, preserving native scrollback and search. Meanwhile, IDE extensions are adding agent panels that look increasingly like TUIs. The two paradigms are converging on a shared set of patterns: collapsible tool cards, status indicators, diff panels, and approval dialogs.

**The canvas shift.** The most significant 2026 trend is the move from chat-transcript-as-interface to structured canvases. Copilot's Canvases, Cursor's Agents Window, Replit's Design Canvas, and Claude Code's Agent View all decouple agent output from the linear chat stream. This lets users inspect, edit, approve, and organize agent work in a persistent, non-linear workspace.

**Chat for intent, state for outcomes.** The emerging industry design principle: use chat to express intent (what you want), but use structured visual surfaces for state (what the agent is doing, what changed, what needs approval). Flat chat transcripts are being replaced by rich, interactive, persistent work surfaces.
