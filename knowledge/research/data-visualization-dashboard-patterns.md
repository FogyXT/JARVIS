# Data Visualization & Dashboard Patterns for AI Assistant Web UI

> Research summary compiled June 2026. Covers charting libraries, LLM analytics, real-time streaming, conversation analytics, information architecture, dark-theme accessibility, monitoring UI, AI-specific components, audio visualization, and decorative WebGL effects.

---

## 1. Charting & Visualization Libraries

### Library Comparison

| Library | Best For | Bundle Size | Performance Ceiling | Learning Curve |
|---------|----------|-------------|---------------------|----------------|
| **Chart.js** | Standard dashboards, rapid prototyping | ~60-125 KB gzipped | ~10K points comfortably | 2-3 hours |
| **ECharts** | Enterprise, huge datasets, geospatial | ~167-400 KB | 10M+ points (progressive rendering) | 1-2 weeks |
| **D3.js** | Custom/chart-type visuals | ~70-250 KB modular | ~50K+ with optimization | 4-8 weeks |
| **Observable Plot** | Declarative D3 charts | Leverages D3 | Moderate (SVG-based) | Moderate |
| **ApexCharts** | Marketing dashboards, rapid dev | ~280 KB | Moderate | 1-2 days |

### Recommendation for JARVIS

**ECharts** is the strongest candidate for an AI analytics dashboard. It handles massive token datasets with progressive rendering, supports 20+ chart types, and has official React/Vue wrappers. With the 6.0 release (July 2025) it added chord diagrams (useful for topic/session relationships) and a matrix coordinate system.

**Chart.js** is a lighter alternative if bundle size matters. Its v4 tree-shaking architecture keeps payloads small. It lacks ECharts' large-data engine but is sufficient for a single-user assistant.

**D3.js** should be reserved for one-off custom visualizations (e.g., a conversation-branch tree) rather than as the primary charting layer.

### Real-Time Updates

ECharts has native incremental append (no full redraw), which is critical for streaming token counters. Chart.js needs manual decimation (LTTB algorithm) and animation disabling for real-time data.

---

## 2. Token Usage & Cost Visualization

### Core Metrics to Display

- **Total tokens** split by type: input, output, cache_read, cache_creation, reasoning (reasoning tokens can cost 60x more than visible output)
- **Cache hit rate** per session and per route
- **Cost tracking** with a maintained price book (update within 1 business day of provider price changes)
- **Per-session breakdown** with user/feature/tag dimensions

### Dashboard Components

- **KPI marquee row**: Total messages, total cost, avg cost/request, cache savings
- **Stacked area chart** (daily): input vs output vs cached tokens over time
- **Donut/bar chart**: cost by model/provider, cost by feature/route
- **Activity heatmap**: time-of-day usage patterns (hourly)
- **p99 cost per session** line chart -- averages lie; the tail is where issues live

### Key Implementation Details

- Compute cost at ingest time (not query time) by multiplying token counts against a `prices.json` book
- Tag every LLM span with: session_id, model_name, prompt_version, timestamp
- Use OpenTelemetry GenAI semantic conventions for standardized attribute naming
- Cache tracking is essential -- a 5% hit rate means leaving 40-70% of budget unused

---

## 3. Real-Time Data Display

### Streaming Architecture Choices

- **Server-Sent Events (SSE)**: Best for one-way server-to-client dashboards. Built-in auto-reconnection via `EventSource`, proxy-friendly, simpler than WebSocket. Recommended default for JARVIS.
- **WebSocket**: Full-duplex, lowest latency. Needed only if the client needs to send subscribe/unsubscribe commands.
- **Long Polling**: Fallback only -- increases latency and server load.

### SSE Pattern for JARVIS

Flask endpoint that subscribes to an in-memory event bus. Each turn's token count, tool calls, and status updates are pushed as SSE events. The frontend maintains a circular buffer (last N points) in React Query or similar state manager.

