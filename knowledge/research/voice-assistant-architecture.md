# Voice Assistant Architecture: Research Summary

> Research conducted June 2026 for the JARVIS project -- a voice-driven desktop assistant for Windows with bilingual Slovak/English support.

---

## AREA 1: Voice Interface Design

### Speech Recognition Tradeoffs

Three tiers of STT exist for Python-based assistants, each with distinct tradeoffs:

**Google Speech Recognition (via `speech_recognition`)**
- Zero local model cost; simple API; reasonable accuracy for well-formed audio.
- Requires internet; no offline fallback; cloud dependency introduces variable latency.
- Best for: rapid prototyping, occasional use, projects where internet is guaranteed.

**Whisper (OpenAI)**
- Best-in-class accuracy, robust to noise and accents, multilingual (including Slovak), outputs punctuation.
- Latency: 350ms+ for tiny model on CPU; seconds for larger models. GPU strongly recommended for real-time use.
- Pronounced hallucination tendency ("Thank you." during silence) -- VAD preprocessing is essential.
- Faster-Whisper (CTranslate2 backend) offers the best accuracy-vs-speed balance for local deployment.

**Vosk**
- True streaming/real-time inference; ~65ms latency with small (40MB) models; runs on CPU only, even Raspberry Pi.
- Accuracy markedly lower (82-92% WER); known buffer deletion at utterance start (~200ms); struggles with overlapping speech.
- 20+ languages supported; fully offline; ideal for command-and-control but insufficient for freeform dictation.

**Pattern:** A hybrid approach combines Vosk for always-on wake/listen (low latency) and Whisper for high-quality transcription of captured utterances. VAD (WebRTC or Silero) gates the audio pipeline before either model runs.

### TTS Patterns: Latency vs. Quality

| System | Type | P95 Latency | Memory | Quality | Offline |
|--------|------|-------------|--------|---------|---------|
| Edge TTS | Cloud (Microsoft API) | ~240ms (warm), ~310ms (cold) | 58MB | Very high (neural) | No |
| Piper | Local (ONNX) | ~227ms | 45-65MB | Good (varies by model) | Yes |
| ElevenLabs | Cloud API | ~300-500ms | N/A | Highest | No |
| pyttsx3 | Local (system) | ~50ms | Low | Low (robotic) | Yes |

Edge TTS hits a sweet spot: cloud neural quality without local GPU cost, and its latency is competitive with local Piper once HTTP/2 connections are reused. The main liability is network dependency -- a local fallback (Piper or pyttsx3) is prudent for offline resilience.

**Streaming vs. Batch:** Streaming TTS (synthesising-and-playing in parallel chunks) reduces perceived latency by 40-60% versus generate-then-play. Edge TTS supports streaming natively via its `StreamReader` API; Piper has streaming via incremental ONNX inference. ElevenLabs requires websocket connections for streaming.

### Voice UX Patterns

**Wake Words:** Projects converge on Porcupine (Picovoice) for on-device wake detection -- small footprint, cross-platform, configurable sensitivity. Snowboy (deprecated upstream) and Vosk-based keyword spotting are alternatives. A push-to-talk fallback is standard for noisy environments.

**Interruption (Barge-in) Handling:** The voice agent pipeline can be modelled as an arbitration system:
- Full barge-in: any user speech stops TTS immediately.
- Selective barge-in: only specific keywords ("stop", "wait") trigger interruption.
- Adaptive interruption (LiveKit pattern): acoustic signal analysis distinguishes true barge-in from backchannels ("uh-huh", "right") before routing to STT.
- A shared `_is_speaking` flag (single-writer, GIL-protected) is the simplest Python pattern; more sophisticated systems use an event-based arbitrator that pauses TTS on VAD activation.

**Endpoint Detection:** The standard approach is WebRTC VAD with a "hangover" mechanism -- extending endpoints through brief silence (300-800ms) to avoid fragmenting natural speech. Semantic end-of-turn detection (BERT-based classifier) is emerging but adds complexity.

### Language Detection and Switching

Bilingual Slovak/English voice assistants are well-supported. The recommended architecture:
1. STT runs with language hint (`sk-SK` or `en-US`) derived from the last known response language.
2. After transcription, a lightweight language identifier (`langdetect` or `fasttext`) runs on the text.
3. The detected language is passed to the LLM in the system prompt, which responds in the matching language.
4. A response prefix tag (`[SK]` / `[EN]`) is parsed to update the global language state and select the correct TTS voice.

Whisper supports Slovak natively; Google STT requires explicit language code per request. Edge TTS has matching neural voices (`sk-SK-Lukas` for Slovak, `en-US-Jenny` for English).

### Microphone Thread Safety

Desktop voice assistants are inherently multithreaded:
- A **listener daemon thread** reads from the microphone (blocking PyAudio calls).
- A **main/executor thread** sends data to STT, calls the LLM, and plays TTS.
- A **TTS playback thread** (or callback) handles audio output.

Three invariants for thread safety:
- The input-mode flag (`_input_mode`: voice/text) is written only from the main loop, read from the listener thread -- single-writer + GIL is sufficient.
- The speaking flag (`_is_speaking`) is written before TTS starts, cleared after it ends. The listener reads it to suppress input during playback.
- The language variable is guarded by a `threading.Lock()` or `threading.RLock()`.

---

## AREA 2: Desktop Assistant Architecture

### How Open-Source Projects Are Structured

Surveying 10+ active open-source desktop voice assistants (2025-2026) reveals a convergent architecture:

