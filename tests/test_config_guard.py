"""
test_config_guard.py — unit tests for require_config() in shared.py

Covers:
- Guard raises ToolError with canonical message when config file is absent
- Guard raises ToolError when config file is unreadable (bad JSON)
- Guard raises ToolError when vault_path is absent from config
- Guard raises ToolError when vault_path is the placeholder value
- Guard raises ToolError when vault_path does not exist on disk
- Guard passes (returns config dict) when all conditions are met
- Guard includes the specific issue in the error message for each failure mode
- Guard passes the cwd through to resolve_config on success
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

try:
    from fastmcp.exceptions import ToolError
except ImportError:

    class ToolError(Exception):  # type: ignore[no-redef]
        pass


def _get_require_config():
    """Always return the live require_config from the current shared module.

    test_setup_enrich_tools.py clears and re-imports cyberbrain.mcp.shared,
    which means the module object changes between test files. Fetching it fresh
    every time ensures we call the function that lives in the active module.
    """
    import cyberbrain.mcp.shared as _shared

    return _shared.require_config


def _get_shared_module():
    """Return the current live shared module."""
    return sys.modules["cyberbrain.mcp.shared"]


_CANONICAL_NOT_CONFIGURED_MSG = "Cyberbrain is not configured"
_CANONICAL_RUN_CONFIG_MSG = "/cyberbrain:config"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_config(config_path: Path, data: dict) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(data), encoding="utf-8")


# ---------------------------------------------------------------------------
# Check 1: config file existence
# ---------------------------------------------------------------------------


class TestRequireConfigMissingFile:
    def test_raises_when_no_config_file(self, tmp_path):
        """ToolError with canonical message when ~/.claude/cyberbrain/config.json is absent."""
        nonexistent = tmp_path / "no" / "config.json"
        with patch("cyberbrain.extractors.config.GLOBAL_CONFIG_PATH", nonexistent):
            with pytest.raises(ToolError) as exc_info:
                _get_require_config()()
        msg = str(exc_info.value)
        assert _CANONICAL_NOT_CONFIGURED_MSG in msg
        assert _CANONICAL_RUN_CONFIG_MSG in msg

    def test_error_message_is_actionable(self, tmp_path):
        """The error message tells the user what to do next."""
        nonexistent = tmp_path / "no" / "config.json"
        with patch("cyberbrain.extractors.config.GLOBAL_CONFIG_PATH", nonexistent):
            with pytest.raises(ToolError) as exc_info:
                _get_require_config()()
        assert "/cyberbrain:config" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Check 2a: config file exists but is invalid JSON
# ---------------------------------------------------------------------------


class TestRequireConfigUnreadable:
    def test_raises_when_config_is_invalid_json(self, tmp_path):
        """ToolError when config.json contains malformed JSON."""
        bad_path = tmp_path / "config.json"
        bad_path.parent.mkdir(parents=True, exist_ok=True)
        bad_path.write_text("{ this is not json }", encoding="utf-8")
        with patch("cyberbrain.extractors.config.GLOBAL_CONFIG_PATH", bad_path):
            with pytest.raises(ToolError) as exc_info:
                _get_require_config()()
        msg = str(exc_info.value).lower()
        assert "unreadable" in msg or "not configured" in msg


# ---------------------------------------------------------------------------
# Check 2b: vault_path absent or empty
# ---------------------------------------------------------------------------


class TestRequireConfigNoVaultPath:
    def test_raises_when_vault_path_absent(self, tmp_path):
        """ToolError when config.json exists but has no vault_path key."""
        cfg_path = tmp_path / "config.json"
        _write_config(cfg_path, {"inbox": "AI/Claude-Sessions"})
        with patch("cyberbrain.extractors.config.GLOBAL_CONFIG_PATH", cfg_path):
            with pytest.raises(ToolError) as exc_info:
                _get_require_config()()
        assert _CANONICAL_NOT_CONFIGURED_MSG in str(exc_info.value)

    def test_raises_when_vault_path_is_empty_string(self, tmp_path):
        """ToolError when vault_path is present but empty."""
        cfg_path = tmp_path / "config.json"
        _write_config(cfg_path, {"vault_path": "", "inbox": "AI/Claude-Sessions"})
        with patch("cyberbrain.extractors.config.GLOBAL_CONFIG_PATH", cfg_path):
            with pytest.raises(ToolError) as exc_info:
                _get_require_config()()
        assert _CANONICAL_NOT_CONFIGURED_MSG in str(exc_info.value)


# ---------------------------------------------------------------------------
# Check 2c: vault_path is placeholder
# ---------------------------------------------------------------------------


class TestRequireConfigPlaceholder:
    def test_raises_when_vault_path_is_placeholder(self, tmp_path):
        """ToolError when vault_path is the default placeholder value."""
        cfg_path = tmp_path / "config.json"
        _write_config(
            cfg_path,
            {
                "vault_path": "/path/to/your/ObsidianVault",
                "inbox": "AI/Claude-Sessions",
            },
        )
        with patch("cyberbrain.extractors.config.GLOBAL_CONFIG_PATH", cfg_path):
            with pytest.raises(ToolError) as exc_info:
                _get_require_config()()
        assert "placeholder" in str(exc_info.value).lower()
        assert _CANONICAL_RUN_CONFIG_MSG in str(exc_info.value)

    def test_placeholder_message_includes_specific_issue(self, tmp_path):
        """The error message for placeholder vault_path mentions the specific issue."""
        cfg_path = tmp_path / "config.json"
        _write_config(
            cfg_path,
            {
                "vault_path": "/path/to/your/ObsidianVault",
                "inbox": "AI/Claude-Sessions",
            },
        )
        with patch("cyberbrain.extractors.config.GLOBAL_CONFIG_PATH", cfg_path):
            with pytest.raises(ToolError) as exc_info:
                _get_require_config()()
        assert "placeholder" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Check 3: vault_path does not exist on disk
# ---------------------------------------------------------------------------


class TestRequireConfigVaultNotOnDisk:
    def test_raises_when_vault_path_does_not_exist(self, tmp_path):
        """ToolError when vault_path is set but the directory does not exist."""
        cfg_path = tmp_path / "config.json"
        nonexistent_vault = str(tmp_path / "nonexistent-vault")
        _write_config(
            cfg_path,
            {"vault_path": nonexistent_vault, "inbox": "AI/Claude-Sessions"},
        )
        with patch("cyberbrain.extractors.config.GLOBAL_CONFIG_PATH", cfg_path):
            with pytest.raises(ToolError) as exc_info:
                _get_require_config()()
        msg = str(exc_info.value)
        assert "does not exist" in msg
        assert _CANONICAL_RUN_CONFIG_MSG in msg

    def test_error_message_includes_the_bad_path(self, tmp_path):
        """The error message for missing vault_path includes the actual bad path."""
        cfg_path = tmp_path / "config.json"
        nonexistent_vault = str(tmp_path / "bad-vault-path")
        _write_config(
            cfg_path,
            {"vault_path": nonexistent_vault, "inbox": "AI/Claude-Sessions"},
        )
        with patch("cyberbrain.extractors.config.GLOBAL_CONFIG_PATH", cfg_path):
            with pytest.raises(ToolError) as exc_info:
                _get_require_config()()
        assert nonexistent_vault in str(exc_info.value)


# ---------------------------------------------------------------------------
# Happy path: all conditions met
# ---------------------------------------------------------------------------


class TestRequireConfigSuccess:
    def test_returns_config_dict_when_all_valid(self, tmp_path):
        """Returns a dict with vault_path when config is fully valid."""
        vault = tmp_path / "vault"
        vault.mkdir()
        cfg_path = tmp_path / "config.json"
        expected_config = {
            "vault_path": str(vault),
            "inbox": "AI/Claude-Sessions",
            "backend": "claude-code",
            "model": "claude-haiku-4-5",
        }
        _write_config(cfg_path, expected_config)
        shared_mod = _get_shared_module()
        with patch("cyberbrain.extractors.config.GLOBAL_CONFIG_PATH", cfg_path):
            with patch.object(
                shared_mod,
                "_resolve_config",
                return_value=expected_config,
            ):
                result = _get_require_config()()

        assert isinstance(result, dict)
        assert result["vault_path"] == str(vault)

    def test_passes_cwd_to_resolve_config(self, tmp_path):
        """The cwd argument is forwarded to _resolve_config on success."""
        vault = tmp_path / "vault"
        vault.mkdir()
        cfg_path = tmp_path / "config.json"
        _write_config(
            cfg_path,
            {
                "vault_path": str(vault),
                "inbox": "AI/Claude-Sessions",
                "backend": "claude-code",
                "model": "claude-haiku-4-5",
            },
        )
        project_cwd = "/my/project"
        shared_mod = _get_shared_module()
        with patch("cyberbrain.extractors.config.GLOBAL_CONFIG_PATH", cfg_path):
            with patch.object(
                shared_mod,
                "_resolve_config",
                return_value={"vault_path": str(vault), "inbox": "AI/Claude-Sessions"},
            ) as mock_resolve:
                _get_require_config()(cwd=project_cwd)

        mock_resolve.assert_called_once_with(project_cwd)

    def test_defaults_cwd_to_home_when_omitted(self, tmp_path):
        """When cwd is omitted, _resolve_config is called with str(Path.home())."""
        vault = tmp_path / "vault"
        vault.mkdir()
        cfg_path = tmp_path / "config.json"
        _write_config(
            cfg_path,
            {
                "vault_path": str(vault),
                "inbox": "AI/Claude-Sessions",
                "backend": "claude-code",
                "model": "claude-haiku-4-5",
            },
        )
        shared_mod = _get_shared_module()
        with patch("cyberbrain.extractors.config.GLOBAL_CONFIG_PATH", cfg_path):
            with patch.object(
                shared_mod,
                "_resolve_config",
                return_value={"vault_path": str(vault), "inbox": "AI/Claude-Sessions"},
            ) as mock_resolve:
                _get_require_config()()

        called_cwd = mock_resolve.call_args[0][0]
        assert called_cwd == str(Path.home())


# ---------------------------------------------------------------------------
# Tool integration: cb_* tools raise guard error before any logic
# ---------------------------------------------------------------------------


class TestToolsRaiseGuardError:
    """Verify that cb_* tools surface the guard error when config is absent.

    These tests use patch.object on the tool module's require_config binding to
    simulate an unconfigured state without touching the filesystem.
    """

    def test_cb_extract_raises_guard_error(self, tmp_path, monkeypatch):
        """cb_extract raises ToolError from guard when not configured."""
        import cyberbrain.mcp.tools.extract as extract_mod

        class FakeMCP:
            def tool(self, annotations=None, **kwargs):
                def deco(fn):
                    self._fn = fn
                    return fn

                return deco

        fake = FakeMCP()
        extract_mod.register(fake)

        # Simulate unconfigured: make require_config raise ToolError
        with patch.object(
            extract_mod,
            "require_config",
            side_effect=ToolError(
                "Cyberbrain is not configured. Run /cyberbrain:config to set up your vault."
            ),
        ):
            with pytest.raises(ToolError, match="Cyberbrain is not configured"):
                # transcript_path must be in ~/.claude/projects/ to pass the path check
                projects_dir = tmp_path / ".claude" / "projects"
                projects_dir.mkdir(parents=True)
                tf = projects_dir / "session.jsonl"
                tf.write_text(
                    '{"type":"user","message":{"role":"user","content":"hi"}}\n'
                )
                monkeypatch.setattr(
                    Path,
                    "home",
                    classmethod(lambda cls: tmp_path),
                )
                fake._fn(transcript_path=str(tf))

    def test_cb_recall_raises_guard_error(self):
        """cb_recall raises ToolError from guard when not configured."""
        import cyberbrain.mcp.tools.recall as recall_mod

        class FakeMCP:
            def __init__(self):
                self._tools = {}

            def tool(self, annotations=None, **kwargs):
                def deco(fn):
                    self._tools[fn.__name__] = fn
                    return fn

                return deco

        fake = FakeMCP()
        recall_mod.register(fake)
        cb_recall = fake._tools["cb_recall"]

        with patch.object(
            recall_mod,
            "require_config",
            side_effect=ToolError(
                "Cyberbrain is not configured. Run /cyberbrain:config to set up your vault."
            ),
        ):
            with pytest.raises(ToolError, match="Cyberbrain is not configured"):
                cb_recall(query="some query about anything")
