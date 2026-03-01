# SP5: Additional Data Source Research

**Date:** 2026-02-27
**Status:** Complete
**Spike:** SP5 — Additional data source research

---

## Summary

Seven data sources evaluated for feasibility of feeding into the knowledge-graph pipeline. Ranked by the product of (access feasibility) × (expected knowledge value). Claude.ai mobile is the highest-priority gap and has a viable near-term path via periodic batch export. A browser extension for desktop Claude.ai is a higher-fidelity but higher-effort alternative. ChatGPT import is nearly free given the existing pipeline. Everything else degrades quickly in value-to-effort ratio.

---

## Ranked Source List

### 1. Claude.ai Mobile and Web — PURSUE NOW

**Verdict: Pursue now (batch export path). Pursue later (browser extension path).**

**Why it ranks first:** This is where the user already spends significant time. Sessions on Claude.ai (web and iOS app) produce no vault beats today. This is not an edge case — it is a primary interface gap. Every conversation on the phone disappears.

**Access method — Batch export (viable now):**

Anthropic provides a GDPR/CCPA-compliant data export at `claude.ai/settings` → Privacy → Export Data (or via `privacy.anthropic.com`). The export is a ZIP file delivered by email, typically within a few hours of request. The core artifact is `conversations.json`.

The existing codebase already reveals the complete `conversations.json` schema from the import script (`/Users/dan/code/knowledge-graph/scripts/import-desktop-export.py`):

```json
[
  {
    "uuid": "...",
    "name": "conversation title",
    "summary": "auto-generated summary",
    "updated_at": "2025-08-15T14:23:00Z",
    "chat_messages": [
      {
        "sender": "human",
        "text": "...",
        "content": [
          { "type": "text", "text": "..." },
          { "type": "tool_use", "..." }
        ]
      },
      {
        "sender": "assistant",
        "text": "...",
        "content": [
          { "type": "text", "text": "..." }
        ]
      }
    ]
  }
]
```

Key properties the importer already handles:
- `content[].type == "text"` blocks preferred over top-level `text` field (the latter contains "This block is not supported" artifacts for tool messages)
- Conversations sorted by `updated_at`
- Per-conversation `uuid` used as deduplication key in the state file

**Critical finding:** The export covers ALL Claude interfaces — web, mobile (iOS/Android), and Claude Desktop. There is no interface-specific filtering. A conversation started on iPhone and continued on the web appears as a single conversation in the export. This means the batch export path immediately solves the mobile gap.

**What does NOT work today for mobile:**
- No public API for real-time conversation access. The Anthropic API (`api.anthropic.com`) is for building on top of Claude, not for reading back conversation history.
- No webhook for "conversation ended" events.
- No iOS Share Sheet or Shortcuts integration in the Claude iOS app as of the knowledge cutoff. The iOS app does not expose conversation content to iOS automation.
- No background sync. Export is pull-only, user-initiated, and delivered via email.

**Access method — Browser extension (desktop web, higher fidelity):**

A Chrome/Firefox extension with `activeTab` permission can read the Claude.ai DOM. The conversation transcript is rendered as HTML in the page and is accessible to content scripts. A content script could:
1. Parse the conversation DOM on page unload or on a manual trigger
2. POST the transcript to a local server (e.g., `localhost:PORT` run by a small companion script) or write to a file via the Native Messaging API
3. The companion script calls `extract_beats.py`

Technical constraints:
- Claude.ai does not use a Content Security Policy that blocks content scripts from reading page DOM. CSP only restricts what the *page itself* can load, not what extensions can read.
- Native Messaging requires a host manifest registered on the OS — doable but adds install complexity.
- A simpler approach: the extension copies the transcript to clipboard or triggers a download of a text file, which the user manually runs through `/kg-extract`.
- Real-time (per-message) extraction would require intercepting XHR/fetch responses, which is more complex but technically possible via a service worker.

**Blockers:**
- Batch export: None. Works today. Requires periodic manual export request (once a week or once a month). Frequency is the only friction.
- Browser extension: Build effort (~1-2 days for a minimal version). Not on iOS — Safari extensions on iOS have significant restrictions and the Claude.ai mobile web experience is limited.