**Pipeline stages (common to all):**
```
Audio Input --> VAD --> STT --> LLM --> TTS --> Audio Output
                 ^                       |
                 |   (barge-in loop)     |
                 +-----------------------+
```

**Three common process models:**
1. **Single-process with threads** (AG3, JARVIS Python): One Python process with daemon threads for audio I/O. Simplest, but GIL-bound and harder to isolate failures.
2. **Multi-process (Vocalyx pattern):** Separate STT server, TTS server, and client communicating over WebSockets. Higher complexity but enables hot-reload of individual components.
3. **Electron + Python backend (JARVIS Axshatt):** Electron frontend for GUI, Python MCP server for OS control. Best for visual-heavy assistants but adds build complexity.

**Common tools found across projects:**
- STT: SpeechRecognition, Whisper, Vosk, Deepgram
- TTS: edge-tts, pyttsx3, ElevenLabs
- GUI: PyQt5/PyQt6, tkinter, Electron
- LLM: Ollama (local), OpenAI, Gemini, Claude, Groq
- VAD: webrtcvad, Silero VAD

### Context Injection Patterns

The most efficient pattern is **prepending memory to the first user message** rather than embedding it in the system prompt. This keeps the system prompt stable for prompt caching (avoiding cache invalidation every turn) while still giving the model access to stored context.

The memory injection flow:
1. User speaks ("What was that recipe I saved last week?")
2. Before the API call, the assistant reads from its key-value store (`jarvis_memory.json` or SQLite).
3. The stored items are prepended as synthetic user context ("[Memory context: Recipe for lasagne saved 2026-06-10.]").
4. This message + memory is sent as the first user turn.

More sophisticated systems (mengram, brainctl, MindForge) use token-budgeted context builders that pack memory with variable fidelity -- full text for recent/critical items, compressed summaries for older ones, placeholders for least important.

### Event Loops for Real-Time Interaction

Python desktop assistants use `asyncio` event loops (not `tkinter.mainloop` or PyQt exec) for real-time interaction. The pattern:
1. `asyncio.run(async_main())` boots the application.
2. Two daemon threads start for text reader (stdin) and voice listener (mic).
3. The asyncio event loop handles the main turn logic: waiting for input from either thread, calling the LLM (blocking), dispatching tools, streaming TTS.
4. `asyncio.sleep(0)` yields control between turns.

This avoids the complexity of async audio libraries while keeping the main logic in a modern event-driven pattern.

### Daemon / Background Process Patterns

All surveyed assistants run as **persistent desktop processes** (not services):
- Daemon threads (`threading.Thread(daemon=True)`) ensure audio listeners terminate when the main process exits.
- System tray icons (PyQt5 `QSystemTrayIcon`) provide visibility without a full window.
- Hot-reload: when the assistant modifies its own code (`call_developer_agent`), `os.execv()` restarts the process in-place. This drops all process state (audio handles, mic) so the new process starts clean from `main()`.
- Startup timestamp and bootstrap sequence are logged to a file for debugging.

### Logging and Debugging Voice Applications

Voice apps present unique debugging challenges -- audio state is hard to inspect post-mortem. Patterns from the field:

- **Per-turn log entries**: each turn records input text, STT latency, LLM token usage, TTS latency, and output text. Enables end-to-end latency analysis.
- **Audio file capture**: option to save WAV files of recorded utterances (rotated/limited to avoid disk bloat). Invaluable for debugging STT failures.
- **Token usage logging**: input tokens, output tokens, cache read tokens, cache creation tokens printed per turn. Essential for cost monitoring with cloud LLMs.
- **Graceful degradation logging**: if STT fails (noise, API error), log the raw audio duration and RMS energy -- distinguishes "no speech detected" from "speech present but garbled".
- **Tool call audit trail**: every tool dispatch and its result is logged with elapsed time and truncation status.

---

## Key Sources

- [AG3 - Desktop Voice Assistant (PyQt5)](https://github.com/Speed1929/AG3)
- [JARVIS - Electron + Python MCP Backend](https://github.com/Axshatt/VirtualAssistant)
- [EveryLinguaAI - Multilingual Voice Assistant](https://github.com/RoshisRai/EveryLinguaAI)
- [Mira-AI - Bilingual Voice Assistant](https://github.com/deepak1700707/Mira-AI)
- [Screen-Aware AI Assistant (PyQt6 + Whisper + edge-tts)](https://dev.to/bitshank2338/how-i-built-a-screen-aware-ai-assistant-in-python-full-stack-breakdown-pyqt6-whisper-ollama-1354)
- [mengram - Memory Engine for LLM Agents](https://pypi.org/project/mengram/)
- [brainctl - Context Engineering for AI Agents](https://pypi.org/project/brainctl/1.2.0/)
- [Open Timeline Engine - Local-First Context Platform](https://github.com/JOELJOSEPHCHALAKUDY/open-timeline-engine)
- [MindForge - Multi-Level Memory Management](https://github.com/aiopsforce/mindforge)
- [Piper TTS vs Edge-TTS Benchmarks](https://datasea.cn/go0503609553.html)
- [LiveKit Adaptive Interruption Handling](https://docs.livekit.io/agents/logic/turns/adaptive-interruption-handling/)
- [FireRedChat Full-Duplex Voice Interaction](https://ar5iv.labs.arxiv.org/html/2509.06502)
- [Pocket TTS Voice Agent Tutorial](https://getstream.io/blog/pocket-tts-voice-agent/)
