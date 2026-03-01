# SP10: ChatGPT Export Format and Import Pipeline

**Date:** 2026-02-27
**Status:** Research complete — recommendation: extend existing script with `--format chatgpt` flag

---

## Summary

The ChatGPT data export uses a fundamentally different JSON structure than the Anthropic export, but the differences are mechanical and well-understood. The core divergence is the tree-encoded message graph (ChatGPT) versus a flat ordered array (Anthropic). Everything else the extraction pipeline needs — role-labeled turns, timestamps, conversation IDs — is present in both. A `--format chatgpt` flag in the existing `import-desktop-export.py` script, backed by a new `render_chatgpt_conversation()` function, is the right implementation path.

---

## Part 1: ChatGPT Export Format Specification

### How to Request an Export

1. Open ChatGPT in a browser (chat.openai.com)
2. Click your avatar → **Settings** → **Data controls**
3. Click **Export data** → confirm the dialog
4. OpenAI emails a download link (typically within minutes; may take hours for large histories)
5. Download the ZIP and extract it

The email link expires after a short window. For users with years of history, the ZIP can be hundreds of megabytes.

### Files in the Export ZIP

| File | Contents |
|---|---|
| `conversations.json` | All conversations — the primary file for import |
| `user.json` | Account metadata (name, email, phone) |
| `message_feedback.json` | Thumbs up/down ratings by message ID |
| `model_comparisons.json` | A/B comparison data (may be empty) |
| `chat.html` | Standalone HTML viewer for local browsing |
| `dalle/` | Subdirectory of DALL-E generated images (if any) |

The importer only needs `conversations.json`.

### Top-Level Structure

`conversations.json` is a JSON array of conversation objects. Each conversation looks like:

```json
{
  "id": "conv-abc123def456",
  "conversation_id": "conv-abc123def456",
  "title": "Python async patterns",
  "create_time": 1700000000.123,
  "update_time": 1700001234.456,
  "current_node": "msg-uuid-leaf",
  "gizmo_id": null,
  "moderation_results": [],
  "mapping": {
    "msg-uuid-root": { ... },
    "msg-uuid-2": { ... },
    "msg-uuid-leaf": { ... }
  }
}
```

**Key identity fields:**
- `id` and `conversation_id` are always identical — use either as the deduplication key
- `title` is the conversation title (user-editable; ChatGPT auto-generates it)
- `create_time` / `update_time` are Unix epoch **floats** (not ISO 8601 strings)
- `current_node` is the message ID of the leaf of the main branch
- `gizmo_id` is non-null for conversations with a custom GPT from the GPT Store

### The `mapping` Object — The Core Structural Difference

Unlike the Anthropic format's ordered `chat_messages` array, the ChatGPT format encodes conversations as a **flat dictionary of nodes** forming a tree. Each node has explicit `parent` and `children` references.

```json
"mapping": {
  "msg-uuid-1": {
    "id": "msg-uuid-1",
    "message": {
      "id": "msg-uuid-1",
      "author": {
        "role": "system",
        "metadata": {}
      },
      "content": {
        "content_type": "text",
        "parts": ["You are a helpful assistant."]
      },
      "create_time": null,
      "update_time": null,
      "status": "finished_successfully",
      "weight": 1.0,
      "metadata": {
        "model_slug": "gpt-4o",
        "is_visually_hidden_from_conversation": true
      }
    },
    "parent": null,
    "children": ["msg-uuid-2"]
  },
  "msg-uuid-2": {
    "id": "msg-uuid-2",
    "message": {
      "id": "msg-uuid-2",
      "author": { "role": "user", "metadata": {} },
      "content": {
        "content_type": "text",
        "parts": ["How do I use asyncio in Python?"]
      },
      "create_time": 1700000010.0,
      "update_time": null,
      "status": "finished_successfully",
      "weight": 1.0,
      "metadata": {}
    },
    "parent": "msg-uuid-1",
    "children": ["msg-uuid-3", "msg-uuid-3b"]
  },
  "msg-uuid-3": {
    "id": "msg-uuid-3",
    "message": {
      "id": "msg-uuid-3",
      "author": { "role": "assistant", "metadata": {} },
      "content": {
        "content_type": "text",
        "parts": ["Here's how asyncio works: asyncio is Python's standard library for..."]
      },
      "create_time": 1700000025.0,
      "update_time": null,
      "status": "finished_successfully",
      "weight": 1.0,
      "metadata": {
        "model_slug": "gpt-4o",
        "finish_details": { "type": "stop" }
      }
    },
    "parent": "msg-uuid-2",
    "children": []
  },
  "msg-uuid-3b": {
    "id": "msg-uuid-3b",
    "message": { ... },
    "parent": "msg-uuid-2",
    "children": [],
    "weight": 0.0
  }
}
```

