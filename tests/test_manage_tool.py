"""
test_manage_tool.py — unit tests for mcp/tools/manage.py

Covers:
- _read_prefs_section: all branches
- _write_prefs_section: all branches
- cb_configure(show_prefs/set_prefs/reset_prefs): all paths
- cb_configure(working_memory_ttl): valid and invalid inputs
- cb_configure(vault_path): write path including background index rebuild
- cb_configure() no-args: status display with runs log
- cb_status(): all major branches
"""

import json
import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# sys.path setup — must match the pattern from other test files
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent
MCP_DIR = REPO_ROOT / "mcp"
EXTRACTORS_DIR = REPO_ROOT / "extractors"

for d in [str(MCP_DIR), str(EXTRACTORS_DIR), str(REPO_ROOT)]:
    if d not in sys.path:
        sys.path.insert(0, d)

# conftest.py installs the shared extract_beats mock before this module is imported.
# Clear stale cache entries so we get a fresh import bound to our FakeMCP.
for _mod in ["shared", "tools.manage"]:
    sys.modules.pop(_mod, None)

import shared as _shared  # noqa: E402  (needed after sys.path setup)
import tools.manage as manage_mod  # noqa: E402

try:
    from fastmcp.exceptions import ToolError
except ImportError:
    class ToolError(Exception):  # type: ignore[no-redef]
        pass

# ---------------------------------------------------------------------------
# FakeMCP
# ---------------------------------------------------------------------------


class _Annotations:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class FakeMCP:
    def __init__(self):
        self._tools = {}

    def tool(self, annotations=None, **kwargs):
        def decorator(fn):
            self._tools[fn.__name__] = {"fn": fn, "annotations": annotations}
            return fn
        return decorator


_fake_mcp = FakeMCP()
manage_mod.register(_fake_mcp)


def _cb_configure():
    return _fake_mcp._tools["cb_configure"]["fn"]


def _cb_status():
    return _fake_mcp._tools["cb_status"]["fn"]


# ---------------------------------------------------------------------------
# Helper: write a CLAUDE.md to a vault dir
# ---------------------------------------------------------------------------

def _write_claude_md(vault: Path, content: str) -> None:
    (vault / "CLAUDE.md").write_text(content, encoding="utf-8")


# ===========================================================================
# _read_prefs_section
# ===========================================================================

class TestReadPrefsSection:
    def test_no_claude_md_returns_none(self, tmp_path):
        result = manage_mod._read_prefs_section(str(tmp_path))
        assert result is None

    def test_claude_md_no_prefs_heading_returns_none(self, tmp_path):
        _write_claude_md(tmp_path, "# My Vault\n\nSome content here.\n")
        result = manage_mod._read_prefs_section(str(tmp_path))
        assert result is None

    def test_claude_md_with_prefs_section_at_eof(self, tmp_path):
        content = "# My Vault\n\n## Cyberbrain Preferences\n\n- Extract durable knowledge\n- Focus on decisions\n"
        _write_claude_md(tmp_path, content)
        result = manage_mod._read_prefs_section(str(tmp_path))
        assert result is not None
        assert "Cyberbrain Preferences" in result
        assert "Extract durable knowledge" in result

    def test_claude_md_prefs_section_followed_by_another_heading(self, tmp_path):
        content = (
            "# My Vault\n\n"
            "## Cyberbrain Preferences\n\n"
            "- Extract durable knowledge\n\n"
            "## Another Section\n\n"
            "other content\n"
        )
        _write_claude_md(tmp_path, content)
        result = manage_mod._read_prefs_section(str(tmp_path))
        assert result is not None
        assert "Extract durable knowledge" in result
        # Must not include the next section
        assert "Another Section" not in result
        assert "other content" not in result

    def test_prefs_section_content_is_stripped(self, tmp_path):
        content = "## Cyberbrain Preferences\n\n- Pref one\n"
        _write_claude_md(tmp_path, content)
        result = manage_mod._read_prefs_section(str(tmp_path))
        assert result is not None
        assert result == result.strip()


# ===========================================================================
# _write_prefs_section
# ===========================================================================

