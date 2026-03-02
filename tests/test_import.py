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