**Reconstructing ordered turns from the tree:**

Walk from `current_node` back through `parent` links until reaching the root (null parent). Reverse the result to get chronological order. This is the canonical conversation thread. Branches not on the path to `current_node` are alternate regenerations — discard them.

```python
def extract_thread(mapping, current_node):
    thread = []
    node_id = current_node
    while node_id:
        node = mapping.get(node_id, {})
        thread.append(node)
        node_id = node.get("parent")
    thread.reverse()
    return thread
```

### Message Roles

| `author.role` | Meaning |
|---|---|
| `system` | System prompt (usually the first node; often default "helpful assistant" text) |
| `user` | Human turns |
| `assistant` | ChatGPT response turns |
| `tool` | Tool call results (code interpreter output, browsing results, image generation) |

### Content Types

Each message has a `content` object with a `content_type` discriminator:

| `content_type` | Description | `parts` structure |
|---|---|---|
| `text` | Normal text | `["the text string"]` — single-element list of strings |
| `code` | Code interpreter input | `[{"language": "python", "text": "print('hello')"}]` |
| `execution_output` | Code interpreter stdout/result | `[{"text": "hello\n"}]` |
| `tether_quote` | Web browsing citation | `[{"url": "...", "text": "...", "title": "..."}]` |
| `tether_browsing_display` | Browsing search results block | nested dict, not useful for extraction |
| `multimodal_text` | Mixed text + image upload | parts array mixing strings and `{"asset_pointer": "..."}` dicts |
| `dalle_image` | DALL-E generation | `[{"prompt": "...", "url": "...", "asset_pointer": "file-..."}]` |
| `system_error` | Tool error | `[{"text": "Error: ..."}]` |

For extraction purposes, only `content_type: text` from `role: user` and `role: assistant` nodes is reliably useful. The others are signals for filtering (see Part 3).

### Important Structural Quirks

1. **Null message nodes:** Some entries in `mapping` have `"message": null`. These are branching placeholders. Skip them when traversing.

2. **`parts` is always a list:** For text messages, `parts[0]` is the string. Never assume `parts` is a string directly.

3. **Empty `parts`:** Some messages have `parts: [""]` — an empty turn. Check for this and skip.

4. **Timestamp format:** `create_time` and `update_time` are Unix epoch floats, not ISO strings. Convert with `datetime.fromtimestamp(ts, tz=timezone.utc)`.

5. **Branching:** When a user edits a message or clicks "regenerate," the parent node gets multiple children. Only the branch that leads to `current_node` is canonical. The `weight` field on non-canonical branch nodes is often `0.0`, but using the `current_node` walk is more reliable.

6. **System prompt node:** The root node is almost always a `role: system` message. For standard ChatGPT conversations, `parts[0]` is `""` or `"You are a helpful assistant."` — not useful content. Skip system nodes during rendering.

7. **Missing `title`:** Some older conversations have `null` or empty titles. Default to `"Untitled"`.

8. **Shared GPT conversations:** `gizmo_id` is non-null for conversations using a custom GPT from the store. These have modified system prompts and may have unusual turn patterns.

---

## Part 2: Comparison to Anthropic Export Format

### Field Mapping

| Concept | Anthropic format | ChatGPT format |
|---|---|---|
| Conversation ID | `conv["uuid"]` (string) | `conv["id"]` or `conv["conversation_id"]` (same value) |
| Title | `conv["name"]` | `conv["title"]` |
| Last updated | `conv["updated_at"]` (ISO 8601 string) | `conv["update_time"]` (Unix float) |
| Messages | `conv["chat_messages"]` — ordered list | `conv["mapping"]` — flat dict, reconstruct via tree walk |
| Message role | `msg["sender"]` — values: `"human"`, `"assistant"` | `msg["author"]["role"]` — values: `"user"`, `"assistant"`, `"system"`, `"tool"` |
| Message text | `msg["content"][].type=="text"` blocks, or `msg["text"]` fallback | `msg["content"]["parts"][0]` where `content_type == "text"` |
| Timestamp | ISO 8601 string on `updated_at` | Unix float on `create_time` |
| Summary | `conv["summary"]` (sometimes present) | Not present |