class TestWritePrefsSection:
    def test_no_claude_md_creates_file(self, tmp_path):
        manage_mod._write_prefs_section(str(tmp_path), "- My preference\n")
        claude_md = tmp_path / "CLAUDE.md"
        assert claude_md.exists()
        text = claude_md.read_text(encoding="utf-8")
        assert "## Cyberbrain Preferences" in text
        assert "My preference" in text

    def test_existing_file_no_prefs_appends(self, tmp_path):
        _write_claude_md(tmp_path, "# My Vault\n\nExisting content.\n")
        manage_mod._write_prefs_section(str(tmp_path), "- New pref\n")
        text = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
        assert "Existing content" in text
        assert "## Cyberbrain Preferences" in text
        assert "New pref" in text

    def test_existing_prefs_section_replaced(self, tmp_path):
        content = (
            "# My Vault\n\n"
            "## Cyberbrain Preferences\n\n"
            "- Old preference\n"
        )
        _write_claude_md(tmp_path, content)
        manage_mod._write_prefs_section(str(tmp_path), "- New preference\n")
        text = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
        assert "New preference" in text
        assert "Old preference" not in text

    def test_existing_prefs_section_with_following_heading_replaced(self, tmp_path):
        content = (
            "# My Vault\n\n"
            "## Cyberbrain Preferences\n\n"
            "- Old preference\n\n"
            "## Another Section\n\n"
            "other content\n"
        )
        _write_claude_md(tmp_path, content)
        manage_mod._write_prefs_section(str(tmp_path), "- New preference\n")
        text = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
        assert "New preference" in text
        assert "Old preference" not in text
        # The following section should be preserved
        assert "Another Section" in text
        assert "other content" in text

    def test_prefs_text_already_has_heading_not_doubled(self, tmp_path):
        _write_claude_md(tmp_path, "")
        manage_mod._write_prefs_section(
            str(tmp_path), "## Cyberbrain Preferences\n\n- My pref\n"
        )
        text = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
        # Heading should appear exactly once
        assert text.count("## Cyberbrain Preferences") == 1

    def test_existing_file_ending_without_double_newline_gets_separator(self, tmp_path):
        _write_claude_md(tmp_path, "# My Vault\n")
        manage_mod._write_prefs_section(str(tmp_path), "- Pref\n")
        text = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
        assert "My Vault" in text
        assert "Cyberbrain Preferences" in text


# ===========================================================================
# cb_configure — preferences paths
# ===========================================================================

BASE_CONFIG = {
    "vault_path": "/tmp/test_vault",
    "inbox": "AI/Claude-Sessions",
    "backend": "claude-code",
    "model": "claude-haiku-4-5",
}


class TestCbConfigurePrefs:
    def test_show_prefs_no_vault_configured(self):
        cfg = {**BASE_CONFIG, "vault_path": ""}
        with patch.object(manage_mod, "_load_config", return_value=cfg):
            result = _cb_configure()(show_prefs=True)
        assert "No vault configured" in result

    def test_show_prefs_vault_does_not_exist(self, tmp_path):
        missing = str(tmp_path / "nonexistent")
        cfg = {**BASE_CONFIG, "vault_path": missing}
        with patch.object(manage_mod, "_load_config", return_value=cfg):
            result = _cb_configure()(show_prefs=True)
        assert "No vault configured" in result

    def test_show_prefs_no_prefs_section(self, tmp_path):
        _write_claude_md(tmp_path, "# My Vault\n\nNo prefs here.\n")
        cfg = {**BASE_CONFIG, "vault_path": str(tmp_path)}
        with patch.object(manage_mod, "_load_config", return_value=cfg):
            result = _cb_configure()(show_prefs=True)
        assert "No Cyberbrain Preferences" in result
        assert "reset_prefs=True" in result

    def test_show_prefs_returns_prefs_text(self, tmp_path):
        _write_claude_md(
            tmp_path,
            "# My Vault\n\n## Cyberbrain Preferences\n\n- Extract insights\n"
        )
        cfg = {**BASE_CONFIG, "vault_path": str(tmp_path)}
        with patch.object(manage_mod, "_load_config", return_value=cfg):
            result = _cb_configure()(show_prefs=True)
        assert "Extract insights" in result

    def test_set_prefs_no_vault(self):
        cfg = {**BASE_CONFIG, "vault_path": ""}
        with patch.object(manage_mod, "_load_config", return_value=cfg):
            result = _cb_configure()(set_prefs="- My custom pref")
        assert "No vault configured" in result

    def test_set_prefs_writes_and_returns_line_count(self, tmp_path):
        cfg = {**BASE_CONFIG, "vault_path": str(tmp_path)}
        prefs_text = "- Pref one\n- Pref two\n- Pref three"
        with patch.object(manage_mod, "_load_config", return_value=cfg):
            result = _cb_configure()(set_prefs=prefs_text)
        assert "updated" in result.lower()
        assert "3 lines" in result
        text = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
        assert "Pref one" in text

    def test_reset_prefs_no_vault(self):
        cfg = {**BASE_CONFIG, "vault_path": ""}
        with patch.object(manage_mod, "_load_config", return_value=cfg):
            result = _cb_configure()(reset_prefs=True)
        assert "No vault configured" in result

    def test_reset_prefs_writes_defaults(self, tmp_path):
        cfg = {**BASE_CONFIG, "vault_path": str(tmp_path)}
        with patch.object(manage_mod, "_load_config", return_value=cfg):
            result = _cb_configure()(reset_prefs=True)
        assert "reset" in result.lower() or "default" in result.lower()
        text = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
        assert "Cyberbrain Preferences" in text


# ===========================================================================
# cb_configure — working_memory_ttl
# ===========================================================================