**Format compatibility:** The existing `import-desktop-export.py` already handles the exact format the export produces. The pipeline is ready. No new parser needed.

**Recommended near-term path:**
1. Document the batch export workflow for the user (request → download → run import script). This costs zero development effort and closes the gap immediately.
2. Add a `--source` flag or separate import script for future sources so the state file tracks conversations by source.
3. Longer-term: build a minimal browser extension that captures conversations from desktop Claude.ai on demand (button in extension popup), writing a transcript file that `extract_beats.py` can process directly.

---

### 2. ChatGPT Export — PURSUE NOW

**Verdict: Pursue now. Marginal effort, high yield for users with ChatGPT history.**

**Access method:**

ChatGPT provides a data export at `chatgpt.com/settings` → Data Controls → Export Data. Delivered as a ZIP within hours. The key file is `conversations.json`.

**ChatGPT conversations.json structure** (differs from Claude's format):

```json
[
  {
    "id": "...",
    "title": "conversation title",
    "create_time": 1700000000.0,
    "update_time": 1700001000.0,
    "mapping": {
      "<node-id>": {
        "id": "<node-id>",
        "parent": "<parent-node-id>",
        "children": ["<child-node-id>"],
        "message": {
          "id": "...",
          "author": { "role": "user" | "assistant" | "system" | "tool" },
          "content": {
            "content_type": "text" | "tether_browsing_display" | "code" | "multimodal_text",
            "parts": ["text content here"]
          },
          "create_time": 1700000500.0,
          "status": "finished_successfully"
        }
      }
    },
    "conversation_template_id": null,
    "gizmo_id": null
  }
]
```

Key structural differences from Claude's format:
- **Tree structure, not array**: Messages are stored as a graph (`mapping` dict with parent/child pointers) to support conversation branching. A linear transcript requires a tree traversal from root to leaf.
- **Timestamps**: Unix epoch floats, not ISO strings.
- **Content parts**: Text is in `content.parts[]` (array), not a top-level `text` field.
- **Author roles**: `"user"` / `"assistant"` (not `"human"` / `"assistant"` as in Claude).
- **No summary field**: Claude exports include an auto-generated `summary`; ChatGPT does not.
- **Tool messages present**: `content_type: "tether_browsing_display"` for browsing tool results, code interpreter outputs, etc. These should be skipped or truncated, analogous to how the Claude importer skips `tool_use` blocks.
- **GPT-4o image generation**: Appears as messages with `content_type: "multimodal_text"` containing image references. These produce no useful beats and should be filtered.

**Adaptation effort:**

The existing `import-desktop-export.py` cannot be used directly — the tree traversal and field mapping are different enough to require a separate `import-chatgpt-export.py`. However, the extraction engine (`extract_beats.py`) is format-agnostic: it takes a rendered plain-text transcript string. The new script only needs to:
1. Walk the message tree (depth-first from root, follow `children[0]` for linear conversations)
2. Skip non-text content types
3. Render to the same `**Human:** / **Assistant:**` format the extractor expects
4. Call `extract_beats.py` with the rendered transcript

Estimated effort: ~1 day for a clean implementation with state tracking.

**Content quality:** ChatGPT conversations skew technical for users who use it for coding and research — exactly the kind of content that produces good beats. Creative writing, image generation, and casual Q&A should be filtered by the existing `--min-chars` threshold and the LLM's own judgment during extraction.

**Blockers:** None. Export is publicly available, format is well-documented, extraction pipeline is ready.

---

### 3. Obsidian Web Clipper (Browser Extension) — PURSUE NOW (already exists)

**Verdict: Pursue now — this already exists and requires no custom development.**

**What it is:**

Obsidian released an official Web Clipper browser extension (Chrome, Firefox, Safari) in late 2024. It captures web page content and saves it directly to a local Obsidian vault via the Obsidian URI protocol or the Local REST API plugin.

**What it captures:**
- Full page content converted to Markdown
- Selected text only (if text is highlighted before clipping)
- Page metadata: title, URL, author, publication date
- User-defined templates for different content types

**How it integrates:**
- On click, opens a popup showing a Markdown preview of the captured content
- Saves directly to the vault as a `.md` file in a configurable folder
- Supports Obsidian templates with variables (`{{title}}`, `{{url}}`, `{{date}}`, `{{content}}`)

**Relevance to this project:**

Web Clipper captures to the vault but does not pass content through `extract_beats.py`. Clipped pages land as raw notes, not as structured beats with frontmatter. Two options:
1. Use the existing `/kg-file` command in a Claude Code session to process a clipped note into beats after the fact.
2. Configure the Web Clipper template to produce frontmatter that approximates the beat format — a partial solution.
3. Longer-term: the SP13 (auto-enrichment) feature would process these raw clipped notes into proper beats automatically.

**Verdict nuance:** Web Clipper is immediately useful for capturing web research, but it doesn't close the loop into the beat pipeline without additional steps. It's a good complementary tool but not a primary beat source.

---

### 4. Voice Memos / Meeting Transcripts — PURSUE LATER

**Verdict: Pursue later. Transcription tools exist; integration requires orchestration work.**

**Apple Voice Memos:**
- No public API. Voice Memos is a sandboxed iOS/macOS app with no programmatic access to recordings.
- iOS Shortcuts *cannot* directly access Voice Memos recordings as of iOS 17/18. The app does not expose a Shortcuts action for reading audio content.
- Manual workaround: user exports a recording from Voice Memos → AirDrop or Files app → run through Whisper.

**iOS Shortcuts + Whisper path:**
- iOS Shortcuts has a "Transcribe Audio" action (uses on-device speech recognition, not Whisper) available since iOS 16. It can transcribe a selected audio file.
- The transcribed text can be sent to a webhook, saved to a file, or passed to another app via Share Sheet.
- A Shortcut could: select audio → transcribe → send to a local server running on the Mac (via direct HTTP if on same Wi-Fi) → server calls `extract_beats.py`.
- Limitation: iOS on-device transcription quality is speaker-dependent and worse than Whisper for technical content. It struggles with code-heavy or jargon-heavy conversation.

**Whisper (OpenAI) — local transcription:**
- `whisper` CLI and Python library accept audio files in most common formats (m4a, mp3, wav, etc.).
- Output: plain text transcript, or structured JSON with timestamps per segment.
- Quality: significantly better than iOS on-device for technical content. The `medium` or `large-v3` model is appropriate for technical speech.
- Integration path: `whisper audio.m4a --output_format txt` → output file → `extract_beats.py --transcript output.txt`
- Fully compatible with the extractor's plain-text mode (the extractor already handles non-JSONL input as plain text).
- Runs locally, no API key needed if using `openai-whisper` library.

**Meeting transcription services (Otter.ai, Fireflies.ai, Grain):**
- Otter.ai: Has a paid API (`otter.ai/api`) for enterprise, not available on free/basic plans. Export format is structured JSON with speaker diarization and timestamped segments.
- Fireflies.ai: REST API available on Growth plan and above. Webhooks fire when a transcript is completed. Output is JSON with speaker labels and full transcript text.
- Grain: No public API. Export is manual (PDF, DOCX, or copy-paste).

**Realistic path today:**
1. Record voice memo → export audio file → run `whisper` locally → feed plain-text output to `extract_beats.py`. Works now, manual.
2. If using Otter or Fireflies: configure webhook to POST transcript JSON to a local receiver → receiver calls extractor. Requires a paid tier and a running local server.
3. iOS Shortcut for the full flow (voice → transcribe → extract) is feasible but requires the Mac to be reachable on local network or via a cloud relay.

**Why pursue later:** The tap-to-capture friction on mobile is high. A voice memo workflow requires 3-5 manual steps. The user's highest-value gap (Claude.ai mobile sessions) is more important and much easier to close. Voice capture is compelling for meeting transcripts specifically, but that requires a meeting transcription service subscription.

---

### 5. Slack — PURSUE LATER (personal use) / NOT WORTH IT (workspace use)

**Verdict: Pursue later for personal/DM content only. Not worth it for workspace messages.**

**Access methods:**

Personal Slack messages (DMs, personal channel posts) can be accessed via the Slack API with a user token:
- OAuth scope required: `channels:history` (public channels), `groups:history` (private channels), `im:history` (DMs), `mpim:history` (group DMs)
- A personal token (created via a custom Slack app you install to your own workspace, or via legacy tokens for personal workspaces) can read your own messages.
- **No workspace admin access required** for your own DMs and channels you're a member of.
- Export format: JSON with `ts` (Unix timestamp), `user`, `text`, `thread_ts`, and `blocks` (rich text blocks for newer messages).

**Blockers:**

- **Workplace Slack:** Most enterprise Slack workspaces restrict the ability to create custom apps or use personal API tokens. Data sovereignty policies may prohibit exporting message content. This is a policy blocker, not a technical one.
- **Signal-to-noise:** Slack conversations are high-volume, low-signal relative to LLM sessions. Most messages are coordination ("can you review PR #123", "lunch?") rather than knowledge worth filing. The LLM extraction would produce poor yield per conversation processed.
- **Thread structure:** Threads are stored separately from main channel history and require a second API call (`conversations.replies`) per thread. The rendering logic is non-trivial.
- **Personal Slack:** If the user has a personal or small-team Slack, the signal-to-noise is better and technical API access is easier. Worth considering for workspaces where substantive technical discussion happens.

**Recommended framing:** Slack is most useful as a *manual* source — the user pastes a relevant Slack thread into `/kg-file` when it contains something worth saving, rather than bulk-importing all messages. This costs zero engineering effort and gets 90% of the value.

---

### 6. iMessage — NOT WORTH IT

**Verdict: Not worth it.**

**Access methods:**

On macOS, iMessage history is stored in a SQLite database at `~/Library/Messages/chat.db`. The schema is complex but documented (tables: `message`, `chat`, `handle`, `attachment`). Reading it requires Full Disk Access permission on macOS 10.14+.

**Blockers:**
- **Full Disk Access:** Requires granting the terminal or script Full Disk Access in System Preferences. This is a significant security gate and will break on OS updates.
- **iOS:** No programmatic access to iMessage history on iOS. The Messages app is sandboxed. No Shortcuts actions for reading message content.
- **Signal-to-noise:** Personal text messages are overwhelmingly low-signal for a knowledge vault. Technical discussions do occasionally happen over iMessage, but they are rare and fragmented.
- **Privacy:** Importing personal message history into an LLM extraction pipeline creates real privacy exposure — the pipeline reads content from *other* people who did not consent to this.

The combination of platform friction, poor signal, and privacy concerns makes this a poor candidate.

---

### 7. WhatsApp — NOT WORTH IT

**Verdict: Not worth it.**

**Access methods:**

WhatsApp provides a manual export: open a chat → More → Export Chat → Without Media. This produces a `.txt` file in a structured but informal format:

```
[2025-08-15, 14:23:45] Dan: here's the thing about the architecture
[2025-08-15, 14:24:01] Other Person: makes sense, what about the cache layer?
```

**Blockers:**
- **Manual per-chat export:** No API. No bulk export. Each chat must be exported individually from within the app. There is no WhatsApp web API for conversation history.
- **WhatsApp Business API:** Provides webhooks for incoming messages, but only for business accounts receiving customer messages — not for personal conversation history.
- **Signal-to-noise:** Same problem as iMessage. Personal WhatsApp chats are low-signal for a knowledge vault.
- **Privacy:** Same concerns as iMessage — other participants' messages would be ingested without their knowledge.

The export format is parseable (regex on the timestamp+name pattern), but the access friction and poor signal make it not worth building.

---

## Feasibility × Value Matrix

| Source | Access Feasibility | Expected Value | Effort to Integrate | Verdict |
|---|---|---|---|---|
| Claude.ai mobile/web (batch export) | High — export exists today | Very High — primary interface | Low — pipeline ready | **Pursue now** |
| Claude.ai desktop (browser extension) | Medium — build required | High — real-time capture | Medium — ~2 days | **Pursue later** |
| ChatGPT export | High — export exists | High — years of history | Low-Medium — new parser | **Pursue now** |
| Obsidian Web Clipper | High — already exists | Medium — raw clips, not beats | Zero — already built | **Pursue now** |
| Voice / Whisper | Medium — manual pipeline | Medium — meeting capture | Medium — orchestration | **Pursue later** |
| Slack (personal/small team) | Medium — API available | Low-Medium — noisy | Medium | **Pursue later** |
| Slack (enterprise workspace) | Low — policy blocked | Low-Medium — noisy | High | **Not worth it** |
| iMessage | Low — macOS only, FDA required | Low — poor signal | High | **Not worth it** |
| WhatsApp | Low — manual per-chat | Low — poor signal | Medium | **Not worth it** |

---

## Recommended Action Sequence

### Immediate (zero or near-zero development effort)

1. **Document the Claude.ai batch export workflow.** The pipeline already supports the exact format. The user requests an export from `claude.ai/settings`, downloads the ZIP, and runs `import-desktop-export.py`. This closes the mobile gap today. Friction: periodic manual export request.

2. **Run a ChatGPT import.** Write `import-chatgpt-export.py` — a new script that walks the ChatGPT message tree and renders to the same transcript format the extractor expects. The extraction engine (`extract_beats.py`) requires no changes.

3. **Install Obsidian Web Clipper.** Official extension, no custom code. Captures web research to vault. Not beats, but enrichable later (SP13).

### Short-term (1-2 days of build)

4. **Browser extension for Claude.ai desktop.** A minimal Chrome extension with a "Capture this conversation" button that reads the DOM and either downloads a transcript file or sends it to a local companion. Closes the real-time gap on desktop without waiting for a full export cycle. Does not help on iOS.

5. **iOS Shortcut: voice → Whisper → extract.** A Shortcut that exports a Voice Memo audio file, runs it through a local `whisper` call (via SSH or a local server on Mac), and feeds the transcript to `extract_beats.py`. Useful for meeting debrief or idea capture while mobile.

### Not now

6. Slack, iMessage, WhatsApp — reassess only if the user's conversation patterns shift to include substantive technical discussion in these channels. The manual `/kg-file` path handles the occasional high-value message from these sources without bulk-import infrastructure.

---

## Key Finding on Claude.ai Export Coverage

The Anthropic data export is **not** restricted to Claude Desktop or Claude Code. It includes all conversations from all interfaces: Claude.ai web, Claude iOS app, Claude Android app, and Claude Desktop. The `conversations.json` format is identical regardless of which interface was used. The existing `import-desktop-export.py` script processes this file correctly already. The only change needed is user documentation explaining how to request the export and how frequently to do it.

---

## Sources

- `/Users/dan/code/knowledge-graph/scripts/import-desktop-export.py` — Reveals the Anthropic `conversations.json` schema from its parsing logic (`render_message_text`, `render_conversation`, field access patterns)
- `/Users/dan/code/knowledge-graph/steering/SPIKES.md` — SP5 specification
- `/Users/dan/code/knowledge-graph/steering/OVERVIEW.md` — System context
- ChatGPT export format: documented community analysis of `conversations.json` mapping/tree structure; consistent across multiple sources in training data through August 2025
- Obsidian Web Clipper: announced and released by Obsidian in late 2024, available at obsidian.md/clipper
- Slack API: `conversations.history` endpoint, OAuth scope requirements documented at api.slack.com
- Whisper: openai/whisper GitHub repository, CLI and Python API
- Apple Voice Memos / iOS Shortcuts: iOS 16-18 feature documentation
- Note: WebSearch and WebFetch were unavailable in this research session. Findings on external services draw on training knowledge through August 2025. The Anthropic export format is verified directly from the codebase.