### What the Existing Importer Reads (Anthropic Format)

From `import-desktop-export.py`:

- `conv["uuid"]` — deduplication key
- `conv["name"]` — display name and transcript header
- `conv["updated_at"]` — date filtering (`--since`/`--until`) and beat timestamps
- `conv["chat_messages"]` — the ordered message list
- `msg["sender"]` — maps `"human"` → `"Human"`, else → `"Assistant"` label
- `msg["content"]` — prefers `type=="text"` content blocks; falls back to `msg["text"]`
- `conv["summary"]` — included in transcript header if present

### Key Differences

**1. Message graph structure (major)**
The Anthropic format provides `chat_messages` as an ordered list — iterate directly. The ChatGPT format requires a tree walk from `current_node` back through `parent` links. This is the most significant implementation difference, but it's a contained ~15-line function.

**2. Timestamp format (minor)**
Anthropic uses ISO 8601 strings (`"2024-11-15T14:32:00.000Z"`). ChatGPT uses Unix epoch floats (`1731678720.0`). Need `datetime.fromtimestamp()` vs. `datetime.fromisoformat()`.

**3. Role naming (minor)**
Anthropic: `sender` field with `"human"` / `"assistant"`. ChatGPT: `author.role` with `"user"` / `"assistant"` / `"system"` / `"tool"`. Map `"user"` → `"Human"`, `"assistant"` → `"Assistant"`, skip `"system"` and `"tool"`.

**4. Text extraction (minor)**
Anthropic: `content` is a list of typed blocks; prefers `type=="text"` blocks, falls back to `msg["text"]`. ChatGPT: `content.parts[0]` where `content.content_type == "text"`. Slightly simpler — no fallback needed, just check `content_type`.

**5. No `summary` field (minor)**
Anthropic conversations sometimes have a `summary` field that `render_conversation()` includes in the transcript header. ChatGPT conversations have no equivalent. The transcript header will just omit this line.

**6. `conv["summary"]` absent → smaller transcript headers**
Minor — the extraction prompt doesn't depend on the summary being present.

### Verdict: Extend vs. New Script

**Extend the existing script with `--format chatgpt`.**

The differences are all in the parsing layer — two functions:
- `render_chatgpt_conversation()` — replaces `render_conversation()` for ChatGPT input
- `conversation_chatgpt_char_count()` — replaces `conversation_char_count()` for ChatGPT input

Everything else — state management, work queue, process_conversation(), deduplication, `--limit`/`--since`/`--until`/`--dry-run` flags, the beat extraction pipeline — is format-agnostic and works unchanged. There is no value in a separate script. The state file and all CLI flags are already correct for both formats.

The ID key difference (`"uuid"` vs. `"id"`) does require a small abstraction (`conv_id()` helper), but this is trivial.

---

## Part 3: Filtering Considerations

### High-Priority Filters (implement)

**1. DALL-E image generation conversations**
Conversations whose content_type messages are predominantly `dalle_image` produce no extractable text knowledge. A conversation where the only assistant turns are `content_type: "dalle_image"` should be filtered. Detection: if all assistant messages have `content_type != "text"`, skip.

Simpler heuristic: skip if `rendered_chars < min_chars` (the `--min-chars` filter already handles this implicitly, since DALL-E conversations render to very short text — mostly just the user prompt with no substantive assistant text).

**2. Very short conversations**
The existing `--min-chars 100` filter applies here. A two-turn "what's the capital of France?" exchange renders to ~60 characters and is correctly skipped.

**3. Purely creative writing**
Difficult to detect programmatically without an LLM call. Low priority: the extraction LLM (Haiku) already handles this gracefully — it produces zero beats from a short story or poem because none of the six beat types apply. The cost of an LLM call on a creative writing session is wasted, but this is a low-frequency case and not worth complex heuristics. The `--min-chars` filter catches very short creative prompts.

### Lower-Priority Filters (skip for now)

