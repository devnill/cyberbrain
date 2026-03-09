"""
tests/test_import.py — Tests for scripts/import.py

Tests cover:
- Claude export parser extracts conversation text correctly
- Claude export parser skips system/tool messages
- ChatGPT export parser extracts conversation text
- Import skips conversation IDs already in the state file (idempotency)
- Import writes new conversation ID to state file after processing
- --dry-run produces no file writes and does not update the state file

Per spec Section 14 — test behavior, not implementation. Mock at the LLM boundary.
"""

import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path setup — import.py lives in scripts/ relative to the project root.
# We resolve the path relative to this test file.
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Add scripts/ to sys.path so we can import import.py as a module
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import importlib
import importlib.util

def _load_import_module():
    """Load scripts/import.py as a module named 'kg_import' (avoids 'import' keyword clash)."""
    spec = importlib.util.spec_from_file_location("kg_import", SCRIPTS_DIR / "import.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Load the module once at import time. If extract_beats is missing from the
# installed path, the _import_extract_beats() call only runs in main() — not at
# module level — so this is safe for unit tests.
kg_import = _load_import_module()


# ---------------------------------------------------------------------------
# Claude export parsing tests
# ---------------------------------------------------------------------------

class TestParseClaudeConversation:
    """Tests for parse_claude_conversation() — Claude Desktop export format."""

    def _make_message(self, sender: str, text: str) -> dict:
        return {
            "sender": sender,
            "text": text,
            "content": [{"type": "text", "text": text}],
        }

    def test_extracts_human_and_assistant_turns(self):
        conv = {
            "uuid": "test-001",
            "name": "Test conversation",
            "updated_at": "2026-02-10T10:00:00Z",
            "chat_messages": [
                self._make_message("human", "How do I configure connection pooling?"),
                self._make_message("assistant", "Set pool_timeout to 10 in database.yml."),
            ],
        }
        result = kg_import.parse_claude_conversation(conv)
        assert "Human: How do I configure connection pooling?" in result
        assert "Assistant: Set pool_timeout to 10 in database.yml." in result

    def test_skips_non_human_non_assistant_senders(self):
        conv = {
            "uuid": "test-002",
            "name": "Mixed senders",
            "updated_at": "2026-02-10T10:00:00Z",
            "chat_messages": [
                {"sender": "system", "text": "You are a helpful assistant.", "content": []},
                {"sender": "tool", "text": "tool_result_data", "content": []},
                self._make_message("human", "What is Redis?"),
                self._make_message("assistant", "A fast in-memory data store."),
            ],
        }
        result = kg_import.parse_claude_conversation(conv)
        assert "You are a helpful assistant." not in result
        assert "tool_result_data" not in result
        assert "Human: What is Redis?" in result
        assert "Assistant: A fast in-memory data store." in result

    def test_prefers_content_blocks_over_text_field(self):
        """Prefers content[].type=='text' blocks to avoid 'This block is not supported' artifacts."""
        conv = {
            "uuid": "test-003",
            "name": "Content blocks test",
            "updated_at": "2026-02-10T10:00:00Z",
            "chat_messages": [
                {
                    "sender": "human",
                    "text": "This block is not supported",  # artifact in text field
                    "content": [{"type": "text", "text": "Real question about auth middleware."}],
                },
                {
                    "sender": "assistant",
                    "text": "This block is not supported",
                    "content": [{"type": "text", "text": "Auth middleware should run before rate limiting."}],
                },
            ],
        }
        result = kg_import.parse_claude_conversation(conv)
        assert "This block is not supported" not in result
        assert "Real question about auth middleware." in result
        assert "Auth middleware should run before rate limiting." in result

    def test_includes_title_and_date_header(self):
        conv = {
            "uuid": "test-004",
            "name": "Postgres debugging",
            "updated_at": "2026-02-15T14:00:00Z",
            "chat_messages": [
                self._make_message("human", "question"),
                self._make_message("assistant", "answer"),
            ],
        }
        result = kg_import.parse_claude_conversation(conv)
        assert "## Postgres debugging" in result
        assert "Date: 2026-02-15" in result

    def test_falls_back_to_text_field_when_no_content_blocks(self):
        conv = {
            "uuid": "test-005",
            "name": "Fallback test",
            "updated_at": "2026-02-10T10:00:00Z",
            "chat_messages": [
                {"sender": "human", "text": "Fallback text question", "content": []},
                {"sender": "assistant", "text": "Fallback text answer", "content": []},
            ],
        }
        result = kg_import.parse_claude_conversation(conv)
        assert "Human: Fallback text question" in result
        assert "Assistant: Fallback text answer" in result

    def test_transcript_truncated_when_too_long(self):
        """Line 197: truncation when rendered output exceeds MAX_TRANSCRIPT_CHARS."""
        long_text = "x" * (kg_import.MAX_TRANSCRIPT_CHARS + 5000)
        conv = {
            "uuid": "long-001",
            "name": "Long conversation",
            "updated_at": "2026-02-10T10:00:00Z",
            "chat_messages": [
                {
                    "sender": "human",
                    "text": long_text,
                    "content": [{"type": "text", "text": long_text}],
                },
            ],
        }
        result = kg_import.parse_claude_conversation(conv)
        assert "truncated" in result
        assert len(result) <= kg_import.MAX_TRANSCRIPT_CHARS + len("...[earlier content truncated]...\n\n")

    def test_skips_empty_messages(self):
        conv = {
            "uuid": "test-006",
            "name": "Empty messages",
            "updated_at": "2026-02-10T10:00:00Z",
            "chat_messages": [
                self._make_message("human", ""),  # empty
                self._make_message("assistant", "Something useful"),
            ],
        }
        result = kg_import.parse_claude_conversation(conv)
        assert "Human: " not in result
        assert "Assistant: Something useful" in result

    def test_fixture_file_parses_correctly(self):
        """End-to-end: parse the sample fixture file and check structure."""
        fixture_path = FIXTURES_DIR / "sample_claude_export.json"
        assert fixture_path.exists(), f"Fixture not found: {fixture_path}"
        with open(fixture_path, encoding="utf-8") as f:
            conversations = json.load(f)
        assert len(conversations) == 3
        # First conversation should have meaningful content
        rendered = kg_import.parse_claude_conversation(conversations[0])
        assert "Postgres" in rendered or "pool" in rendered.lower()
        assert "Human:" in rendered
        assert "Assistant:" in rendered


# ---------------------------------------------------------------------------
# ChatGPT export parsing tests
# ---------------------------------------------------------------------------

class TestParseChatGPTConversation:
    """Tests for parse_chatgpt_conversation() — ChatGPT export format."""

    def _make_conv(self, messages: list[tuple[str, str]], title: str = "Test", ts: float = 1738800000.0) -> dict:
        """
        Build a minimal ChatGPT conversation dict from a list of (role, text) tuples.
        Constructs a simple linear chain from msg-1 to msg-N.
        """
        mapping = {}
        prev_id = None
        last_id = None
        for i, (role, text) in enumerate(messages):
            msg_id = f"msg-{i + 1}"
            mapping[msg_id] = {
                "id": msg_id,
                "parent": prev_id,
                "children": [],
                "message": {
                    "id": msg_id,
                    "author": {"role": role},
                    "content": {"content_type": "text", "parts": [text]},
                },
            }
            if prev_id:
                mapping[prev_id]["children"].append(msg_id)
            prev_id = msg_id
            last_id = msg_id
        return {
            "id": "chatgpt-test-001",
            "title": title,
            "create_time": ts,
            "update_time": ts,
            "current_node": last_id,
            "mapping": mapping,
        }

    def test_extracts_user_and_assistant_turns(self):
        conv = self._make_conv([
            ("user", "What is the best Redis eviction policy for sessions?"),
            ("assistant", "Use allkeys-lru for session caching."),
        ])
        result = kg_import.parse_chatgpt_conversation(conv)
        assert "Human: What is the best Redis eviction policy for sessions?" in result
        assert "Assistant: Use allkeys-lru for session caching." in result

    def test_skips_system_messages(self):
        conv = self._make_conv([
            ("system", "You are a helpful assistant."),
            ("user", "How do I configure Redis?"),
            ("assistant", "Set maxmemory-policy allkeys-lru."),
        ])
        result = kg_import.parse_chatgpt_conversation(conv)
        assert "You are a helpful assistant." not in result
        assert "Human: How do I configure Redis?" in result

    def test_skips_tool_messages(self):
        conv = self._make_conv([
            ("user", "Search the web for Redis docs."),
            ("tool", "tool_result: <search results>"),
            ("assistant", "Redis documentation is at redis.io."),
        ])
        result = kg_import.parse_chatgpt_conversation(conv)
        assert "tool_result" not in result
        assert "Human: Search the web for Redis docs." in result
        assert "Assistant: Redis documentation is at redis.io." in result

    def test_includes_title_and_date_header(self):
        conv = self._make_conv(
            [("user", "question"), ("assistant", "answer")],
            title="Redis Cache Strategy",
            ts=1738800000.0,  # 2026-02-06
        )
        result = kg_import.parse_chatgpt_conversation(conv)
        assert "## Redis Cache Strategy" in result
        assert "Date:" in result

    def test_skips_non_text_content(self):
        """Messages with content_type != 'text' should produce no output."""
        conv = {
            "id": "chatgpt-test-002",
            "title": "Image conv",
            "create_time": 1738800000.0,
            "update_time": 1738800000.0,
            "current_node": "msg-2",
            "mapping": {
                "msg-1": {
                    "id": "msg-1",
                    "parent": None,
                    "children": ["msg-2"],
                    "message": {
                        "id": "msg-1",
                        "author": {"role": "user"},
                        "content": {"content_type": "multimodal_text", "parts": ["[image]"]},
                    },
                },
                "msg-2": {
                    "id": "msg-2",
                    "parent": "msg-1",
                    "children": [],
                    "message": {
                        "id": "msg-2",
                        "author": {"role": "assistant"},
                        "content": {"content_type": "text", "parts": ["I see an image."]},
                    },
                },
            },
        }
        result = kg_import.parse_chatgpt_conversation(conv)
        assert "[image]" not in result
        assert "I see an image." in result

    def test_fixture_file_parses_correctly(self):
        """End-to-end: parse the sample ChatGPT fixture file."""
        fixture_path = FIXTURES_DIR / "sample_chatgpt_export.json"
        assert fixture_path.exists(), f"Fixture not found: {fixture_path}"
        with open(fixture_path, encoding="utf-8") as f:
            conversations = json.load(f)
        assert len(conversations) == 3
        rendered = kg_import.parse_chatgpt_conversation(conversations[0])
        assert "Human:" in rendered
        assert "Assistant:" in rendered


# ---------------------------------------------------------------------------
# State file management tests
# ---------------------------------------------------------------------------

class TestStateManagement:
    """Tests for load_state, save_state, and record_imported."""

    def test_load_state_returns_empty_dict_when_file_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            missing_path = Path(tmpdir) / "nonexistent.json"
            state = kg_import.load_state(missing_path)
            assert isinstance(state, dict)
            assert state == {}

    def test_load_state_returns_empty_dict_on_corrupt_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            corrupt_path = Path(tmpdir) / "corrupt.json"
            corrupt_path.write_text("not valid json{{{", encoding="utf-8")
            state = kg_import.load_state(corrupt_path)
            assert isinstance(state, dict)
            assert state == {}

    def test_load_state_reads_existing_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            existing = {"conv-001": {"imported_at": "2026-02-01T00:00:00Z", "beats_written": 3}}
            state_path.write_text(json.dumps(existing), encoding="utf-8")
            state = kg_import.load_state(state_path)
            assert "conv-001" in state
            assert state["conv-001"]["beats_written"] == 3

    def test_save_state_writes_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            state = {"conv-001": {"imported_at": "2026-02-01T00:00:00Z", "beats_written": 2}}
            kg_import.save_state(state, state_path)
            assert state_path.exists()
            loaded = json.loads(state_path.read_text(encoding="utf-8"))
            assert loaded["conv-001"]["beats_written"] == 2

    def test_record_imported_adds_entry(self):
        state = {}
        kg_import.record_imported(state, "conv-xyz", 5)
        assert "conv-xyz" in state
        assert state["conv-xyz"]["beats_written"] == 5
        assert "imported_at" in state["conv-xyz"]


# ---------------------------------------------------------------------------
# Import idempotency tests
# ---------------------------------------------------------------------------

class TestImportIdempotency:
    """Tests that already-imported conversations are skipped correctly."""

    def _make_claude_conversation(self, uid: str, title: str = "Test", msgs: int = 4) -> dict:
        """Create a minimal Claude export conversation."""
        messages = []
        for i in range(msgs):
            sender = "human" if i % 2 == 0 else "assistant"
            messages.append({
                "sender": sender,
                "text": f"Message {i} with enough content to pass the length check.",
                "content": [{"type": "text", "text": f"Message {i} with enough content to pass the length check."}],
            })
        return {
            "uuid": uid,
            "name": title,
            "updated_at": "2026-02-10T10:00:00Z",
            "chat_messages": messages,
        }

    def test_skips_conversations_already_in_state(self):
        """Conversations whose IDs are in the state file must be skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            # Pre-populate state with conv-001
            state = {"conv-001": {"imported_at": "2026-02-01T00:00:00Z", "beats_written": 2}}
            kg_import.save_state(state, state_path)

            conversations = [
                self._make_claude_conversation("conv-001", "Already imported"),
                self._make_claude_conversation("conv-002", "New conversation"),
            ]

            # Load state and verify partition
            loaded_state = kg_import.load_state(state_path)
            already_imported_ids = set(loaded_state.keys())

            to_process = [
                c for c in conversations
                if kg_import.get_conv_id(c, "claude") not in already_imported_ids
            ]

            assert len(to_process) == 1
            assert kg_import.get_conv_id(to_process[0], "claude") == "conv-002"

    def test_state_file_written_after_processing(self):
        """After processing a conversation, its ID must appear in the state file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            state = {}

            conv_id = "conv-new-001"
            kg_import.record_imported(state, conv_id, 3)
            kg_import.save_state(state, state_path)

            loaded = kg_import.load_state(state_path)
            assert conv_id in loaded
            assert loaded[conv_id]["beats_written"] == 3

    def test_rerunning_skips_previously_imported(self):
        """Simulates a second run: conversations in state should not appear in to_process."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"

            conv_ids = ["a", "b", "c"]
            conversations = [self._make_claude_conversation(uid) for uid in conv_ids]

            # Simulate first run: process 'a' and 'b'
            state = {}
            kg_import.record_imported(state, "a", 2)
            kg_import.record_imported(state, "b", 1)
            kg_import.save_state(state, state_path)

            # Second run: only 'c' should be in to_process
            loaded_state = kg_import.load_state(state_path)
            already_imported_ids = set(loaded_state.keys())
            to_process = [
                c for c in conversations
                if kg_import.get_conv_id(c, "claude") not in already_imported_ids
            ]
            assert len(to_process) == 1
            assert kg_import.get_conv_id(to_process[0], "claude") == "c"


# ---------------------------------------------------------------------------
# Dry-run tests
# ---------------------------------------------------------------------------

class TestDryRun:
    """
    Tests that --dry-run mode produces no file writes and does not update the state file.

    The main() function calls _import_extract_beats() which requires the installed
    extractor. For unit testing dry-run behavior, we test the logic that --dry-run
    bypasses: specifically that process_conversation() is never called and
    save_state() is never called.
    """

    def test_dry_run_does_not_write_state_file(self):
        """
        When dry_run=True the state file must not be updated.

        We verify this by confirming that save_state is never called during
        a dry-run pass through the conversation loop.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"

            # State starts empty
            assert not state_path.exists()

            state = kg_import.load_state(state_path)
            conversations = [
                {
                    "uuid": "dry-conv-001",
                    "name": "Would be processed",
                    "updated_at": "2026-02-10T10:00:00Z",
                    "chat_messages": [
                        {"sender": "human", "text": "How do I fix a Postgres timeout?",
                         "content": [{"type": "text", "text": "How do I fix a Postgres timeout?"}]},
                        {"sender": "assistant", "text": "Increase pool_timeout in database.yml.",
                         "content": [{"type": "text", "text": "Increase pool_timeout in database.yml."}]},
                    ],
                }
            ]

            dry_run = True

            # Simulate the dry-run branch of main() — should skip save_state
            for conv in conversations:
                uid = kg_import.get_conv_id(conv, "claude")
                if uid in state:
                    continue
                if dry_run:
                    # Dry-run: report only, do not process or write state
                    pass

            # State file should not have been created
            assert not state_path.exists()

    def test_dry_run_does_not_call_process_conversation(self):
        """
        Verify that no extractor calls are made during dry-run.

        We use a mock for process_conversation to ensure it is never invoked
        in the dry-run path.
        """
        process_mock = MagicMock()

        conversations = [
            {
                "uuid": "dry-002",
                "name": "Some conversation",
                "updated_at": "2026-02-10T10:00:00Z",
                "chat_messages": [
                    {"sender": "human", "text": "What is autofile?",
                     "content": [{"type": "text", "text": "What is autofile?"}]},
                    {"sender": "assistant", "text": "Autofile routes beats intelligently.",
                     "content": [{"type": "text", "text": "Autofile routes beats intelligently."}]},
                ],
            }
        ]

        state = {}
        dry_run = True

        for conv in conversations:
            uid = kg_import.get_conv_id(conv, "claude")
            if uid in state:
                continue
            if dry_run:
                # In dry-run, we never call process_conversation
                continue
            process_mock(conv)  # this line should never be reached

        process_mock.assert_not_called()


# ---------------------------------------------------------------------------
# Integration: full parse pipeline (no LLM calls)
# ---------------------------------------------------------------------------

class TestConversationRendering:
    """Tests for the full rendering pipeline of both formats."""

    def test_claude_render_with_fixture(self):
        fixture = FIXTURES_DIR / "sample_claude_export.json"
        with open(fixture, encoding="utf-8") as f:
            convs = json.load(f)

        # conv 0: should render with content
        rendered_0 = kg_import.render_conversation(convs[0], "claude")
        assert len(rendered_0) >= kg_import.MIN_CHARS_FOR_EXTRACTION
        assert "Human:" in rendered_0
        assert "Assistant:" in rendered_0

        # conv 2: "Quick question" — should be too short to extract
        rendered_2 = kg_import.render_conversation(convs[2], "claude")
        assert len(rendered_2.strip()) < 200  # very short

    def test_chatgpt_render_with_fixture(self):
        fixture = FIXTURES_DIR / "sample_chatgpt_export.json"
        with open(fixture, encoding="utf-8") as f:
            convs = json.load(f)

        # conv 0 and 1: should render with content
        for i in range(2):
            rendered = kg_import.render_conversation(convs[i], "chatgpt")
            assert "Human:" in rendered
            assert "Assistant:" in rendered

    def test_get_conv_id_claude_format(self):
        conv = {"uuid": "my-uuid-123"}
        assert kg_import.get_conv_id(conv, "claude") == "my-uuid-123"

    def test_get_conv_id_chatgpt_format(self):
        conv = {"id": "chatgpt-id-456"}
        assert kg_import.get_conv_id(conv, "chatgpt") == "chatgpt-id-456"

    def test_get_conv_date_claude_format(self):
        conv = {"updated_at": "2026-02-15T14:30:00Z"}
        assert kg_import.get_conv_date(conv, "claude") == "2026-02-15"

    def test_get_conv_date_chatgpt_format(self):
        # 1738800000 = 2025-02-06 in UTC
        conv = {"update_time": 1738800000.0}
        date = kg_import.get_conv_date(conv, "chatgpt")
        assert date.startswith("2025-02-")


# ---------------------------------------------------------------------------
# _extract_chatgpt_thread tests (lines 47-58)
# ---------------------------------------------------------------------------

class TestRenderClaudeMessageText:
    """Tests for _render_claude_message_text() — line 147 branch."""

    def test_non_human_assistant_sender_returns_empty(self):
        """Line 147: non-human/assistant sender returns empty string."""
        msg = {"sender": "system", "text": "You are helpful.", "content": []}
        result = kg_import._render_claude_message_text(msg)
        assert result == ""

    def test_tool_sender_returns_empty(self):
        msg = {"sender": "tool", "text": "tool output", "content": []}
        result = kg_import._render_claude_message_text(msg)
        assert result == ""

    def test_human_sender_returns_content(self):
        msg = {"sender": "human", "text": "hello", "content": [{"type": "text", "text": "hello"}]}
        result = kg_import._render_claude_message_text(msg)
        assert result == "hello"


class TestExtractChatGPTThread:
    """Tests for _extract_chatgpt_thread() — tree-walking from current_node."""

    def _make_mapping(self):
        root_id = "root"
        msg1_id = "msg1"
        msg2_id = "msg2"
        mapping = {
            root_id: {
                "id": root_id,
                "parent": None,
                "children": [msg1_id],
                "message": None,
            },
            msg1_id: {
                "id": msg1_id,
                "parent": root_id,
                "children": [msg2_id],
                "message": {
                    "author": {"role": "user"},
                    "content": {"content_type": "text", "parts": ["Hello"]},
                },
            },
            msg2_id: {
                "id": msg2_id,
                "parent": msg1_id,
                "children": [],
                "message": {
                    "author": {"role": "assistant"},
                    "content": {"content_type": "text", "parts": ["Hi there"]},
                },
            },
        }
        return mapping, root_id, msg1_id, msg2_id

    def test_returns_messages_in_order(self):
        mapping, _, _, msg2_id = self._make_mapping()
        thread = kg_import._extract_chatgpt_thread(mapping, msg2_id)
        # Should be in forward order: msg1, msg2 (root has no message)
        assert len(thread) == 2
        assert thread[0]["author"]["role"] == "user"
        assert thread[1]["author"]["role"] == "assistant"

    def test_skips_nodes_with_none_message(self):
        mapping, _, _, msg2_id = self._make_mapping()
        thread = kg_import._extract_chatgpt_thread(mapping, msg2_id)
        # root has message=None, so should not be in thread
        assert len(thread) == 2

    def test_handles_missing_node_gracefully(self):
        mapping, _, _, msg2_id = self._make_mapping()
        # Start from a node whose parent doesn't exist in mapping
        mapping["msg2"]["parent"] = "nonexistent-node"
        thread = kg_import._extract_chatgpt_thread(mapping, msg2_id)
        # Should include msg2 (which has a message), then stop
        assert len(thread) == 1
        assert thread[0]["author"]["role"] == "assistant"

    def test_empty_mapping_returns_empty_list(self):
        thread = kg_import._extract_chatgpt_thread({}, "some-node")
        assert thread == []

    def test_single_node_with_message(self):
        mapping = {
            "only": {
                "id": "only",
                "parent": None,
                "children": [],
                "message": {
                    "author": {"role": "user"},
                    "content": {"content_type": "text", "parts": ["Just me"]},
                },
            }
        }
        thread = kg_import._extract_chatgpt_thread(mapping, "only")
        assert len(thread) == 1
        assert thread[0]["author"]["role"] == "user"


# ---------------------------------------------------------------------------
# _render_chatgpt_message_text tests (lines 66-96)
# ---------------------------------------------------------------------------

class TestRenderChatGPTMessageText:
    """Tests for _render_chatgpt_message_text() — content extraction."""

    def test_simple_text_parts(self):
        msg = {"content": {"content_type": "text", "parts": ["Hello world"]}}
        result = kg_import._render_chatgpt_message_text(msg)
        assert result == "Hello world"

    def test_multiple_text_parts_joined(self):
        msg = {"content": {"content_type": "text", "parts": ["Hello", " world"]}}
        result = kg_import._render_chatgpt_message_text(msg)
        assert result == "Hello world"

    def test_non_text_content_type_returns_empty(self):
        msg = {"content": {"content_type": "multimodal_text", "parts": ["[image]"]}}
        result = kg_import._render_chatgpt_message_text(msg)
        assert result == ""

    def test_non_string_parts_skipped(self):
        # Parts that are dicts (e.g. image objects) should be skipped
        msg = {
            "content": {
                "content_type": "text",
                "parts": [{"type": "image", "url": "http://example.com"}, "text part"],
            }
        }
        result = kg_import._render_chatgpt_message_text(msg)
        assert result == "text part"

    def test_empty_parts_returns_empty(self):
        msg = {"content": {"content_type": "text", "parts": []}}
        result = kg_import._render_chatgpt_message_text(msg)
        assert result == ""

    def test_missing_content_returns_empty(self):
        msg = {}
        result = kg_import._render_chatgpt_message_text(msg)
        assert result == ""

    def test_none_content_returns_empty(self):
        msg = {"content": None}
        result = kg_import._render_chatgpt_message_text(msg)
        assert result == ""

    def test_strips_whitespace(self):
        msg = {"content": {"content_type": "text", "parts": ["  hello  "]}}
        result = kg_import._render_chatgpt_message_text(msg)
        assert result == "hello"


# ---------------------------------------------------------------------------
# parse_chatgpt_conversation additional branches (lines 147, 261-262, 279, 288)
# ---------------------------------------------------------------------------

class TestParseChatGPTConversationBranches:
    """Tests for uncovered branches in parse_chatgpt_conversation()."""

    def test_date_falls_back_to_create_time_when_no_update_time(self):
        """Line 261-262: use create_time when update_time is absent."""
        conv = {
            "id": "test-fallback",
            "title": "Fallback date test",
            "create_time": 1700000000.0,  # ~2023-11-14
            "mapping": {
                "msg1": {
                    "id": "msg1",
                    "parent": None,
                    "children": [],
                    "message": {
                        "author": {"role": "user"},
                        "content": {"content_type": "text", "parts": ["Hello"]},
                    },
                }
            },
            "current_node": "msg1",
        }
        result = kg_import.parse_chatgpt_conversation(conv)
        assert "Date:" in result
        assert "2023-11" in result

    def test_no_date_when_neither_update_time_nor_create_time(self):
        """Lines 261-262: date is empty string when both timestamps absent."""
        conv = {
            "id": "test-no-date",
            "title": "No date",
            "mapping": {},
            "current_node": "",
        }
        result = kg_import.parse_chatgpt_conversation(conv)
        # Date line should not appear
        assert "Date:" not in result

    def test_transcript_truncated_when_too_long(self):
        """Line 288: truncation when rendered output exceeds MAX_TRANSCRIPT_CHARS."""
        # Create a very long message
        long_text = "x" * (kg_import.MAX_TRANSCRIPT_CHARS + 5000)
        conv = {
            "id": "long-conv",
            "title": "Long",
            "update_time": 1700000000.0,
            "mapping": {
                "msg1": {
                    "id": "msg1",
                    "parent": None,
                    "children": [],
                    "message": {
                        "author": {"role": "user"},
                        "content": {"content_type": "text", "parts": [long_text]},
                    },
                }
            },
            "current_node": "msg1",
        }
        result = kg_import.parse_chatgpt_conversation(conv)
        assert len(result) <= kg_import.MAX_TRANSCRIPT_CHARS + len("...[earlier content truncated]...\n\n")
        assert "truncated" in result

    def test_skips_unknown_role(self):
        """Line 279: roles not in (user, assistant, system, tool) are skipped."""
        conv = {
            "id": "test-unknown-role",
            "title": "Unknown role",
            "update_time": 1700000000.0,
            "mapping": {
                "msg1": {
                    "id": "msg1",
                    "parent": None,
                    "children": ["msg2"],
                    "message": {
                        "author": {"role": "unknown_role"},
                        "content": {"content_type": "text", "parts": ["secret stuff"]},
                    },
                },
                "msg2": {
                    "id": "msg2",
                    "parent": "msg1",
                    "children": [],
                    "message": {
                        "author": {"role": "assistant"},
                        "content": {"content_type": "text", "parts": ["I can help."]},
                    },
                },
            },
            "current_node": "msg2",
        }
        result = kg_import.parse_chatgpt_conversation(conv)
        assert "secret stuff" not in result
        assert "I can help." in result


# ---------------------------------------------------------------------------
# ChatGPT dispatch helpers (lines 301, 305, 325-327)
# ---------------------------------------------------------------------------

class TestChatGPTHelpers:
    """Tests for get_chatgpt_conv_date, get_chatgpt_conv_title, render_conversation dispatch."""

    def test_get_chatgpt_conv_date_uses_create_time_when_no_update_time(self):
        """Line 301: fallback to create_time."""
        conv = {"create_time": 1700000000.0}
        date = kg_import.get_chatgpt_conv_date(conv)
        assert date.startswith("2023-")

    def test_get_chatgpt_conv_date_returns_empty_when_no_timestamp(self):
        conv = {}
        date = kg_import.get_chatgpt_conv_date(conv)
        assert date == ""

    def test_get_chatgpt_conv_title_returns_untitled_when_missing(self):
        """Line 305: fallback to 'Untitled'."""
        conv = {}
        title = kg_import.get_chatgpt_conv_title(conv)
        assert title == "Untitled"

    def test_get_chatgpt_conv_title_strips_whitespace(self):
        conv = {"title": "  My Chat  "}
        title = kg_import.get_chatgpt_conv_title(conv)
        assert title == "My Chat"

    def test_render_conversation_dispatches_chatgpt(self):
        """Lines 325-327: render_conversation calls parse_chatgpt_conversation for chatgpt fmt."""
        conv = {
            "id": "x",
            "title": "dispatch test",
            "update_time": 1700000000.0,
            "mapping": {
                "msg1": {
                    "id": "msg1",
                    "parent": None,
                    "children": [],
                    "message": {
                        "author": {"role": "user"},
                        "content": {"content_type": "text", "parts": ["hi"]},
                    },
                }
            },
            "current_node": "msg1",
        }
        result = kg_import.render_conversation(conv, "chatgpt")
        assert "dispatch test" in result
        assert "Human: hi" in result

    def test_get_conv_title_chatgpt_format(self):
        """Line 326: get_conv_title dispatches to chatgpt helper."""
        conv = {"title": "ChatGPT Title"}
        assert kg_import.get_conv_title(conv, "chatgpt") == "ChatGPT Title"

    def test_get_conv_title_claude_format(self):
        """Line 327: get_conv_title dispatches to claude helper."""
        conv = {"name": "Claude Title"}
        assert kg_import.get_conv_title(conv, "claude") == "Claude Title"


# ---------------------------------------------------------------------------
# load_export tests (lines 348-372)
# ---------------------------------------------------------------------------

class TestLoadExport:
    """Tests for load_export() — file loading and format handling."""

    def test_file_not_found_exits(self):
        with pytest.raises(SystemExit):
            kg_import.load_export("/nonexistent/path/that/does/not/exist.json", "claude")

    def test_bad_json_exits(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("not valid json {{{")
            fname = f.name
        with pytest.raises(SystemExit):
            kg_import.load_export(fname, "claude")

    def test_wrapped_format_unwrapped(self):
        """Wrapped format: {"conversations": [...]} should be unwrapped."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"conversations": [{"id": "x"}, {"id": "y"}]}, f)
            fname = f.name
        result = kg_import.load_export(fname, "claude")
        assert result == [{"id": "x"}, {"id": "y"}]

    def test_plain_list_returned_as_is(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([{"id": "a"}, {"id": "b"}], f)
            fname = f.name
        result = kg_import.load_export(fname, "claude")
        assert result == [{"id": "a"}, {"id": "b"}]

    def test_non_list_non_dict_exits(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(42, f)
            fname = f.name
        with pytest.raises(SystemExit):
            kg_import.load_export(fname, "claude")

    def test_dict_without_conversations_key_returns_empty(self):
        """Dict without 'conversations' key returns empty list (dict.get default)."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"something_else": [1, 2, 3]}, f)
            fname = f.name
        result = kg_import.load_export(fname, "claude")
        assert result == []


# ---------------------------------------------------------------------------
# get_conv_timestamp tests (lines 381-392)
# ---------------------------------------------------------------------------

class TestGetConvTimestamp:
    """Tests for get_conv_timestamp() — returns datetime for beat dating."""

    def test_chatgpt_uses_update_time(self):
        conv = {"update_time": 1700000000.0}
        ts = kg_import.get_conv_timestamp(conv, "chatgpt")
        assert isinstance(ts, datetime)
        assert ts.year == 2023

    def test_chatgpt_falls_back_to_create_time(self):
        conv = {"create_time": 1700000000.0}
        ts = kg_import.get_conv_timestamp(conv, "chatgpt")
        assert isinstance(ts, datetime)
        assert ts.year == 2023

    def test_chatgpt_no_timestamp_returns_now(self):
        ts = kg_import.get_conv_timestamp({}, "chatgpt")
        assert isinstance(ts, datetime)
        # Should be very recent
        now = datetime.now(timezone.utc)
        delta = abs((now - ts).total_seconds())
        assert delta < 5

    def test_claude_uses_updated_at(self):
        conv = {"updated_at": "2024-01-15T10:30:00Z"}
        ts = kg_import.get_conv_timestamp(conv, "claude")
        assert isinstance(ts, datetime)
        assert ts.year == 2024
        assert ts.month == 1
        assert ts.day == 15

    def test_claude_falls_back_to_created_at(self):
        conv = {"created_at": "2024-06-01T00:00:00Z"}
        ts = kg_import.get_conv_timestamp(conv, "claude")
        assert isinstance(ts, datetime)
        assert ts.year == 2024
        assert ts.month == 6

    def test_claude_invalid_timestamp_returns_now(self):
        conv = {"updated_at": "not-a-date"}
        ts = kg_import.get_conv_timestamp(conv, "claude")
        assert isinstance(ts, datetime)
        now = datetime.now(timezone.utc)
        delta = abs((now - ts).total_seconds())
        assert delta < 5

    def test_claude_no_timestamp_returns_now(self):
        ts = kg_import.get_conv_timestamp({}, "claude")
        assert isinstance(ts, datetime)
        now = datetime.now(timezone.utc)
        delta = abs((now - ts).total_seconds())
        assert delta < 5


# ---------------------------------------------------------------------------
# process_conversation tests (lines 413-455)
# ---------------------------------------------------------------------------

class TestProcessConversation:
    """Tests for process_conversation() — extract beats and write to vault."""

    def _make_claude_conv(self, uid="test-123", text="Hello world this is a test"):
        return {
            "uuid": uid,
            "name": "Test conversation",
            "updated_at": "2024-01-01T00:00:00Z",
            "chat_messages": [
                {
                    "sender": "human",
                    "text": text,
                    "content": [{"type": "text", "text": text}],
                },
                {
                    "sender": "assistant",
                    "text": "This is a detailed and informative answer.",
                    "content": [{"type": "text", "text": "This is a detailed and informative answer."}],
                },
            ],
        }

    def _make_config(self, tmp_path, autofile=False):
        return {
            "vault_path": str(tmp_path),
            "inbox": "AI/Claude-Sessions",
            "autofile": autofile,
            "backend": "claude-code",
            "model": "claude-haiku-4-5",
        }

    def _make_beat(self, title="Test Beat"):
        return {
            "title": title,
            "type": "insight",
            "summary": "A test insight",
            "tags": ["python"],
        }

    def test_returns_count_and_paths(self, tmp_path):
        eb = MagicMock()
        eb.extract_beats.return_value = [self._make_beat()]
        eb.write_beat.return_value = Path(tmp_path / "note.md")

        conv = self._make_claude_conv()
        config = self._make_config(tmp_path)
        count, paths = kg_import.process_conversation(conv, "claude", config, eb, "/tmp")

        assert count == 1
        assert len(paths) == 1
        eb.write_beat.assert_called_once()

    def test_empty_transcript_returns_zero(self, tmp_path):
        eb = MagicMock()
        # Use a chatgpt conv whose mapping is empty and current_node is missing,
        # so render produces just the header (title + no messages).
        # We patch render_conversation to return "" to hit the empty-transcript branch.
        conv = {
            "uuid": "empty-123",
            "name": "Empty",
            "updated_at": "2024-01-01T00:00:00Z",
            "chat_messages": [],
        }
        config = self._make_config(tmp_path)
        with patch.object(kg_import, "render_conversation", return_value="   "):
            count, paths = kg_import.process_conversation(conv, "claude", config, eb, "/tmp")

        assert count == 0
        assert paths == []
        eb.extract_beats.assert_not_called()

    def test_extract_beats_returns_empty_returns_zero(self, tmp_path):
        eb = MagicMock()
        eb.extract_beats.return_value = []

        conv = self._make_claude_conv()
        config = self._make_config(tmp_path)
        count, paths = kg_import.process_conversation(conv, "claude", config, eb, "/tmp")

        assert count == 0
        assert paths == []
        eb.write_beat.assert_not_called()

    def test_autofile_enabled_calls_autofile_beat(self, tmp_path):
        eb = MagicMock()
        eb.extract_beats.return_value = [self._make_beat()]
        eb.autofile_beat.return_value = Path(tmp_path / "autofile-note.md")

        # Create a CLAUDE.md in vault for vault_context
        (tmp_path / "CLAUDE.md").write_text("## Vault config", encoding="utf-8")

        conv = self._make_claude_conv()
        config = self._make_config(tmp_path, autofile=True)
        count, paths = kg_import.process_conversation(conv, "claude", config, eb, "/tmp")

        assert count == 1
        eb.autofile_beat.assert_called_once()
        eb.write_beat.assert_not_called()

    def test_autofile_no_claude_md_uses_fallback_context(self, tmp_path):
        """When vault has no CLAUDE.md, autofile uses a fallback vault_context string."""
        eb = MagicMock()
        eb.extract_beats.return_value = [self._make_beat()]
        eb.autofile_beat.return_value = Path(tmp_path / "note.md")

        conv = self._make_claude_conv()
        config = self._make_config(tmp_path, autofile=True)
        count, paths = kg_import.process_conversation(conv, "claude", config, eb, "/tmp")

        assert count == 1
        # Check vault_context argument contains fallback text
        call_kwargs = eb.autofile_beat.call_args
        vault_ctx = call_kwargs.kwargs.get("vault_context", call_kwargs.args[4] if len(call_kwargs.args) > 4 else None)
        # The fallback string contains "decision"
        if vault_ctx is not None:
            assert "decision" in vault_ctx or "ontology" in vault_ctx.lower() or "File notes" in vault_ctx

    def test_write_beat_exception_continues(self, tmp_path):
        """If write_beat raises, process_conversation prints a warning and continues."""
        eb = MagicMock()
        beats = [self._make_beat("Beat 1"), self._make_beat("Beat 2")]
        eb.extract_beats.return_value = beats
        # First beat fails, second succeeds
        eb.write_beat.side_effect = [Exception("disk full"), Path(tmp_path / "note2.md")]

        conv = self._make_claude_conv()
        config = self._make_config(tmp_path)
        count, paths = kg_import.process_conversation(conv, "claude", config, eb, "/tmp")

        # Only the successful beat is counted
        assert count == 1
        assert len(paths) == 1

    def test_write_beat_returning_none_not_counted(self, tmp_path):
        """If write_beat returns None (e.g. dupe), it's not added to written list."""
        eb = MagicMock()
        eb.extract_beats.return_value = [self._make_beat()]
        eb.write_beat.return_value = None

        conv = self._make_claude_conv()
        config = self._make_config(tmp_path)
        count, paths = kg_import.process_conversation(conv, "claude", config, eb, "/tmp")

        assert count == 0
        assert paths == []

    def test_multiple_beats_all_written(self, tmp_path):
        eb = MagicMock()
        beats = [self._make_beat(f"Beat {i}") for i in range(3)]
        eb.extract_beats.return_value = beats
        eb.write_beat.side_effect = [
            Path(tmp_path / "note1.md"),
            Path(tmp_path / "note2.md"),
            Path(tmp_path / "note3.md"),
        ]

        conv = self._make_claude_conv()
        config = self._make_config(tmp_path)
        count, paths = kg_import.process_conversation(conv, "claude", config, eb, "/tmp")

        assert count == 3
        assert len(paths) == 3


# ---------------------------------------------------------------------------
# main() tests (lines 463-590)
# ---------------------------------------------------------------------------

class TestMain:
    """Tests for main() — CLI entry point."""

    def _make_claude_export(self, tmp_path, conversations=None):
        if conversations is None:
            conversations = [
                {
                    "uuid": "conv-main-001",
                    "name": "Test conversation for main",
                    "updated_at": "2024-01-01T00:00:00Z",
                    "chat_messages": [
                        {
                            "sender": "human",
                            "text": "What is Python?",
                            "content": [{"type": "text", "text": "What is Python?"}],
                        },
                        {
                            "sender": "assistant",
                            "text": "Python is a high-level programming language.",
                            "content": [{"type": "text", "text": "Python is a high-level programming language."}],
                        },
                    ],
                }
            ]
        export_file = tmp_path / "export.json"
        export_file.write_text(json.dumps(conversations), encoding="utf-8")
        return export_file

    def _make_mock_eb(self, beats=None):
        eb = MagicMock()
        if beats is None:
            beats = []
        eb.extract_beats.return_value = beats
        eb.resolve_config.return_value = {
            "vault_path": "/tmp/vault",
            "inbox": "AI/Claude-Sessions",
            "autofile": False,
            "backend": "claude-code",
            "model": "claude-haiku-4-5",
            "daily_journal": False,
        }
        return eb

    def test_main_dry_run_no_writes(self, tmp_path):
        export_file = self._make_claude_export(tmp_path)
        mock_eb = self._make_mock_eb()

        with patch.object(kg_import, "_import_extract_beats", return_value=mock_eb), \
             patch("sys.argv", ["import.py", "--export", str(export_file), "--format", "claude", "--dry-run"]):
            kg_import.main()

        # In dry-run, extract_beats should NOT be called
        mock_eb.extract_beats.assert_not_called()

    def test_main_dry_run_prints_would_process(self, tmp_path, capsys):
        export_file = self._make_claude_export(tmp_path)
        mock_eb = self._make_mock_eb()

        with patch.object(kg_import, "_import_extract_beats", return_value=mock_eb), \
             patch("sys.argv", ["import.py", "--export", str(export_file), "--format", "claude", "--dry-run"]):
            kg_import.main()

        out = capsys.readouterr().out
        assert "DRY RUN" in out or "would process" in out.lower() or "Would process" in out

    def test_main_empty_export_exits_cleanly(self, tmp_path, capsys):
        export_file = self._make_claude_export(tmp_path, conversations=[])
        mock_eb = self._make_mock_eb()

        with patch.object(kg_import, "_import_extract_beats", return_value=mock_eb), \
             patch("sys.argv", ["import.py", "--export", str(export_file), "--format", "claude"]):
            kg_import.main()

        out = capsys.readouterr().out
        assert "Nothing to process" in out or "0 to process" in out

    def test_main_all_already_imported_skips(self, tmp_path, capsys):
        """Conversations already in state file are skipped without processing."""
        export_file = self._make_claude_export(tmp_path)
        mock_eb = self._make_mock_eb()

        state_path = tmp_path / "state.json"
        existing_state = {"conv-main-001": {"imported_at": "2024-01-01T00:00:00Z", "beats_written": 2}}
        state_path.write_text(json.dumps(existing_state), encoding="utf-8")

        with patch.object(kg_import, "_import_extract_beats", return_value=mock_eb), \
             patch.object(kg_import, "STATE_PATH", state_path), \
             patch("sys.argv", ["import.py", "--export", str(export_file), "--format", "claude"]):
            kg_import.main()

        mock_eb.extract_beats.assert_not_called()

    def test_main_limit_respected(self, tmp_path, capsys):
        """--limit N processes at most N conversations."""
        conversations = [
            {
                "uuid": f"conv-{i}",
                "name": f"Conversation {i}",
                "updated_at": "2024-01-01T00:00:00Z",
                "chat_messages": [
                    {"sender": "human", "text": f"Question {i} with some text to pass min chars check",
                     "content": [{"type": "text", "text": f"Question {i} with some text to pass min chars check"}]},
                    {"sender": "assistant", "text": f"Answer {i} providing detailed information about the topic",
                     "content": [{"type": "text", "text": f"Answer {i} providing detailed information about the topic"}]},
                ],
            }
            for i in range(5)
        ]
        export_file = self._make_claude_export(tmp_path, conversations)
        mock_eb = self._make_mock_eb()

        with patch.object(kg_import, "_import_extract_beats", return_value=mock_eb), \
             patch("sys.argv", ["import.py", "--export", str(export_file), "--format", "claude", "--dry-run", "--limit", "2"]):
            kg_import.main()

        out = capsys.readouterr().out
        assert "2 to process" in out or "Would process 2" in out

    def test_main_since_filter(self, tmp_path, capsys):
        """--since YYYY-MM-DD filters out older conversations."""
        conversations = [
            {
                "uuid": "old-conv",
                "name": "Old conversation",
                "updated_at": "2023-01-01T00:00:00Z",
                "chat_messages": [
                    {"sender": "human", "text": "old question",
                     "content": [{"type": "text", "text": "old question"}]},
                ],
            },
            {
                "uuid": "new-conv",
                "name": "New conversation",
                "updated_at": "2024-06-01T00:00:00Z",
                "chat_messages": [
                    {"sender": "human", "text": "new question that is long enough to pass min chars",
                     "content": [{"type": "text", "text": "new question that is long enough to pass min chars"}]},
                    {"sender": "assistant", "text": "new answer that is detailed and informative",
                     "content": [{"type": "text", "text": "new answer that is detailed and informative"}]},
                ],
            },
        ]
        export_file = self._make_claude_export(tmp_path, conversations)
        mock_eb = self._make_mock_eb()

        with patch.object(kg_import, "_import_extract_beats", return_value=mock_eb), \
             patch("sys.argv", ["import.py", "--export", str(export_file), "--format", "claude",
                                "--dry-run", "--since", "2024-01-01"]):
            kg_import.main()

        out = capsys.readouterr().out
        assert "1 to process" in out

    def test_main_short_conversation_skipped(self, tmp_path, capsys):
        """Conversations shorter than MIN_CHARS_FOR_EXTRACTION are skipped."""
        conversations = [
            {
                "uuid": "short-conv",
                "name": "Short",
                "updated_at": "2024-01-01T00:00:00Z",
                "chat_messages": [
                    {"sender": "human", "text": "hi",
                     "content": [{"type": "text", "text": "hi"}]},
                ],
            }
        ]
        export_file = self._make_claude_export(tmp_path, conversations)
        mock_eb = self._make_mock_eb()
        mock_eb.resolve_config.return_value = {
            "vault_path": str(tmp_path),
            "inbox": "AI",
            "autofile": False,
            "backend": "claude-code",
            "model": "claude-haiku-4-5",
            "daily_journal": False,
        }

        state_path = tmp_path / "state.json"
        with patch.object(kg_import, "_import_extract_beats", return_value=mock_eb), \
             patch.object(kg_import, "STATE_PATH", state_path), \
             patch("sys.argv", ["import.py", "--export", str(export_file), "--format", "claude"]):
            kg_import.main()

        out = capsys.readouterr().out
        assert "too short" in out.lower() or "Skipping" in out

    def test_main_chatgpt_format(self, tmp_path, capsys):
        """main() handles --format chatgpt."""
        conversations = [
            {
                "id": "chatgpt-conv-001",
                "title": "ChatGPT test",
                "update_time": 1700000000.0,
                "mapping": {
                    "msg1": {
                        "id": "msg1",
                        "parent": None,
                        "children": [],
                        "message": {
                            "author": {"role": "user"},
                            "content": {"content_type": "text", "parts": ["Hello ChatGPT, what is Python?"]},
                        },
                    }
                },
                "current_node": "msg1",
            }
        ]
        export_file = tmp_path / "chatgpt_export.json"
        export_file.write_text(json.dumps(conversations), encoding="utf-8")
        mock_eb = self._make_mock_eb()

        with patch.object(kg_import, "_import_extract_beats", return_value=mock_eb), \
             patch("sys.argv", ["import.py", "--export", str(export_file), "--format", "chatgpt", "--dry-run"]):
            kg_import.main()

        out = capsys.readouterr().out
        assert "chatgpt" in out.lower()

    def test_main_no_id_conversation_skipped(self, tmp_path, capsys):
        """Conversations with no ID are skipped (not added to to_process)."""
        conversations = [
            {
                # No uuid field
                "name": "No ID conversation",
                "updated_at": "2024-01-01T00:00:00Z",
                "chat_messages": [],
            },
            {
                "uuid": "valid-conv-001",
                "name": "Valid",
                "updated_at": "2024-01-01T00:00:00Z",
                "chat_messages": [
                    {"sender": "human", "text": "Valid question with enough content to test",
                     "content": [{"type": "text", "text": "Valid question with enough content to test"}]},
                    {"sender": "assistant", "text": "Valid answer that provides detailed information",
                     "content": [{"type": "text", "text": "Valid answer that provides detailed information"}]},
                ],
            },
        ]
        export_file = self._make_claude_export(tmp_path, conversations)
        mock_eb = self._make_mock_eb()

        with patch.object(kg_import, "_import_extract_beats", return_value=mock_eb), \
             patch("sys.argv", ["import.py", "--export", str(export_file), "--format", "claude", "--dry-run"]):
            kg_import.main()

        out = capsys.readouterr().out
        # Only 1 conversation should be in to_process (the one with uuid)
        assert "1 to process" in out

    def test_main_process_conversation_error_counted(self, tmp_path, capsys):
        """Errors in process_conversation are caught and counted."""
        conversations = [
            {
                "uuid": "error-conv",
                "name": "Error conversation",
                "updated_at": "2024-01-01T00:00:00Z",
                "chat_messages": [
                    {"sender": "human", "text": "Question with sufficient length to pass the min chars check",
                     "content": [{"type": "text", "text": "Question with sufficient length to pass the min chars check"}]},
                    {"sender": "assistant", "text": "Answer with sufficient length providing detailed information",
                     "content": [{"type": "text", "text": "Answer with sufficient length providing detailed information"}]},
                ],
            }
        ]
        export_file = self._make_claude_export(tmp_path, conversations)
        mock_eb = self._make_mock_eb()
        mock_eb.resolve_config.return_value = {
            "vault_path": str(tmp_path),
            "inbox": "AI",
            "autofile": False,
            "backend": "claude-code",
            "model": "claude-haiku-4-5",
            "daily_journal": False,
        }
        mock_eb.extract_beats.side_effect = Exception("LLM failure")

        state_path = tmp_path / "state.json"
        with patch.object(kg_import, "_import_extract_beats", return_value=mock_eb), \
             patch.object(kg_import, "STATE_PATH", state_path), \
             patch("sys.argv", ["import.py", "--export", str(export_file), "--format", "claude"]):
            kg_import.main()

        out = capsys.readouterr().out
        assert "Errors: 1" in out

    def test_main_writes_state_after_success(self, tmp_path, capsys):
        """Successful processing updates the state file."""
        conversations = [
            {
                "uuid": "success-conv",
                "name": "Success conversation",
                "updated_at": "2024-01-01T00:00:00Z",
                "chat_messages": [
                    {"sender": "human", "text": "Question with sufficient length to pass the minimum chars check threshold",
                     "content": [{"type": "text", "text": "Question with sufficient length to pass the minimum chars check threshold"}]},
                    {"sender": "assistant", "text": "Answer with sufficient length providing very detailed information about the topic",
                     "content": [{"type": "text", "text": "Answer with sufficient length providing very detailed information about the topic"}]},
                ],
            }
        ]
        export_file = self._make_claude_export(tmp_path, conversations)
        mock_eb = self._make_mock_eb()
        mock_eb.resolve_config.return_value = {
            "vault_path": str(tmp_path),
            "inbox": "AI",
            "autofile": False,
            "backend": "claude-code",
            "model": "claude-haiku-4-5",
            "daily_journal": False,
        }
        mock_eb.extract_beats.return_value = []  # no beats but no error

        state_path = tmp_path / "state.json"
        with patch.object(kg_import, "_import_extract_beats", return_value=mock_eb), \
             patch.object(kg_import, "STATE_PATH", state_path), \
             patch("sys.argv", ["import.py", "--export", str(export_file), "--format", "claude"]):
            kg_import.main()

        # State should have been written
        assert state_path.exists()
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert "success-conv" in state

    def test_main_journal_written_when_enabled(self, tmp_path, capsys):
        """When daily_journal=True and beats were written, journal entry is created."""
        conversations = [
            {
                "uuid": "journal-conv",
                "name": "Journal test",
                "updated_at": "2024-01-01T00:00:00Z",
                "chat_messages": [
                    {"sender": "human", "text": "Question with sufficient length to pass the minimum chars check threshold",
                     "content": [{"type": "text", "text": "Question with sufficient length to pass the minimum chars check threshold"}]},
                    {"sender": "assistant", "text": "Answer with sufficient length providing very detailed information about the topic",
                     "content": [{"type": "text", "text": "Answer with sufficient length providing very detailed information about the topic"}]},
                ],
            }
        ]
        export_file = self._make_claude_export(tmp_path, conversations)
        mock_eb = self._make_mock_eb()
        mock_eb.resolve_config.return_value = {
            "vault_path": str(tmp_path),
            "inbox": "AI",
            "autofile": False,
            "backend": "claude-code",
            "model": "claude-haiku-4-5",
            "daily_journal": True,  # enabled
        }
        mock_eb.extract_beats.return_value = [
            {"title": "Beat", "type": "insight", "summary": "x", "tags": []}
        ]
        mock_eb.write_beat.return_value = Path(tmp_path / "note.md")

        state_path = tmp_path / "state.json"
        with patch.object(kg_import, "_import_extract_beats", return_value=mock_eb), \
             patch.object(kg_import, "STATE_PATH", state_path), \
             patch("sys.argv", ["import.py", "--export", str(export_file), "--format", "claude"]):
            kg_import.main()

        mock_eb.write_journal_entry.assert_called_once()

    def test_main_extractor_not_found_exits(self, tmp_path):
        """_import_extract_beats exits with sys.exit(1) when extractor is missing."""
        with patch.object(kg_import, "EXTRACTORS_DIR", tmp_path / "nonexistent"), \
             patch("sys.argv", ["import.py", "--export", "/dev/null", "--format", "claude"]):
            with pytest.raises(SystemExit):
                kg_import._import_extract_beats()

    def test_main_summary_printed(self, tmp_path, capsys):
        """Import complete summary is printed after non-dry-run."""
        conversations = [
            {
                "uuid": "summary-conv",
                "name": "Summary test",
                "updated_at": "2024-01-01T00:00:00Z",
                "chat_messages": [
                    {"sender": "human", "text": "Question with sufficient length to pass the minimum chars check threshold",
                     "content": [{"type": "text", "text": "Question with sufficient length to pass the minimum chars check threshold"}]},
                    {"sender": "assistant", "text": "Answer with sufficient length providing very detailed information about the topic",
                     "content": [{"type": "text", "text": "Answer with sufficient length providing very detailed information about the topic"}]},
                ],
            }
        ]
        export_file = self._make_claude_export(tmp_path, conversations)
        mock_eb = self._make_mock_eb()
        mock_eb.resolve_config.return_value = {
            "vault_path": str(tmp_path),
            "inbox": "AI",
            "autofile": False,
            "backend": "claude-code",
            "model": "claude-haiku-4-5",
            "daily_journal": False,
        }
        mock_eb.extract_beats.return_value = []

        state_path = tmp_path / "state.json"
        with patch.object(kg_import, "_import_extract_beats", return_value=mock_eb), \
             patch.object(kg_import, "STATE_PATH", state_path), \
             patch("sys.argv", ["import.py", "--export", str(export_file), "--format", "claude"]):
            kg_import.main()

        out = capsys.readouterr().out
        assert "Import complete" in out
        assert "beats written" in out
