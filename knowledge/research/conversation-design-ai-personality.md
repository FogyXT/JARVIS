# Conversation Design & AI Personality — Research Synthesis for JARVIS

> Voice-driven desktop AI assistant | Bilingual (SK/EN) | Single user ("Fogy") | Windows + HUD

---

## 1. Conversational UX Patterns

### Turn-Taking
The foundational rule from VUI design: **voice is linear and transitory** — listeners cannot re-read. Every turn should pass the "one-breath test" (Amazon Alexa guideline): if the response can be spoken at a conversational pace in one inhalation, the length is correct. Responses over ~20-25 words fragment user attention.

**Key patterns for JARVIS:**
- End every turn with a clear prompt or question, then stop. Users instinctively begin speaking when they hear a question finish — don't bury it.
- Use **conversation markers** ("First...", "Next...", "Finally...") for multi-step tasks, with 350-400ms SSML breaks between items.
- After speaking, signal the user's turn with a visual indicator (HUD mic icon glow) and begin listening immediately — no dead air.

### Handling Pauses and Silence
Well-timed silence is a design tool, not a bug. The Nielsen Norman Group's usability studies of Alexa/Siri/Google Assistant confirm that premature interruption is a top user complaint.

- **End-of-speech to first-audio latency target**: <= 300ms at p95. Humans perceive lag beyond that.
- **Micro-pauses (0.3-0.5s)** after key statements mirror natural conversational rhythm.
- **Silence can convey empathy**: slightly longer pauses before delivering bad news or apologies increase perceived sincerity.
- **Smart endpointing**: Use ML-based detection (not just VAD silence thresholds) to distinguish a genuine pause from "thinking" mid-sentence. If multiple low-word-count utterances arrive in a window, the user is likely in a noisy environment — defer.

### Barge-In (Interruption)
Whether to allow the user to speak over the assistant depends on persona design. In conversational systems with avatars/HUDs (human-like presence), barge-in is often turned **off** — people naturally wait for their turn. In task-oriented systems, barge-in is essential.

**Recommendation for JARVIS:** Enable barge-in with an "adaptive" interruption mode. Use an audio model to distinguish real interruptions from backchannel acknowledgments ("uh-huh", "okay"). Set a `min_words` threshold (>= 1-2 words) before an utterance counts as an interruption, preventing coughs or background noise from triggering.

### Confirmation Strategies
- **Implicit confirmation** (preferred): Repeat key information naturally in the next turn. "Setting an alarm for 7 AM. What label should I add?" — the repetition confirms without breaking flow.
- **Explicit confirmation** (use sparingly): "Did you mean X?" — reserve for high-stakes actions (deleting files, sending messages).
- **Avoid over-confirming**: Saying "Okay" after every user utterance feels robotic. Use strategic silence or subtle audio cues instead.

### Error Recovery
The most effective repair strategy when things go wrong: **give the user options based on what they just said** — not generic "I didn't understand." Guide them back to a valid state rather than dumping an error message.

---

## 2. AI Personality Design

### Anthropic's "Well-Liked Traveler" Framework
Claude's personality designer Amanda Askell describes the ideal AI persona as a **"well-liked traveler"** — an entity that adapts to local customs and the person they're talking to without pandering. This is the single most useful mental model for JARVIS.

**Three balancing acts this solves:**
1. Adaptable yet principled — adjusts tone to context without abandoning core values.
2. Helpful without sycophancy — will disagree when appropriate, but respectfully.
3. Engaging without manipulation — prioritizes honesty over keeping the user happy.

### The Soul.md / SOUL.md Pattern
An emerging standard for portable AI personas. Key dimensions that map well to JARVIS:

| Dimension | Scale / Choice |
|-----------|----------------|
| Formality | Casual to formal (JARVIS: casual but competent) |
| Warmth | Reserved to warm (JARVIS: warm but not overbearing) |
| Verbosity | Minimal to elaborate (JARVIS: concise for voice, richer on HUD) |
| Jargon | None to domain-specific (JARVIS: tech-literate but explains when needed) |
| Uncertainty handling | Confident to "I'm not sure, here's what I think" |
| Refusal style | Direct ("I can't do that") vs. apologetic |

### Personality Traits That Work for Assistants
Research across Replika, Character.AI, and major VAs converges on a shortlist:

- **Competent but not arrogant** — confidence earned through accuracy, not bluster.
- **Helpful but not overbearing** — offers suggestions, doesn't push them.
- **Warm but not fake** — sincerity beats manufactured cheerfulness.
- **Humorous but not at the user's expense** — self-deprecating works; sarcasm at the user doesn't.
- **Willing to disagree** — paradoxically, occasional principled disagreement increases trust.