**Custom GPT conversations (`gizmo_id != null`)**
These use modified system prompts and may have unusual patterns (e.g., roleplay GPTs, customer service bots). The extraction LLM handles these adequately — it finds real knowledge if present, produces nothing if not. Not worth filtering.

**Code interpreter sessions**
These contain high-value technical knowledge (debugging, data analysis, algorithm development). The code content appears as `content_type: "code"` and `content_type: "execution_output"` in `tool` role messages, which the renderer can extract as text. These should not be filtered — they are among the highest-yield conversation types.

**Web browsing sessions**
Mixed yield. `tether_quote` blocks contain cited source text, not original user knowledge. The assistant's synthesis turn is usually `content_type: "text"` and does contain useful knowledge. Render only the text turns — the browsing artifact blocks can be skipped.

### Recommended Filter Set

```python
# Filter at conversation level (before LLM call)
skip_if:
  - no messages (empty mapping or no text-content messages after tree walk)
  - rendered text < min_chars (default 100)

# No conversation-type heuristics needed — let the extraction LLM do the work
```

---

## Part 4: Scale Considerations

### Expected Volume

Users with 2–4 year ChatGPT histories typically have 500–3,000 conversations. Power users may have 5,000+. The Anthropic importer's architecture handles this correctly (state file, resumable, `--limit` batching). The same approach works for ChatGPT.

### State File at Scale

The state file (`~/.claude/kg-import-state.json`) stores one record per conversation:

```json
{
  "conv-abc123": {
    "status": "ok",
    "beats_written": 3,
    "error": null,
    "name": "Python async patterns",
    "processed_at": "2026-02-27T10:00:00Z"
  }
}
```

At 5,000 conversations, each record ~200 bytes → ~1 MB total. JSON load and save at this size takes <50ms. No scale problem here. The existing state design works fine.

However, if the same state file is used for both Anthropic and ChatGPT imports, conversation IDs from both sources will coexist. Because both use UUIDs and both are guaranteed unique within their own systems, collisions are astronomically unlikely. Using the same state file is fine and avoids split-brain if the user re-imports after running both.

If isolation is preferred, add a `--state` flag override (already supported) and recommend separate state files: `kg-import-anthropic-state.json` and `kg-import-chatgpt-state.json`.

### Batch Size per LLM Call

The existing design is one conversation → one LLM extraction call. This is correct for ChatGPT import too. Multi-conversation batching is premature — it complicates error recovery and the `--limit` granularity. The `MAX_TRANSCRIPT_CHARS = 150_000` truncation limit handles unusually long conversations.

The default `--delay 2.0` seconds between API calls is reasonable for the `claude-cli` backend. For the `anthropic` SDK backend with rate limits, users should set `--delay 3.0` or higher for large imports.

---

## Recommended Implementation

### Architecture

Extend `import-desktop-export.py` with a `--format` flag:

```python
parser.add_argument(
    "--format", choices=["claude", "chatgpt"], default="claude",
    help="Export format: 'claude' (Anthropic) or 'chatgpt' (OpenAI) (default: claude)"
)
```

Add three new functions (replacing/augmenting the Anthropic-specific ones):