### UI Components for Real-Time Data

- **Live counters** with animated number transitions (GSAP or framer-motion for smooth digit rolling)
- **Progress bars** for long AI operations (tool execution, file processing)
- **Status indicator badge**: green/amber/red dot with pulsing animation
- **Newest-data emphasis**: gradient that fades from bright (latest) to dim (oldest)

### Key Constraints

- SSE has no built-in backpressure -- drop old messages for slow clients
- Use exponential backoff reconnection (EventSource does this automatically)
- Show connection status indicator (green connected / red disconnected)

---

## 4. Conversation Analytics

### Visualizing Chat History

- **Daily activity bar chart** with hour-by-day heatmap overlay
- **Sentiment timeline**: polarity scores plotted over time per message
- **Topic cluster view**: UMAP + HDBSCAN for 2D semantic map, or LDA for per-topic bar charts
- **Message length distribution**: histogram showing user vs AI message lengths

### Session Replay

- **Timeline scrubber**: step through conversation turns with adjustable playback speed
- **Gantt-style lanes**: parallel swimlanes for user prompts, thinking blocks, tool calls, and responses (pattern used by ClaudeScope)
- **Force-directed graph**: message nodes connected by reply relationships, colored by role (user/assistant/tool)

### Conversation Branching

- **Radial sunburst layout**: root at center (current session), branches for alternative tool execution paths
- **Tree view** with collapsible nodes for multi-turn reasoning forks

### Components for JARVIS

Given single-user scope, the most valuable analytics are: session activity timeline, tool-call frequency histogram, and a simple sentiment trend. Topic clustering adds visual polish but is secondary.

---

## 5. Information Architecture for Dashboards

### Bento Box Layouts (2025 Dominant Pattern)

A modular grid of differently-sized tiles arranged with **structured asymmetry** -- not a rigid equal-column layout. This improves scannability and reduces visual noise.

**Grid principles**:
- 12-column desktop grid, 4-column on mobile
- 2-3 larger hero tiles in the first viewport height for KPIs
- Medium analytical tiles balanced with compact utility tiles
- Cluster by purpose: outcomes, drivers, operations, health

### Recommended JARVIS Layout

| Zone | Content |
|------|---------|
| **KPI Marquee** (hero row) | Total conversations, total tokens, total cost, avg response time |
| **Model Telemetry** (medium tiles) | Cache hit rate, context window usage gauge, model in use |
| **Time-Series Band** (full-width) | Token usage over time (stacked area), cost trend |
| **Activity Panel** (right rail) | Real-time log feed, recent sessions, status indicators |
| **Utility Tiles** (bottom strip) | Conversation search, export controls, settings shortcuts |

### Design Patterns

- Micro-interactions (150-250ms) for tile expansion, hover states
- Compact sparklines inside KPI tiles
- Consistent scales across related tiles for reliable comparison
- Progressive disclosure: show summary first, drill down on click
- Predefined span remaps at breakpoints (12 -> 8 -> 4 columns)

---

## 6. Dark Theme Data Visualization

### Color Palette for Dark Backgrounds