class TestCbConfigureWorkingMemoryTTL:
    def test_valid_ttl_dict_writes_config(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
        cfg_dir = tmp_path / ".claude" / "cyberbrain"
        cfg_dir.mkdir(parents=True)
        cfg_file = cfg_dir / "config.json"
        cfg_file.write_text(json.dumps({"vault_path": str(tmp_path)}), encoding="utf-8")

        with patch.object(manage_mod, "_load_config", return_value={}):
            result = _cb_configure()(working_memory_ttl={"default": 28, "decision": 56})
        assert "working_memory_ttl" in result
        saved = json.loads(cfg_file.read_text())
        assert saved["working_memory_ttl"]["default"] == 28
        assert saved["working_memory_ttl"]["decision"] == 56

    def test_invalid_ttl_not_dict_raises(self):
        with pytest.raises(ToolError, match="must be a dict"):
            _cb_configure()(working_memory_ttl="not a dict")  # type: ignore[arg-type]

    def test_invalid_ttl_value_not_positive_int_raises(self):
        with pytest.raises(ToolError, match="positive integers"):
            _cb_configure()(working_memory_ttl={"default": 0})

    def test_invalid_ttl_value_negative_raises(self):
        with pytest.raises(ToolError, match="positive integers"):
            _cb_configure()(working_memory_ttl={"default": -5})

    def test_invalid_ttl_value_string_raises(self):
        with pytest.raises(ToolError, match="positive integers"):
            _cb_configure()(working_memory_ttl={"default": "28"})  # type: ignore[dict-item]


# ===========================================================================
# cb_configure — vault_path write path (background index rebuild)
# ===========================================================================

class TestCbConfigureVaultPath:
    def test_vault_path_write_updates_config(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
        cfg_dir = home / ".claude" / "cyberbrain"
        cfg_dir.mkdir(parents=True)
        cfg_file = cfg_dir / "config.json"
        cfg_file.write_text("{}", encoding="utf-8")

        vault = home / "my_vault"

        with patch.object(manage_mod, "_load_config", return_value={}):
            # Patch search_backends to avoid import error in background thread
            with patch.dict(sys.modules, {"search_backends": MagicMock()}):
                result = _cb_configure()(vault_path=str(vault))

        assert vault.exists()
        assert "vault_path" in result
        saved = json.loads(cfg_file.read_text())
        assert "vault_path" in saved
        assert "index rebuild" in result.lower()

    def test_vault_path_outside_home_raises(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

        with pytest.raises(ToolError, match="within your home directory"):
            _cb_configure()(vault_path="/etc/vault")

    def test_vault_path_background_thread_fires(self, tmp_path, monkeypatch):
        """Verify the background index rebuild thread is started (smoke test)."""
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
        cfg_dir = home / ".claude" / "cyberbrain"
        cfg_dir.mkdir(parents=True)
        (cfg_dir / "config.json").write_text("{}", encoding="utf-8")

        threads_before = threading.active_count()
        mock_backend = MagicMock()
        mock_backend.build_full_index = MagicMock()
        mock_sb = MagicMock()
        mock_sb.get_search_backend.return_value = mock_backend

        vault = home / "vault2"
        with patch.object(manage_mod, "_load_config", return_value={}):
            with patch.dict(sys.modules, {"search_backends": mock_sb}):
                _cb_configure()(vault_path=str(vault))

        # Give the background thread a moment to run
        import time
        time.sleep(0.1)
        # No assertion on thread count — just verify no exception was raised


# ===========================================================================
# cb_configure — no-args (status display with runs log)
# ===========================================================================

class TestCbConfigureNoArgs:
    def test_no_args_shows_config(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        cfg = {
            **BASE_CONFIG,
            "vault_path": str(vault),
            "inbox": "AI/Inbox",
            "backend": "ollama",
            "model": "llama3",
        }
        with patch.object(manage_mod, "_load_config", return_value=cfg):
            with patch.object(manage_mod, "_read_index_stats", return_value={"total": 5, "by_type": {}}):
                with patch.object(manage_mod, "RUNS_LOG_PATH", str(tmp_path / "no-runs.log")):
                    result = _cb_configure()()
        assert "Cyberbrain Configuration" in result
        assert "ollama" in result
        assert "AI/Inbox" in result

    def test_no_args_vault_not_set(self, tmp_path):
        cfg = {**BASE_CONFIG, "vault_path": ""}
        with patch.object(manage_mod, "_load_config", return_value=cfg):
            with patch.object(manage_mod, "RUNS_LOG_PATH", str(tmp_path / "no-runs.log")):
                result = _cb_configure()()
        assert "not configured" in result.lower()

    def test_no_args_vault_does_not_exist(self, tmp_path):
        cfg = {**BASE_CONFIG, "vault_path": str(tmp_path / "missing")}
        with patch.object(manage_mod, "_load_config", return_value=cfg):
            with patch.object(manage_mod, "RUNS_LOG_PATH", str(tmp_path / "no-runs.log")):
                result = _cb_configure()()
        assert "does not exist" in result

    def test_no_args_reads_last_run_from_log(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        cfg = {**BASE_CONFIG, "vault_path": str(vault)}

        log_file = tmp_path / "runs.log"
        run_entry = {
            "timestamp": "2026-03-07T12:34:56",
            "session_id": "abc12345xyz",
            "beats_written": 3,
        }
        log_file.write_text(json.dumps(run_entry) + "\n", encoding="utf-8")

        with patch.object(manage_mod, "_load_config", return_value=cfg):
            with patch.object(manage_mod, "_read_index_stats", return_value={"total": 10, "by_type": {}}):
                with patch.object(manage_mod, "RUNS_LOG_PATH", str(log_file)):
                    result = _cb_configure()()
        assert "2026-03-07" in result
        assert "abc12345" in result
        assert "3 beats" in result

    def test_no_args_empty_log_file(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        cfg = {**BASE_CONFIG, "vault_path": str(vault)}

        log_file = tmp_path / "runs.log"
        log_file.write_text("", encoding="utf-8")

        with patch.object(manage_mod, "_load_config", return_value=cfg):
            with patch.object(manage_mod, "_read_index_stats", return_value={"total": 0, "by_type": {}}):
                with patch.object(manage_mod, "RUNS_LOG_PATH", str(log_file)):
                    result = _cb_configure()()
        # Should still return without error
        assert "Cyberbrain Configuration" in result

    def test_no_args_log_with_invalid_json_lines(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        cfg = {**BASE_CONFIG, "vault_path": str(vault)}

        log_file = tmp_path / "runs.log"
        log_file.write_text("not-json\nalso-not-json\n", encoding="utf-8")

        with patch.object(manage_mod, "_load_config", return_value=cfg):
            with patch.object(manage_mod, "_read_index_stats", return_value={}):
                with patch.object(manage_mod, "RUNS_LOG_PATH", str(log_file)):
                    result = _cb_configure()()
        assert "Cyberbrain Configuration" in result


# ===========================================================================
# cb_status
# ===========================================================================

class TestCbStatus:
    def test_basic_call_no_runs_log(self, tmp_path):
        cfg = {**BASE_CONFIG, "vault_path": ""}
        with patch.object(manage_mod, "_load_config", return_value=cfg):
            with patch.object(manage_mod, "_read_index_stats", return_value={}):
                with patch.object(manage_mod, "RUNS_LOG_PATH", str(tmp_path / "no-log.log")):
                    result = _cb_status()()
        assert "Cyberbrain Status" in result
        assert "No runs recorded" in result
        assert "Index not found" in result

    def test_with_runs_log(self, tmp_path):
        cfg = {**BASE_CONFIG, "vault_path": ""}
        log_file = tmp_path / "runs.log"
        run1 = {
            "timestamp": "2026-03-07T10:00:00",
            "session_id": "sess0001",
            "project": "my-project",
            "trigger": "compact",
            "beats_written": 2,
            "beats_extracted": 3,
            "duration_seconds": 5,
            "beats": [
                {"title": "Beat A", "type": "insight", "scope": "project", "path": "/vault/beat-a.md"},
            ],
            "errors": [],
        }
        log_file.write_text(json.dumps(run1) + "\n", encoding="utf-8")

        with patch.object(manage_mod, "_load_config", return_value=cfg):
            with patch.object(manage_mod, "_read_index_stats", return_value={}):
                with patch.object(manage_mod, "RUNS_LOG_PATH", str(log_file)):
                    result = _cb_status()()
        assert "sess0001" in result
        assert "my-project" in result
        assert "Beat A" in result

    def test_with_index_stats(self, tmp_path):
        cfg = {**BASE_CONFIG, "vault_path": ""}
        stats = {
            "total": 42,
            "by_type": {"insight": 20, "decision": 22},
            "relations_count": 10,
            "stale_count": 0,
        }
        with patch.object(manage_mod, "_load_config", return_value=cfg):
            with patch.object(manage_mod, "_read_index_stats", return_value=stats):
                with patch.object(manage_mod, "RUNS_LOG_PATH", str(tmp_path / "no-log.log")):
                    result = _cb_status()()
        assert "42" in result
        assert "insight: 20" in result
        assert "Relations: 10" in result
        assert "all indexed notes exist" in result

    def test_with_stale_paths(self, tmp_path):
        cfg = {**BASE_CONFIG, "vault_path": ""}
        stats = {
            "total": 5,
            "by_type": {},
            "relations_count": 0,
            "stale_count": 2,
        }
        with patch.object(manage_mod, "_load_config", return_value=cfg):
            with patch.object(manage_mod, "_read_index_stats", return_value=stats):
                with patch.object(manage_mod, "RUNS_LOG_PATH", str(tmp_path / "no-log.log")):
                    result = _cb_status()()
        assert "2 path(s) not found" in result

    def test_with_vault_prefs_section(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        _write_claude_md(vault, "## Cyberbrain Preferences\n\n- Pref A\n- Pref B\n")
        cfg = {**BASE_CONFIG, "vault_path": str(vault)}

        with patch.object(manage_mod, "_load_config", return_value=cfg):
            with patch.object(manage_mod, "_read_index_stats", return_value={}):
                with patch.object(manage_mod, "RUNS_LOG_PATH", str(tmp_path / "no-log.log")):
                    result = _cb_status()()
        assert "Preferences: set" in result

    def test_with_vault_no_prefs_section(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        _write_claude_md(vault, "# My Vault\n\nNo prefs.\n")
        cfg = {**BASE_CONFIG, "vault_path": str(vault)}

        with patch.object(manage_mod, "_load_config", return_value=cfg):
            with patch.object(manage_mod, "_read_index_stats", return_value={}):
                with patch.object(manage_mod, "RUNS_LOG_PATH", str(tmp_path / "no-log.log")):
                    result = _cb_status()()
        assert "Preferences: not set" in result

    def test_with_manifest_model(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        cfg = {**BASE_CONFIG, "vault_path": ""}
        stats = {
            "total": 10,
            "by_type": {},
            "relations_count": 0,
            "stale_count": 0,
        }
        manifest_path = tmp_path / "manifest.json"
        manifest = {"model_name": "all-minilm", "id_map": ["a", "b", "c"]}
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        with patch.object(manage_mod, "_load_config", return_value={
            **cfg,
            "search_manifest_path": str(manifest_path),
        }):
            with patch.object(manage_mod, "_read_index_stats", return_value=stats):
                with patch.object(manage_mod, "RUNS_LOG_PATH", str(tmp_path / "no-log.log")):
                    result = _cb_status()()
        assert "all-minilm" in result
        assert "3" in result

    def test_last_n_runs_parameter(self, tmp_path):
        cfg = {**BASE_CONFIG, "vault_path": ""}
        log_file = tmp_path / "runs.log"
        # Write 5 run entries
        entries = []
        for i in range(5):
            entries.append(json.dumps({
                "timestamp": f"2026-03-0{i+1}T10:00:00",
                "session_id": f"sess000{i}",
                "project": "proj",
                "trigger": "compact",
                "beats_written": i,
                "beats_extracted": i,
                "duration_seconds": 1,
            }))
        log_file.write_text("\n".join(entries) + "\n", encoding="utf-8")

        with patch.object(manage_mod, "_load_config", return_value=cfg):
            with patch.object(manage_mod, "_read_index_stats", return_value={}):
                with patch.object(manage_mod, "RUNS_LOG_PATH", str(log_file)):
                    result = _cb_status()(last_n_runs=3)
        assert "last 3" in result

    def test_runs_with_errors(self, tmp_path):
        cfg = {**BASE_CONFIG, "vault_path": ""}
        log_file = tmp_path / "runs.log"
        run = {
            "timestamp": "2026-03-07T10:00:00",
            "session_id": "errsess01",
            "project": "proj",
            "trigger": "compact",
            "beats_written": 0,
            "beats_extracted": 0,
            "duration_seconds": 2,
            "beats": [],
            "errors": ["Something went wrong"],
        }
        log_file.write_text(json.dumps(run) + "\n", encoding="utf-8")

        with patch.object(manage_mod, "_load_config", return_value=cfg):
            with patch.object(manage_mod, "_read_index_stats", return_value={}):
                with patch.object(manage_mod, "RUNS_LOG_PATH", str(log_file)):
                    result = _cb_status()()
        assert "Something went wrong" in result

    def test_runs_with_no_beats_and_no_errors(self, tmp_path):
        cfg = {**BASE_CONFIG, "vault_path": ""}
        log_file = tmp_path / "runs.log"
        run = {
            "timestamp": "2026-03-07T10:00:00",
            "session_id": "emptysess",
            "project": "proj",
            "trigger": "compact",
            "beats_written": 0,
            "beats_extracted": 0,
            "duration_seconds": 1,
            "beats": [],
            "errors": [],
        }
        log_file.write_text(json.dumps(run) + "\n", encoding="utf-8")

        with patch.object(manage_mod, "_load_config", return_value=cfg):
            with patch.object(manage_mod, "_read_index_stats", return_value={}):
                with patch.object(manage_mod, "RUNS_LOG_PATH", str(log_file)):
                    result = _cb_status()()
        assert "No beats written in last run" in result

    def test_working_memory_stats(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        wm_folder = vault / "AI" / "Working Memory"
        wm_folder.mkdir(parents=True)

        # Write a working memory note with a past review date
        note = wm_folder / "open-bug.md"
        note.write_text(
            "---\ncb_review_after: '2026-01-01'\n---\n\n## Open Bug\n\nDetails here.\n",
            encoding="utf-8",
        )

        cfg = {**BASE_CONFIG, "vault_path": str(vault)}
        with patch.object(manage_mod, "_load_config", return_value=cfg):
            with patch.object(manage_mod, "_read_index_stats", return_value={}):
                with patch.object(manage_mod, "RUNS_LOG_PATH", str(tmp_path / "no-log.log")):
                    result = _cb_status()()
        assert "Working memory" in result
        assert "due for review" in result

    def test_working_memory_not_due(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        wm_folder = vault / "AI" / "Working Memory"
        wm_folder.mkdir(parents=True)

        note = wm_folder / "future-note.md"
        note.write_text(
            "---\ncb_review_after: '2099-12-31'\n---\n\n## Future Note\n\nDetails.\n",
            encoding="utf-8",
        )

        cfg = {**BASE_CONFIG, "vault_path": str(vault)}
        with patch.object(manage_mod, "_load_config", return_value=cfg):
            with patch.object(manage_mod, "_read_index_stats", return_value={}):
                with patch.object(manage_mod, "RUNS_LOG_PATH", str(tmp_path / "no-log.log")):
                    result = _cb_status()()
        assert "Working memory" in result
        # Should not show "due for review" when nothing is due
        assert "due for review" not in result

    def test_oserror_reading_runs_log(self, tmp_path):
        """cb_status should not crash if reading the runs log raises OSError."""
        cfg = {**BASE_CONFIG, "vault_path": ""}
        # Point RUNS_LOG_PATH at a directory so read_text raises IsADirectoryError (OSError)
        log_dir = tmp_path / "runs_log_dir"
        log_dir.mkdir()
        with patch.object(manage_mod, "_load_config", return_value=cfg):
            with patch.object(manage_mod, "_read_index_stats", return_value={}):
                with patch.object(manage_mod, "RUNS_LOG_PATH", str(log_dir)):
                    result = _cb_status()()
        assert "Cyberbrain Status" in result
        assert "No runs recorded" in result


# ===========================================================================
# cb_configure — discover mode
# ===========================================================================

class TestCbConfigureDiscover:
    def test_discover_no_vaults_found(self, tmp_path, monkeypatch):
        # All search roots don't exist in tmp_path home
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
        with patch.object(manage_mod, "_load_config", return_value={}):
            result = _cb_configure()(discover=True)
        assert "No Obsidian vaults found" in result

    def test_discover_finds_vaults(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

        # Create a fake Obsidian vault under ~/Documents
        docs = home / "Documents"
        vault1 = docs / "MyVault"
        (vault1 / ".obsidian").mkdir(parents=True)

        with patch.object(manage_mod, "_load_config", return_value={}):
            result = _cb_configure()(discover=True)
        assert "Found Obsidian vaults" in result
        assert "MyVault" in result
        assert "cb_configure(vault_path=" in result


# ===========================================================================
# cb_configure — inbox and capture_mode write paths
# ===========================================================================

class TestCbConfigureInboxAndCaptureMode:
    def test_inbox_write(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
        cfg_dir = home / ".claude" / "cyberbrain"
        cfg_dir.mkdir(parents=True)
        (cfg_dir / "config.json").write_text("{}", encoding="utf-8")

        with patch.object(manage_mod, "_load_config", return_value={}):
            result = _cb_configure()(inbox="AI/MyInbox")
        assert "inbox" in result
        assert "AI/MyInbox" in result
        saved = json.loads((cfg_dir / "config.json").read_text())
        assert saved["inbox"] == "AI/MyInbox"

    def test_capture_mode_valid(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
        cfg_dir = home / ".claude" / "cyberbrain"
        cfg_dir.mkdir(parents=True)
        (cfg_dir / "config.json").write_text("{}", encoding="utf-8")

        with patch.object(manage_mod, "_load_config", return_value={}):
            result = _cb_configure()(capture_mode="auto")
        assert "desktop_capture_mode" in result
        assert "auto" in result

    def test_capture_mode_invalid_raises(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
        cfg_dir = home / ".claude" / "cyberbrain"
        cfg_dir.mkdir(parents=True)
        (cfg_dir / "config.json").write_text("{}", encoding="utf-8")

        with pytest.raises(ToolError, match="capture_mode must be"):
            _cb_configure()(capture_mode="invalid")

    def test_multiple_writes_in_one_call(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
        cfg_dir = home / ".claude" / "cyberbrain"
        cfg_dir.mkdir(parents=True)
        (cfg_dir / "config.json").write_text("{}", encoding="utf-8")

        with patch.object(manage_mod, "_load_config", return_value={}):
            result = _cb_configure()(inbox="AI/Notes", capture_mode="suggest")
        assert "inbox" in result
        assert "capture_mode" in result or "desktop_capture_mode" in result


# ===========================================================================
# _read_index_stats (direct unit tests)
# ===========================================================================

class TestReadIndexStats:
    def test_returns_empty_dict_on_missing_db(self, tmp_path):
        cfg = {"search_db_path": str(tmp_path / "nonexistent.db")}
        result = manage_mod._read_index_stats(cfg)
        assert result == {}

    def test_returns_stats_from_real_db(self, tmp_path):
        import sqlite3
        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        conn.execute(
            "CREATE TABLE notes (path TEXT, type TEXT)"
        )
        conn.execute(
            "CREATE TABLE relations (id INTEGER PRIMARY KEY)"
        )
        conn.execute("INSERT INTO notes VALUES ('/vault/a.md', 'insight')")
        conn.execute("INSERT INTO notes VALUES ('/vault/b.md', 'decision')")
        conn.execute("INSERT INTO notes VALUES ('/vault/c.md', 'insight')")
        conn.commit()
        conn.close()

        cfg = {"search_db_path": db_path}
        result = manage_mod._read_index_stats(cfg)
        assert result["total"] == 3
        assert result["by_type"]["insight"] == 2
        assert result["by_type"]["decision"] == 1
        assert result["relations_count"] == 0
        # All paths don't exist so all are stale
        assert result["stale_count"] == 3

    def test_stale_count_for_existing_paths(self, tmp_path):
        import sqlite3
        db_path = str(tmp_path / "test2.db")
        real_file = tmp_path / "real.md"
        real_file.write_text("content", encoding="utf-8")

        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE notes (path TEXT, type TEXT)")
        conn.execute("CREATE TABLE relations (id INTEGER PRIMARY KEY)")
        conn.execute(f"INSERT INTO notes VALUES ('{real_file}', 'insight')")
        conn.execute("INSERT INTO notes VALUES ('/nonexistent/path.md', 'decision')")
        conn.commit()
        conn.close()

        cfg = {"search_db_path": db_path}
        result = manage_mod._read_index_stats(cfg)
        assert result["total"] == 2
        assert result["stale_count"] == 1  # Only the nonexistent one is stale


# ===========================================================================
# cb_status — sqlite provenance block
# ===========================================================================

class TestCbStatusProvenanceCoverage:
    def test_vault_with_sqlite_db(self, tmp_path):
        """Covers the sqlite provenance block in cb_status when vault exists and db is queryable."""
        import sqlite3
        vault = tmp_path / "vault"
        vault.mkdir()
        _write_claude_md(vault, "# Vault\n")

        db_path = tmp_path / "search.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE notes (path TEXT, type TEXT)")
        conn.commit()
        conn.close()

        cfg = {
            **BASE_CONFIG,
            "vault_path": str(vault),
            "search_db_path": str(db_path),
        }
        with patch.object(manage_mod, "_load_config", return_value=cfg):
            with patch.object(manage_mod, "_read_index_stats", return_value={}):
                with patch.object(manage_mod, "RUNS_LOG_PATH", str(tmp_path / "no-log.log")):
                    result = _cb_status()()
        assert "Cyberbrain Status" in result

    def test_vault_with_no_notes_table_db(self, tmp_path):
        """Covers provenance exception branch when db exists but has no 'notes' table."""
        import sqlite3
        vault = tmp_path / "vault"
        vault.mkdir()
        _write_claude_md(vault, "# Vault\n")

        db_path = tmp_path / "empty.db"
        conn = sqlite3.connect(str(db_path))
        conn.commit()
        conn.close()

        cfg = {
            **BASE_CONFIG,
            "vault_path": str(vault),
            "search_db_path": str(db_path),
        }
        with patch.object(manage_mod, "_load_config", return_value=cfg):
            with patch.object(manage_mod, "_read_index_stats", return_value={}):
                with patch.object(manage_mod, "RUNS_LOG_PATH", str(tmp_path / "no-log.log")):
                    # Should not raise — exception is caught silently
                    result = _cb_status()()
        assert "Cyberbrain Status" in result

    def test_invalid_json_in_runs_log_skipped(self, tmp_path):
        """Covers JSONDecodeError branch in cb_status runs log parsing."""
        cfg = {**BASE_CONFIG, "vault_path": ""}
        log_file = tmp_path / "runs.log"
        log_file.write_text("not-valid-json\nalso-bad\n", encoding="utf-8")

        with patch.object(manage_mod, "_load_config", return_value=cfg):
            with patch.object(manage_mod, "_read_index_stats", return_value={}):
                with patch.object(manage_mod, "RUNS_LOG_PATH", str(log_file)):
                    result = _cb_status()()
        assert "No runs recorded" in result

    def test_oserror_reading_runs_log_in_status(self, tmp_path):
        """Covers OSError branch in cb_status runs log reading."""
        cfg = {**BASE_CONFIG, "vault_path": ""}
        log_dir = tmp_path / "runs_dir"
        log_dir.mkdir()

        with patch.object(manage_mod, "_load_config", return_value=cfg):
            with patch.object(manage_mod, "_read_index_stats", return_value={}):
                with patch.object(manage_mod, "RUNS_LOG_PATH", str(log_dir)):
                    result = _cb_status()()
        assert "No runs recorded" in result

    def test_manifest_read_exception_handled(self, tmp_path):
        """Covers manifest exception branch when manifest file is invalid JSON."""
        cfg = {**BASE_CONFIG, "vault_path": ""}
        manifest_path = tmp_path / "bad_manifest.json"
        manifest_path.write_text("not-json!", encoding="utf-8")

        with patch.object(manage_mod, "_load_config", return_value={
            **cfg,
            "search_manifest_path": str(manifest_path),
        }):
            with patch.object(manage_mod, "_read_index_stats", return_value={}):
                with patch.object(manage_mod, "RUNS_LOG_PATH", str(tmp_path / "no-log.log")):
                    result = _cb_status()()
        assert "Cyberbrain Status" in result

    def test_working_memory_note_without_frontmatter_delimiter(self, tmp_path):
        """Covers the 'not text.startswith(---) → continue' branch in working memory scan."""
        vault = tmp_path / "vault"
        vault.mkdir()
        wm_folder = vault / "AI" / "Working Memory"
        wm_folder.mkdir(parents=True)

        # Note without YAML frontmatter
        note = wm_folder / "no-frontmatter.md"
        note.write_text("## Just a note\n\nNo frontmatter here.\n", encoding="utf-8")

        cfg = {**BASE_CONFIG, "vault_path": str(vault)}
        with patch.object(manage_mod, "_load_config", return_value=cfg):
            with patch.object(manage_mod, "_read_index_stats", return_value={}):
                with patch.object(manage_mod, "RUNS_LOG_PATH", str(tmp_path / "no-log.log")):
                    result = _cb_status()()
        assert "Working memory" in result

    def test_working_memory_note_with_unclosed_frontmatter(self, tmp_path):
        """Covers the 'end == -1 → continue' branch (no closing ---)."""
        vault = tmp_path / "vault"
        vault.mkdir()
        wm_folder = vault / "AI" / "Working Memory"
        wm_folder.mkdir(parents=True)

        # Note with opening --- but no closing ---
        note = wm_folder / "unclosed.md"
        note.write_text("---\ncb_review_after: '2026-01-01'\n## No closing delimiter\n", encoding="utf-8")

        cfg = {**BASE_CONFIG, "vault_path": str(vault)}
        with patch.object(manage_mod, "_load_config", return_value=cfg):
            with patch.object(manage_mod, "_read_index_stats", return_value={}):
                with patch.object(manage_mod, "RUNS_LOG_PATH", str(tmp_path / "no-log.log")):
                    result = _cb_status()()
        assert "Working memory" in result

    def test_working_memory_yaml_parse_exception_handled(self, tmp_path):
        """Covers the except Exception branch when yaml.safe_load raises."""
        import yaml
        vault = tmp_path / "vault"
        vault.mkdir()
        wm_folder = vault / "AI" / "Working Memory"
        wm_folder.mkdir(parents=True)

        # Valid-looking frontmatter to pass the startswith/end checks
        note = wm_folder / "valid-looking.md"
        note.write_text("---\ncb_review_after: '2026-01-01'\n---\n\n## Note\n", encoding="utf-8")

        cfg = {**BASE_CONFIG, "vault_path": str(vault)}
        with patch.object(manage_mod, "_load_config", return_value=cfg):
            with patch.object(manage_mod, "_read_index_stats", return_value={}):
                with patch.object(manage_mod, "RUNS_LOG_PATH", str(tmp_path / "no-log.log")):
                    with patch("yaml.safe_load", side_effect=yaml.YAMLError("bad yaml")):
                        result = _cb_status()()
        # Should not crash — exception is caught
        assert "Working memory" in result


# ===========================================================================
# cb_configure — additional edge cases
# ===========================================================================

class TestCbConfigureEdgeCases:
    def test_load_raw_bad_json_returns_empty(self, tmp_path, monkeypatch):
        """Covers the exception branch in _load_raw when config file has bad JSON."""
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
        cfg_dir = home / ".claude" / "cyberbrain"
        cfg_dir.mkdir(parents=True)
        # Write invalid JSON to config file
        (cfg_dir / "config.json").write_text("not valid json!!!", encoding="utf-8")

        with patch.object(manage_mod, "_load_config", return_value={}):
            result = _cb_configure()(inbox="AI/Test")
        # Should succeed, treating bad JSON as empty config
        assert "inbox" in result

    def test_discover_permission_error_continues(self, tmp_path, monkeypatch):
        """Covers the PermissionError/OSError exception branch in discover mode."""
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

        # Create Documents dir so it enters the loop, then mock rglob to raise PermissionError
        docs = home / "Documents"
        docs.mkdir()

        original_rglob = Path.rglob

        def mock_rglob(self, pattern):
            if self == docs:
                raise PermissionError("Permission denied")
            return original_rglob(self, pattern)

        with patch.object(Path, "rglob", mock_rglob):
            with patch.object(manage_mod, "_load_config", return_value={}):
                result = _cb_configure()(discover=True)
        # With no vaults found (PermissionError skipped), should return "No Obsidian vaults found"
        assert "No Obsidian vaults found" in result

    def test_no_args_general_exception_in_log_reading(self, tmp_path):
        """Covers the outer except Exception branch when reading the runs log raises non-OSError."""
        vault = tmp_path / "vault"
        vault.mkdir()
        cfg = {**BASE_CONFIG, "vault_path": str(vault)}

        with patch.object(manage_mod, "_load_config", return_value=cfg):
            with patch.object(manage_mod, "_read_index_stats", return_value={"total": 0, "by_type": {}}):
                # Use a non-existent path that will pass Path.exists() check but fail read
                # We achieve this by creating a directory at the log path (IsADirectoryError)
                log_dir = tmp_path / "log_as_dir"
                log_dir.mkdir()
                with patch.object(manage_mod, "RUNS_LOG_PATH", str(log_dir)):
                    result = _cb_configure()()
        assert "Cyberbrain Configuration" in result

    def test_discover_stops_at_10_vaults(self, tmp_path, monkeypatch):
        """Covers the 'len(found) >= 10 → break' branch in discover mode."""
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

        docs = home / "Documents"
        docs.mkdir()

        # Create 11 fake Obsidian vaults
        for i in range(11):
            vault_dir = docs / f"Vault{i}"
            (vault_dir / ".obsidian").mkdir(parents=True)

        with patch.object(manage_mod, "_load_config", return_value={}):
            result = _cb_configure()(discover=True)
        assert "Found Obsidian vaults" in result
        # Should cap at 10
        count = result.count("\n  ")
        assert count <= 11  # At most 10 vaults + trailing message line