```python
def conv_id(conv: dict, fmt: str) -> str:
    """Return the conversation's unique identifier for the given format."""
    if fmt == "chatgpt":
        return conv.get("id") or conv.get("conversation_id", "")
    return conv["uuid"]  # Anthropic format

def extract_chatgpt_thread(mapping: dict, current_node: str) -> list[dict]:
    """Walk from current_node back through parent links; return ordered message list."""
    thread = []
    node_id = current_node
    while node_id:
        node = mapping.get(node_id)
        if node is None:
            break
        msg = node.get("message")
        if msg is not None:
            thread.append(msg)
        node_id = node.get("parent")
    thread.reverse()
    return thread

def render_chatgpt_message_text(msg: dict) -> str:
    """Extract clean text from a ChatGPT message object."""
    content = msg.get("content") or {}
    if content.get("content_type") != "text":
        return ""
    parts = content.get("parts") or []
    return "".join(p for p in parts if isinstance(p, str)).strip()

def chatgpt_conversation_char_count(conv: dict) -> int:
    """Count rendered text characters in a ChatGPT conversation."""
    mapping = conv.get("mapping") or {}
    current_node = conv.get("current_node", "")
    thread = extract_chatgpt_thread(mapping, current_node)
    return sum(len(render_chatgpt_message_text(m)) for m in thread)

def render_chatgpt_conversation(conv: dict) -> str:
    """
    Render a ChatGPT conversation to plain-text transcript for LLM extraction.

    Format matches render_conversation() output so the extraction pipeline
    receives identical input regardless of source format.
    """
    parts: list[str] = []

    title = conv.get("title") or "Untitled"
    update_time = conv.get("update_time")
    date = ""
    if update_time:
        dt = datetime.fromtimestamp(update_time, tz=timezone.utc)
        date = dt.strftime("%Y-%m-%d")

    parts.append(f"## {title}")
    if date:
        parts.append(f"Date: {date}")
    parts.append("")

    mapping = conv.get("mapping") or {}
    current_node = conv.get("current_node", "")
    thread = extract_chatgpt_thread(mapping, current_node)

    SKIP_ROLES = {"system", "tool"}

    for msg in thread:
        role = (msg.get("author") or {}).get("role", "")
        if role in SKIP_ROLES:
            continue
        label = "Human" if role == "user" else "Assistant"
        text = render_chatgpt_message_text(msg)
        if text:
            parts.append(f"**{label}:** {text}")
            parts.append("")

    rendered = "\n".join(parts).strip()

    if len(rendered) > MAX_TRANSCRIPT_CHARS:
        rendered = "...[earlier content truncated]...\n\n" + rendered[-MAX_TRANSCRIPT_CHARS:]

    return rendered
```

The `process_conversation()` and `build_work_queue()` functions use `conv["uuid"]` directly — update them to call `conv_id(conv, fmt)` instead, or pass the resolved ID as a parameter. This is the only change needed outside the new rendering functions.

The `--since`/`--until` date filtering needs a small adaptor for the epoch float:

```python
def conv_updated_date(conv: dict, fmt: str) -> str:
    """Return YYYY-MM-DD string for date filtering."""
    if fmt == "chatgpt":
        ts = conv.get("update_time") or conv.get("create_time") or 0
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
    return (conv.get("updated_at") or "")[:10]  # Anthropic format
```

### Default Project Name

For ChatGPT imports, use `--project-name chatgpt-import` as the default (or allow the user to override). Beats from ChatGPT will be labelled differently from Claude Desktop beats, keeping provenance clear in the vault.

### Suggested CLI Usage

```bash
# Dry run on first 10 ChatGPT conversations
python3 import-desktop-export.py conversations.json --format chatgpt --limit 10 --dry-run

# Process last year of ChatGPT conversations
python3 import-desktop-export.py conversations.json --format chatgpt --since 2025-01-01

# Full import with separate state file
python3 import-desktop-export.py conversations.json \
  --format chatgpt \
  --state ~/.claude/kg-import-chatgpt-state.json \
  --project-name chatgpt-import
```

---

## Gaps and Uncertainties

1. **Content types not validated against a live export.** The content type inventory above is drawn from community parsers and documentation through August 2025. OpenAI may have added new `content_type` values for newer model capabilities (o1 reasoning traces, o3 extended thinking, etc.). The renderer's `content_type != "text"` skip is forward-compatible — unknown types produce no text and are ignored.

2. **o1/o3 reasoning traces.** OpenAI's o1 and o3 models expose chain-of-thought reasoning in some contexts. These may appear as additional message nodes with special `content_type` values or `author.role: "assistant"` with metadata indicating they are thinking traces rather than final responses. Worth checking on a real export. They are likely to be low-signal for beat extraction (intermediate reasoning, not conclusions) and can be filtered by `metadata.is_visually_hidden_from_conversation: true`.

3. **`weight` field reliability.** The `weight` field (1.0 for canonical branch, 0.0 for discarded regenerations) is present in most community-documented exports but its presence is not guaranteed. The `current_node` walk approach is safer and does not depend on `weight`.

4. **Large export ZIPs.** Users with thousands of DALL-E images may have very large `dalle/` subdirectories in the ZIP, but these don't affect `conversations.json` loading. The importer loads the JSON file directly and does not process the ZIP — users must extract it first. This matches the existing Anthropic workflow.

5. **Rate of format change.** OpenAI has changed the export format at least once (the original format did not have the `mapping` tree structure; older exports may be flat arrays). If a user has a very old export, the structure may differ. A format detection check (does `"mapping"` key exist at conversation level?) could handle this gracefully.