- Use desaturated, lighter hues (not pure white or fully saturated)
- Avoid pure black (#000000) -- use dark gray (#1a1a2e or #18181b) instead
- Warm-toned palettes (oranges, yellows, pinks) perform better on dark backgrounds than cool tones
- For sequential data on dark themes: light -> medium -> bright progression (reverse of light-theme convention)

### WCAG Compliance

- **Text**: 4.5:1 contrast ratio minimum (3:1 for large text >= 18px)
- **Graphical elements** (bars, lines, areas): 3:1 contrast ratio with adjacent elements
- **Dual encoding**: never rely on color alone -- pair with shapes (circles vs triangles), line styles (dashed, dotted, solid), or pattern fills (crosshatch, dots)
- **Direct labeling**: label data points on the chart instead of separate legends (reduces cognitive load)

### Accessible Palette Recommendations

**UK Government Analysis Function palette** (tested for WCAG compliance):
- Dark blue (#12436D), Turquoise (#28A197), Dark pink (#801650), Orange (#F46A25), Dark grey (#3D3D3D), Light purple (#A285D1)

### Reduced Motion

- Respect `prefers-reduced-motion` -- replace animations with instant transitions
- For real-time data: use opacity fades instead of sliding/zooming animations
- Pulse animations on status indicators should stop at a solid color

---

## 7. Status & Monitoring UI

### Subsystem Health Dashboard Pattern

A `SystemHealthViewModel` with one entry per monitored subsystem (API, database, audio, STT, TTS). Each entry has:
- `HealthStatus` enum: Healthy / Degraded / Unhealthy / Unknown
- `LastHeartbeat` timestamp
- Optional latency or error detail
- Color encoding: green / amber / red / gray

### Real-Time Status Indicators

- **Connection status pill**: dot + label (Connected / Reconnecting / Disconnected)
- **Heartbeat waveform** for real-time streaming (TTS audio response monitoring)
- **Circular gauges** with color-coded severity for resource utilization
- **5-dot process load**: emerald = active, gray = inactive
- **Scrolling event log**: terminal-style with timestamp, severity badge, message

### Architecture

1. Initial load via REST GET /health
2. Real-time updates via SSE events (serviceHeartbeat, ttsStatus, sttStatus)
3. Heartbeat timeout detection -- if no pulse within threshold (30s), mark unhealthy
4. Status badges use skeleton loading states during initial fetch

### Alert Design

- Toast notifications for transient issues (e.g., API timeout, mic access lost)
- Persistent banner for critical failures (e.g., API key expired)
- Notification history panel with severity filter

---

## 8. AI-Specific UI Components

### Thinking / Reasoning Visualization

The Ant Design Agentic UI (`@ant-design/agentic-ui`) provides production-ready components: `ThoughtChain` for step-by-step reasoning display, `ToolUseBar` for tool call status, and three viewing modes:

- **Collapsed**: compact preview during active thinking (single line + spinner)
- **Summary**: chronological top-N salient steps
- **Expanded**: full step text in structured vertical timeline

Additional patterns:
- **Vertical timeline** with animated step cards, self-correction badges
- **Thinking dots** (animated ellipsis) during reasoning, replaced by structured output when complete
- **Reasoning dependency tree** for multi-turn logic paths (VISTA-style)

### Tool Call Timeline

- **Gantt-style lanes**: parallel tracks for user -> thinking -> tool_execution -> response
- Each tool call gets a collapsible card showing: tool name, input (truncated), output (truncated), duration, success/failure badge
- Color-code by tool type: file operations (blue), search (green), browser (purple), system commands (orange)
- Duration bar proportional to execution time, with a "too long" threshold marker

### Context Window Usage Gauge

A semi-circular gauge showing current context utilization:
- Segmented by input tokens, cached tokens, output tokens
- Warning zone when approaching context limit (e.g., >80%)
- Flashing indicator when context pruning occurs

### Model Comparison View

If JARVIS supports model switching, a side-by-side comparison:
- Response time, token count, cost, and confidence per model
- Sparkline of past N comparisons

---

## 9. Audio Visualization

### Web Audio API Pipeline

The `AnalyserNode` is the core API:
- `getByteTimeDomainData()` -> oscilloscope/waveform (time-domain)
- `getByteFrequencyData()` -> FFT spectrum (frequency-domain)
- `fftSize` range: 32 to 32768 (default 2048), must be power of 2
- Wire up: AudioContext -> MediaStreamSource (mic) -> AnalyserNode -> canvas rendering via requestAnimationFrame

### Recommended Library

**audioMotion-analyzer** (npm, ~30KB minified, zero dependencies):
- High-resolution real-time spectrum analyzer
- Logarithmic, linear, Bark/Mel frequency scales
- Decibel and linear amplitude scales
- 5 built-in color gradients + custom gradients
- LED bars, mirror, reflection, radial spectrum modes
- HiDPI/Retina support

### Visual Modes for JARVIS

| Mode | Data Source | Visual Style | When to Show |
|------|-------------|--------------|-------------|
| **Oscilloscope** | Time-domain | Green-on-black tracing waveform | Idle / listening |
| **Spectrum analyzer** | FFT | LED bars or smooth curve | While speaking TTS |
| **VU meter** | Peak/RMS level | Symmetrical stereo bars | Mic input monitoring |
| **Voice activity** | Energy threshold | Glowing ring/circle | Detecting speech |

### Implementation Notes

- Create AudioContext only after user interaction (browser autoplay policy)
- Use `requestAnimationFrame` for render loop
- Clear canvas each frame before redraw
- Handle microphone access via `getUserMedia({ audio: true })`

---

## 10. WebGL / Canvas Decorative Effects

### Particle Systems for AI Activity

The dominant pattern is a **flow field particle system** using Perlin/simplex noise as a driving force:

- Thousands of small particles flowing along noise vectors
- Color gradient from cool to warm based on activity state
- Mouse interaction (repulsion/attraction fields)
- NeuroFlow Nexus uses custom Canvas API for 80+ animated nodes at 60 FPS

### Implementation Approaches

| Approach | Library | Performance | Complexity |
|----------|---------|-------------|------------|
| **Canvas 2D** | Raw canvas | Good for <10K particles | Low |
| **WebGL** | Three.js | Excellent (60 FPS at 100K+) | Medium |
| **Shader-only** | Custom GLSL | Best for fullscreen effects | High |
| **Lightweight** | Flow Field Background (21st.dev) | Good (zero dependencies) | Low |

### Shader Effects

- **Gradient flow backgrounds**: animated gradients that shift based on AI activity state (idle -> thinking -> speaking)
- **Fractal Brownian Motion** (fBM) in GLSL for organic, natural-feeling motion patterns
- **FBO render pipeline** for post-processing bloom/glow effects (used by Codrops tutorial)
- **LUT-based color grading** for consistent art direction across effects

### Activity-Responsive Effects

Bind particle behavior to real application state:
- **Idle**: slow, cool-colored (blue/purple), gentle drift
- **Thinking**: faster motion, warm pulse, particle density increases
- **Tool executing**: burst particles at intervals, brighter colors
- **Speaking**: waveform-synced particle flow, audio-reactive

### Performance Considerations

- Use `renderOnVisibility` (only render when tab is visible)
- FPS limiter for background or inactive tabs
- Texture-as-data approach (Codrops): reduced JSON payload from 20MB to 604KB by encoding particle data in textures
- Respect `prefers-reduced-motion`: freeze particles at current position, no opacity pulsing
- On low-end machines: degrade gracefully to static gradient or skip WebGL entirely

---

## Synthesis: Recommendations for JARVIS

### Tier 1 (Highest Value -- Build First)

- **ECharts** for token usage/cost time-series and cost breakdown charts
- **SSE-based streaming** for real-time token counter and status updates
- **Bento grid layout** with KPI marquee, time-series band, and activity rail
- **AI thinking visualization** (Ant Design ThoughtChain or custom vertical timeline)
- **Dark theme accessible color palette** (UK Government scheme) with dual encoding

### Tier 2 (Add for Polish)

- **Conversation analytics**: daily heatmap, sentiment timeline, tool call frequency
- **Status dashboard**: subsystem health cards with heartbeat indicators
- **Context window gauge** (semi-circular with warning zone)

### Tier 3 (Decorative / Nice-to-Have)

- **Particle flow field background** using Canvas 2D (not WebGL -- lower complexity)
- **Audio waveform** display (audioMotion-analyzer for TTS visualization)
- **Reduced-motion compliant** animations on all interactive elements