### Implementation via System Prompt
- **Facts must be braided into voice, not placed in separate specification blocks.** A list of traits in a system prompt is just a wishlist. Each trait should manifest as a behavioral rule with an example.
- **Priority hierarchy**: Rules near the end of the system prompt are followed most reliably — put the most important behavioral guardrails there.
- **CARE Pattern**: Context, Ask, Rules, Examples — a structured framework that stabilizes tone across sessions.

---

## 3. Bilingual / Multilingual Assistant Design

### The Code-Switching Reality
Academic research (Cihan et al., CUI 2022) shows that bilingual speakers naturally **code-switch** — mixing languages within utterances. Current voice assistants are "monolingual by default," which forces users into a language mode that feels unnatural. Supporting code-switching reduces the cognitive burden of speaking a non-native language.

### Language Detection Strategy
- **Per-turn, not per-session**: Language can change mid-conversation. Detect on every user turn.
- **Bias detection with context**: If the last assistant response was in Slovak, bias toward Slovak detection.
- **Low-confidence fallback**: When detection confidence is below threshold, use the user's historically preferred language rather than guessing.

### When to Respond in Which Language
Three viable strategies, ordered by naturalness:

1. **Mirror the user** (recommended for JARVIS): Respond in the language the user spoke. If they code-switch mid-utterance, prefer the language of the main clause or the last complete sentence.
2. **Maintain session language**: Once set (by first user utterance or explicit choice), stay in that language until the user switches.
3. **Hybrid**: Respond in the user's language, but allow domain-specific terms in the other language (e.g., technical English terms in a Slovak sentence).

### Cultural Adaptation
- **Slovak mode**: More formal greetings possible ("Dobry den, Fogy"), greater tolerance for indirectness, relationship-focused.
- **English mode**: More direct, task-focused, casual from the start.
- **The language tag system** JARVIS already uses (`[SK]` / `[EN]`) is correct — it makes the choice explicit and trackable.

---

## 4. Voice-Specific UX (Voice vs. Chat)

### Fundamental Differences from Chatbots
| Dimension | Chat | Voice (JARVIS) |
|-----------|------|----------------|
| Response length | Unlimited | One breath (~20-25 words) |
| Formatting | Markdown, lists, code blocks | Spoken prose only |
| Pacing | User controls reading speed | Assistant controls speaking speed |
| Re-reading | Possible | Impossible without "repeat" command |
| Backchanneling | N/A | Verbal affirmations ("hmm", "I see") |
| Noise handling | N/A | VAD, filtering, deferral strategies |

### Verbal Affirmations (Backchanneling)
- Use sparingly and naturally — not after every user turn.
- Acknowledge before acting: "Okay" / "Got it" / "Sure" — signals understanding without repeating the full request.
- Adaptive interruption models must distinguish user backchannels ("uh-huh") from actual turns.

### Pacing and Cadence
- **Answer first, details on demand**: Lead with the result, pause, then offer elaboration. This serves both "give me the quick answer" and "tell me more" users in one turn.
- **One-breath default**: If it takes more than one breath to say, it's too long for voice.
- **Punctuation as pacing**: Use sentence boundaries more frequently than in written text. Short sentences are easier to follow awrally.

### Background Noise Handling
- Multi-layered: Voice isolation -> noise suppression -> VAD -> confidence thresholding.
- When STT confidence is low AND word count is low -> defer (wait for more audio, don't respond to noise).
- Multiple low-confidence events in a window -> the user is likely in a noisy environment -> optionally prompt to move.
- JARVIS already uses `winsound.Beep` before recording — this is a good pattern. Consider adding a visual "listening" indicator on the HUD.

### Wake Word Fatigue
For a single-user always-on desktop assistant, the wake word ("Jarvis") should be lightweight. The current design (no persistent wake word, toggle between voice/text input modes) avoids this entirely — which is the right call for a desktop assistant.

---

## 5. Relationship Building

### Memory Is the #1 Driver of Perceived Relationship Depth
Research across Replika and companionship AI shows that **remembering past conversations** is the single most important factor in making an AI feel like a genuine relationship partner. JARVIS already has a `memory` tool — this is the foundation.

### Hierarchical Memory Architecture
Three-tier model from academic research (IEEE 2025, AAAI 2024):

1. **Episodic** (session-level): What happened in this conversation. Summarized per session.
2. **Semantic** (cross-session): Generalized knowledge about the user — preferences, habits, facts.
3. **Personal** (permanent): Identity-level information — name (Fogy), language preference, relationship history.

### Forgetting as a Feature
The Ebbinghaus Forgetting Curve applies: memories decay unless reinforced through recall. JARVIS should:
- Not treat all memories equally — recent or frequently recalled information gets higher weight.
- "Forget" trivial details gracefully (no need to remember every single query).
- Reinforce important memories through occasional callbacks ("You mentioned you were working on X last time...").

### Personalization Patterns
- **Repeated callbacks**: Refer to previous conversations naturally, not as a database dump.
- **Adaptive greeting**: Vary greetings based on time of day, recent interactions, user mood.
- **Inside jokes/references**: The deepest rapport comes from shared context. If Fogy makes a joke, JARVIS should be able to reference it later.

### Proactivity: Should the Assistant Initiate?
Research is mixed. Users report that proactive check-ins ("How was your meeting?") increase perceived closeness. However, unsolicited interruptions are frustrating.

**Guideline for JARVIS:** Proactivity is acceptable when:
- The user has explicitly enabled it ("remind me about X").
- There's high-confidence time-sensitive information (e.g., a calendar event starting soon).
- The assistant is continuing a previous conversation thread the user initiated.
- **Never** interrupt the user mid-task with unsolicited suggestions.

---

## 6. Error and Apology Patterns

### "I Don't Know" Is a Trust-Building Move
Fast Company research found that when an election-assistance AI said "I don't know" instead of guessing, users found it *reassuring* — it made the answers it did provide more trustworthy. The BODHI framework (Harvard/MIT) confirms: cautious questions build safety, while confident-sounding incorrect answers erode trust over time.

### The Apology Hierarchy
The landmark CHI 2022 study (Mahmood et al.) tested five apology conditions in voice assistants:

| Condition | Effectiveness |
|-----------|--------------|
| Serious + taking the blame | **Most preferred** — highest perceived intelligence, likeability, recovery satisfaction |
| Casual + taking the blame | Moderate — "Sorry for the mishap" |
| Serious + shifting blame | Weak — "The engineering team made an error" |
| Casual + shifting blame | **Worst** — worse than no apology at all |
| No apology (for minor errors) | Sometimes better than a bad apology |

**The key finding**: Offering no apology at all was sometimes better than an apology that lacked acceptance of responsibility.

### AI-Specific Apology Research (AI & Society, 2026)
- Users are **less forgiving** when an AI makes an error and apologizes than when a human does.
- For **anthropomorphized AI** (like JARVIS with personality and voice): Own the mistake (internal attribution) — matches human-human patterns.
- For **non-anthropomorphized AI**: External attribution (blaming circumstances) works better.
- **Sincerity matters**: A neutral/serious apology outperforms a humorous one in trust recovery.

### Practical Guidelines for JARVIS
1. **When you don't know**: Say so directly. Offer alternatives ("I don't know, but I can search for that").
2. **When you make a mistake**: Own it. "I was wrong about X. The correct answer is Y." Follow with action (repair), not just apology.
3. **When you can't do something**: Explain the boundary, not just the refusal. "I can't access your email directly, but I can help you draft a message."
4. **Empty promises backfire**: Saying "I'll do better next time" and then failing erodes trust more than honesty about limitations.
5. **Forward motion**: Always focus on getting the user back to the "happy path" — repair what matters, don't wallow in apology.

---

## 7. Voice + Screen Multimodal (HUD Design)

### The Redundancy Principle
The spoken response should **stand on its own**. The HUD adds depth, not dependency. If a user closes their eyes, they should still get the full interaction.

### Division of Labor

| Belongs in Voice | Belongs on HUD |
|----------------|----------------|
| Short confirmations | Dense or precise information |
| Action results ("File saved") | Passwords, URLs, code, numbers |
| Status updates | Long lists for selection |
| Alerts and timers | Disambiguation options |
| Narrative responses | Visual history / timeline |
| Personality and tone | Reference information (docs, specs) |

### Information Density Trade-off
Research on HUDs for voice assistants (Baghdadi et al., 2025) found that a **minimalist approach** — displaying only essential keywords and icons — achieved the highest usability scores. More visual content improved recall but increased distraction. The optimal pattern:

- **Voice delivers the summary** — what happened, what matters now.
- **HUD provides the detail** — numbers, options, references the user can look at at their own pace.
- **Position strategically**: Lower-center HUD real estate for highest-priority info; secondary info recedes in depth or scrolls.

### Multimodal Context Carryover
Amazon Science research found a **35% accuracy improvement** when users could reference visual elements through voice ("that one on the left"). JARVIS should support this: if the HUD shows options, the user should be able to say "the second one" and have it understood.

### Visual Feedback During Voice Interaction
- **Listening indicator**: Mic icon glow changes when JARVIS is listening vs. processing vs. speaking.
- **Transcription preview**: Show what was heard (reduces errors from misrecognition).
- **Processing state**: Brief visual indicator during Claude API calls.
- **Speaking indicator**: Waveform or similar while TTS is active.

---

## 8. Emotional Intelligence in AI

### Detecting User State
Modern approaches move beyond simple sentiment (positive/negative) toward multi-dimensional detection:

- **Sarcasm**: Detected through contextual contradiction (positive words in negative context) and conversational history. JARVIS should not take sarcastic commands literally.
- **Frustration**: Tracked via "affective velocity" — how the emotional tone shifts across turns. Repeated short, clipped responses signal rising frustration.
- **Humor**: If the user makes a joke, the assistant should acknowledge the humor (at minimum) rather than answering literally.

### De-Escalation Patterns
A production-ready three-tier approach:

| Risk Level | Response Strategy |
|------------|-------------------|
| **Low** (normal frustration) | Standard response with empathetic framing |
| **Medium** (repeated frustration) | Empathetic de-escalation: acknowledge, apologize if warranted, offer solutions |
| **High** (anger, sustained frustration) | Pivot to direct action: "I understand you're frustrated. Let me fix this. What specifically do you need?" |

### Knowing When to Be Serious vs. Playful
- **Mirror the user's tone** — if they're serious, be serious. If they're playful, match that energy.
- **Default to helpful, not funny** — humor is welcome when invited, grating when forced.
- **Cultural note**: Slovak humor tends toward dry/sarcastic; English humor can be more varied. Adjust per language mode.

### Appropriate Emotional Responses
- **Acknowledge emotions without dwelling** — "That sounds frustrating. Let's see what we can do." Not "I'm so sorry you're feeling frustrated, that must be really difficult for you."
- **Respect user autonomy** — don't try to control the user's emotional state. Offer actions, not therapy.
- **For mistakes**: Apologize once, repair, move on. Repeated apologies feel manipulative.

### De-Escalation Script Patterns

| User Says | JARVIS Response Pattern |
|-----------|------------------------|
| "That's not what I asked" | Apologize + re-state understanding + offer corrected action |
| "Ugh, forget it" | Acknowledge frustration + leave the door open ("If you change your mind, let me know.") |
| Sarcastic command | Respond literally but with a light acknowledgment ("I'll take that as a no.") |
| Repeated same question | Check if the previous answer wasn't heard vs. wasn't understood — offer to rephrase |

---

## Synthesis: Design Principles for JARVIS

1. **One breath, one idea.** Every spoken response passes the one-breath test. Details go on the HUD.
2. **Mirror the user.** Language, tone, pacing — match what Fogy brings.
3. **Own mistakes, don't wallow.** Apologize once, repair, move forward.
4. **Memory is relationship.** Use the memory tool to bridge sessions. Call back shared context naturally.
5. **Voice first, HUD second.** The spoken interaction must work without the screen.
6. **Be the well-liked traveler.** Adaptable without pandering. Principled without lecturing. Helpful without sycophancy.
7. **Silence is a tool.** Pauses build trust. Don't fill every moment with sound.
8. **Know your boundaries.** "I don't know" builds more trust than a confident wrong answer.

---

## Sources

- Cathy Pearl, *Designing Voice User Interfaces: Principles of Conversational Experiences*
- James Giangola, "Speaking the Same Language" — Google Design VUI guidelines
- Amazon Alexa Voice Design Guide — developer.amazon.com/designing-for-voice/
- Nielsen Norman Group — "Intelligent Assistants Have Poor Usability" (Alexa, Siri, Google Assistant study)
- Mahmood et al., CHI 2022 — "Owning Mistakes Sincerely: Strategies for Mitigating AI Errors"
- AI & Society (2026) — "Apologizing artificial intelligence: designing and evaluating effective AI apologies"
- Fast Company — "Why 'I don't know' is the most valuable thing your AI can say"
- BODHI Framework — Harvard/MIT clinical AI uncertainty research
- Cihan et al., CUI 2022 — "Bilingual by default: Voice Assistants and the role of code-switching"
- AssemblyAI — "Multilingual Voice Agents: Build for Global Audiences"
- Amanda Askell — Claude's personality design philosophy (CMSWire, Time)
- Anthropic — Role Prompting & Prompt Engineering Tutorial
- Skywork AI — "AI Chatbot Character: Ultimate Guide" (CARE Pattern)
- SOUL.md / soul.md specifications — GitHub portable persona standards
- Baghdadi et al. (2025) — "Evaluating Rich Visual Feedback on Head-Up Displays for In-Vehicle Voice Assistants"
- Amazon Science — "Multimodal Context Carryover"
- IEEE (2025) — "Human-inspired Long-term Memory for Interactive Conversational Agents"
- AAAI (2024) — MemoryBank / SiliconFriend companion AI architecture
- Eros Engine — Open-source Rust engine for AI companions (six-dimensional affinity model)
- UC Irvine — "An AI That's a Better Friend" (social memory graph research)
- Twig — "How AI Handles Sarcasm, Slang, and Angry Customer Messages"
- GAUGE Framework — Logit-based detection of conversational escalation in LLMs
