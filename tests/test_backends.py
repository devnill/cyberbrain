"""
test_backends.py — unit tests for the LLM backend abstraction in extract_beats.py

Each backend has a distinct integration point. Tests verify that:
- The correct external call is made (subprocess or HTTP)
- Configuration (model, region, URL) is wired through correctly
- Errors are surfaced as BackendError, not raw exceptions
- Security constraints (env var stripping) are enforced
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

import extractors.extract_beats as eb
import backends as _backends_module


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = "You are a test assistant."
USER_MESSAGE = "Extract beats from this."

BASE_CONFIG = {
    "vault_path": "/tmp/vault",
    "inbox": "AI/Claude-Sessions",
    "model": "claude-haiku-4-5",
    "claude_timeout": 30,
}


def make_config(**overrides):
    return {**BASE_CONFIG, **overrides}


# ===========================================================================
# claude-code backend
# ===========================================================================

class TestClaudeCodeBackend:
    """_call_claude_code() shells out to the 'claude' CLI subprocess."""

    def test_strips_required_env_vars_before_subprocess(self, monkeypatch):
        """
        CLAUDECODE, CLAUDE_CODE_ENTRYPOINT, CLAUDE_CODE_DISABLE_FEEDBACK_SURVEY,
        and CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC are stripped from the subprocess
        environment to prevent nested-session hangs.
        """
        # Set up the dangerous env vars in the current environment
        monkeypatch.setenv("CLAUDECODE", "1")
        monkeypatch.setenv("CLAUDE_CODE_ENTRYPOINT", "cli")
        monkeypatch.setenv("CLAUDE_CODE_DISABLE_FEEDBACK_SURVEY", "1")
        monkeypatch.setenv("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", "1")
        monkeypatch.setenv("SAFE_VAR", "keep-me")

        captured_env = {}

        def fake_run(cmd, **kwargs):
            captured_env.update(kwargs.get("env", {}))
            result = MagicMock()
            result.returncode = 0
            result.stdout = '[]'
            result.stderr = ''
            return result

        config = make_config(backend="claude-code")

        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            with patch("subprocess.run", side_effect=fake_run):
                eb._call_claude_code(SYSTEM_PROMPT, USER_MESSAGE, config)

        # The four dangerous vars must not appear in the subprocess env
        assert "CLAUDECODE" not in captured_env
        assert "CLAUDE_CODE_ENTRYPOINT" not in captured_env
        assert "CLAUDE_CODE_DISABLE_FEEDBACK_SURVEY" not in captured_env
        assert "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC" not in captured_env
        # Safe vars are preserved
        assert captured_env.get("SAFE_VAR") == "keep-me"

    def test_strips_session_access_token_before_subprocess(self, monkeypatch):
        """
        CLAUDE_CODE_SESSION_ACCESS_TOKEN must also be stripped.
        When present, it causes claude -p to hang even with the other four vars stripped,
        because the subprocess attempts to authenticate with the session token and blocks.
        """
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ACCESS_TOKEN", "sk-ant-oat01-fake-token")
        monkeypatch.setenv("SAFE_VAR", "keep-me")

        captured_env = {}

        def fake_run(cmd, **kwargs):
            captured_env.update(kwargs.get("env", {}))
            result = MagicMock()
            result.returncode = 0
            result.stdout = '[]'
            result.stderr = ''
            return result

        config = make_config(backend="claude-code")

        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            with patch("subprocess.run", side_effect=fake_run):
                eb._call_claude_code(SYSTEM_PROMPT, USER_MESSAGE, config)

        assert "CLAUDE_CODE_SESSION_ACCESS_TOKEN" not in captured_env
        assert captured_env.get("SAFE_VAR") == "keep-me"

    def test_always_passes_empty_allowed_tools(self):
        """
        --allowedTools "" is always passed to prevent tool execution,
        regardless of what config says.
        """
        captured_cmd = []

        def fake_run(cmd, **kwargs):
            captured_cmd.extend(cmd)
            result = MagicMock()
            result.returncode = 0
            result.stdout = '[]'
            result.stderr = ''
            return result

        config = make_config(backend="claude-code")

        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            with patch("subprocess.run", side_effect=fake_run):
                eb._call_claude_code(SYSTEM_PROMPT, USER_MESSAGE, config)

        assert "--allowedTools" in captured_cmd
        tools_idx = captured_cmd.index("--allowedTools")
        assert captured_cmd[tools_idx + 1] == ""

    def test_respects_claude_timeout_config(self):
        """The subprocess is invoked with the claude_timeout from config."""
        captured_kwargs = {}

        def fake_run(cmd, **kwargs):
            captured_kwargs.update(kwargs)
            result = MagicMock()
            result.returncode = 0
            result.stdout = '[]'
            result.stderr = ''
            return result

        config = make_config(backend="claude-code", claude_timeout=45)

        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            with patch("subprocess.run", side_effect=fake_run):
                eb._call_claude_code(SYSTEM_PROMPT, USER_MESSAGE, config)

        assert captured_kwargs["timeout"] == 45

    def test_raises_backend_error_when_claude_not_found(self):
        """BackendError is raised when the claude binary is not in PATH or fallback paths."""
        # Use a custom claude_path so the hardcoded fallback paths are not tried
        config = make_config(backend="claude-code", claude_path="/nonexistent/bin/claude")

        with patch("shutil.which", return_value=None):
            with pytest.raises(eb.BackendError, match="claude"):
                eb._call_claude_code(SYSTEM_PROMPT, USER_MESSAGE, config)

    def test_raises_backend_error_on_nonzero_exit(self):
        """BackendError is raised when the claude subprocess exits with a nonzero code."""
        def fake_run(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 1
            result.stdout = ''
            result.stderr = 'auth error'
            return result

        config = make_config(backend="claude-code")

        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            with patch("subprocess.run", side_effect=fake_run):
                with pytest.raises(eb.BackendError, match="exited with code 1"):
                    eb._call_claude_code(SYSTEM_PROMPT, USER_MESSAGE, config)

    def test_raises_backend_error_on_timeout(self):
        """BackendError is raised when the subprocess times out."""
        import subprocess as _subprocess

        def fake_run(cmd, **kwargs):
            raise _subprocess.TimeoutExpired(cmd, 30)

        config = make_config(backend="claude-code", claude_timeout=30)

        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            with patch("subprocess.run", side_effect=fake_run):
                with pytest.raises(eb.BackendError, match="timed out"):
                    eb._call_claude_code(SYSTEM_PROMPT, USER_MESSAGE, config)

    def test_uses_model_from_config(self):
        """The model from the config's 'model' key is passed to the subprocess."""
        captured_cmd = []

        def fake_run(cmd, **kwargs):
            captured_cmd.extend(cmd)
            result = MagicMock()
            result.returncode = 0
            result.stdout = '[]'
            result.stderr = ''
            return result

        config = make_config(backend="claude-code", model="claude-opus-4-5")

        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            with patch("subprocess.run", side_effect=fake_run):
                eb._call_claude_code(SYSTEM_PROMPT, USER_MESSAGE, config)

        assert "--model" in captured_cmd
        model_idx = captured_cmd.index("--model")
        assert captured_cmd[model_idx + 1] == "claude-opus-4-5"


# ===========================================================================
# bedrock backend
# ===========================================================================

class TestBedrockBackend:
    """_call_bedrock() uses the Anthropic SDK pointed at AWS Bedrock."""

    def test_sends_correct_model_id_and_region(self):
        """The model ID and region from config are passed to the Bedrock client."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='["response"]')]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        mock_anthropic = MagicMock()
        mock_anthropic.AnthropicBedrock.return_value = mock_client

        config = make_config(
            backend="bedrock",
            model="us.anthropic.claude-haiku-4-5-20251001",
            bedrock_region="eu-west-1",
        )

        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            result = eb._call_bedrock(SYSTEM_PROMPT, USER_MESSAGE, config)

        mock_anthropic.AnthropicBedrock.assert_called_once_with(aws_region="eu-west-1")
        call_kwargs = mock_client.messages.create.call_args
        assert call_kwargs.kwargs["model"] == "us.anthropic.claude-haiku-4-5-20251001"

    def test_raises_backend_error_when_sdk_unavailable(self):
        """BackendError is raised when the anthropic package is not installed."""
        config = make_config(backend="bedrock")

        # _call_bedrock does `import anthropic` inside the function body.
        # We simulate the package being absent by patching the import at the module level.
        # The cleanest way: temporarily remove from sys.modules and set to None so Python
        # raises ImportError on the next `import anthropic` statement.
        original = sys.modules.get("anthropic", "NOT_PRESENT")
        sys.modules.pop("anthropic", None)

        # With anthropic gone from sys.modules, force the import to fail
        try:
            with patch.dict(sys.modules, {"anthropic": None}):
                with pytest.raises(eb.BackendError):
                    eb._call_bedrock(SYSTEM_PROMPT, USER_MESSAGE, config)
        finally:
            if original == "NOT_PRESENT":
                sys.modules.pop("anthropic", None)
            else:
                sys.modules["anthropic"] = original

    def test_raises_backend_error_on_api_failure(self):
        """BackendError is raised when the Bedrock API call raises an exception."""
        mock_anthropic = MagicMock()
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("Bedrock error")
        mock_anthropic.AnthropicBedrock.return_value = mock_client

        config = make_config(backend="bedrock")

        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            with pytest.raises(eb.BackendError, match="Bedrock API call failed"):
                eb._call_bedrock(SYSTEM_PROMPT, USER_MESSAGE, config)


# ===========================================================================
# ollama backend
# ===========================================================================

class TestOllamaBackend:
    """_call_ollama() calls a local Ollama instance via urllib."""

    def _make_ollama_response(self, content: str) -> MagicMock:
        """Build a mock urllib response that returns the given JSON string."""
        import io
        response_data = json.dumps({
            "message": {"content": content}
        }).encode("utf-8")
        mock_resp = MagicMock()
        mock_resp.read.return_value = response_data
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    def test_constructs_correct_http_request(self):
        """The Ollama backend sends a POST to /api/chat with the correct body."""
        import urllib.request

        captured_request = {}

        def fake_urlopen(req, timeout=None):
            captured_request["url"] = req.full_url
            captured_request["method"] = req.method
            captured_request["body"] = json.loads(req.data.decode("utf-8"))
            return self._make_ollama_response('["beat"]')

        config = make_config(
            backend="ollama",
            ollama_url="http://localhost:11434",
            model="llama3.2",
        )

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            eb._call_ollama(SYSTEM_PROMPT, USER_MESSAGE, config)

        assert captured_request["url"] == "http://localhost:11434/api/chat"
        assert captured_request["method"] == "POST"
        body = captured_request["body"]
        assert body["model"] == "llama3.2"
        assert body["stream"] is False
        assert body["format"] == "json"
        assert body["options"]["temperature"] == 0.1
        assert body["options"]["num_predict"] == 4096

    def test_returns_parsed_response_content(self):
        """The text from message.content is returned."""
        config = make_config(backend="ollama", model="llama3.2")

        with patch("urllib.request.urlopen", return_value=self._make_ollama_response('["a beat"]')):
            result = eb._call_ollama(SYSTEM_PROMPT, USER_MESSAGE, config)

        assert result == '["a beat"]'

    def test_strips_markdown_fences_and_retries(self):
        """If Ollama wraps the JSON in markdown fences, they are stripped before returning."""
        fenced_content = '```json\n["a beat"]\n```'
        config = make_config(backend="ollama", model="llama3.2")

        with patch("urllib.request.urlopen", return_value=self._make_ollama_response(fenced_content)):
            result = eb._call_ollama(SYSTEM_PROMPT, USER_MESSAGE, config)

        # The returned value should be valid JSON (fences stripped)
        parsed = json.loads(result)
        assert parsed == ["a beat"]

    def test_raises_backend_error_on_unparseable_response(self):
        """BackendError is raised if the response is not valid JSON even after fence stripping."""
        invalid_content = "this is not json at all, not even with fences stripped"
        config = make_config(backend="ollama", model="llama3.2")

        with patch("urllib.request.urlopen", return_value=self._make_ollama_response(invalid_content)):
            with pytest.raises(eb.BackendError, match="not valid JSON"):
                eb._call_ollama(SYSTEM_PROMPT, USER_MESSAGE, config)

    def test_raises_backend_error_on_http_error(self):
        """BackendError is raised on HTTP errors from the Ollama server."""
        import urllib.error

        config = make_config(backend="ollama")

        with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError(
            url=None, code=500, msg="Internal Server Error", hdrs=None, fp=None
        )):
            with pytest.raises(eb.BackendError, match="HTTP error"):
                eb._call_ollama(SYSTEM_PROMPT, USER_MESSAGE, config)

    def test_raises_backend_error_on_connection_error(self):
        """BackendError is raised when Ollama is not reachable."""
        import urllib.error

        config = make_config(backend="ollama")

        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
            with pytest.raises(eb.BackendError, match="connection error"):
                eb._call_ollama(SYSTEM_PROMPT, USER_MESSAGE, config)

    def test_uses_custom_ollama_url(self):
        """A custom ollama_url from config is used in the request."""
        captured_url = []

        def fake_urlopen(req, timeout=None):
            captured_url.append(req.full_url)
            return self._make_ollama_response('["beat"]')

        config = make_config(
            backend="ollama",
            ollama_url="http://192.168.1.10:11434",
            model="llama3.2",
        )

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            eb._call_ollama(SYSTEM_PROMPT, USER_MESSAGE, config)

        assert captured_url[0].startswith("http://192.168.1.10:11434")


# ===========================================================================
# call_model dispatch
# ===========================================================================

class TestCallModelDispatch:
    """call_model() routes to the correct backend based on config."""

    def test_routes_claude_code_backend(self):
        """call_model routes to _call_claude_code when backend=claude-code."""
        config = make_config(backend="claude-code")
        with patch.object(_backends_module, "_call_claude_code", return_value="response") as mock:
            result = eb.call_model(SYSTEM_PROMPT, USER_MESSAGE, config)
        mock.assert_called_once()
        assert result == "response"

    def test_routes_bedrock_backend(self):
        """call_model routes to _call_bedrock when backend=bedrock."""
        config = make_config(backend="bedrock")
        with patch.object(_backends_module, "_call_bedrock", return_value="response") as mock:
            result = eb.call_model(SYSTEM_PROMPT, USER_MESSAGE, config)
        mock.assert_called_once()
        assert result == "response"

    def test_routes_ollama_backend(self):
        """call_model routes to _call_ollama when backend=ollama."""
        config = make_config(backend="ollama")
        with patch.object(_backends_module, "_call_ollama", return_value="response") as mock:
            result = eb.call_model(SYSTEM_PROMPT, USER_MESSAGE, config)
        mock.assert_called_once()
        assert result == "response"

    def test_raises_backend_error_for_unknown_backend(self):
        """call_model raises BackendError for an unrecognized backend name."""
        config = make_config(backend="unknown-backend")
        with pytest.raises(eb.BackendError, match="Unknown backend"):
            eb.call_model(SYSTEM_PROMPT, USER_MESSAGE, config)

    def test_default_backend_is_claude_code(self):
        """When no backend is specified, claude-code is used by default."""
        config = {k: v for k, v in BASE_CONFIG.items() if k != "backend"}
        with patch.object(_backends_module, "_call_claude_code", return_value="response") as mock:
            eb.call_model(SYSTEM_PROMPT, USER_MESSAGE, config)
        mock.assert_called_once()


# ===========================================================================
# claude-code fallback path resolution (lines 48–57)
# ===========================================================================

class TestClaudeCodeFallbackPaths:
    """When shutil.which returns None for 'claude', well-known paths are tried in order."""

    def test_uses_fallback_path_when_which_returns_none(self, tmp_path):
        """
        If 'claude' is not on PATH but exists at a well-known location,
        that location is used rather than raising BackendError.
        The fallback list represents common install locations that Claude Desktop
        may not have in its isolated PATH.
        """
        fake_claude = tmp_path / "claude"
        fake_claude.write_text("#!/bin/sh\necho '[]'")
        fake_claude.chmod(0o755)

        captured_cmd = []

        def fake_run(cmd, **kwargs):
            captured_cmd.extend(cmd)
            result = MagicMock()
            result.returncode = 0
            result.stdout = "ok"
            result.stderr = ""
            return result

        config = make_config(backend="claude-code")

        with patch("shutil.which", return_value=None):
            with patch("os.path.isfile", return_value=True):
                with patch("os.access", return_value=True):
                    with patch("subprocess.run", side_effect=fake_run):
                        result = eb._call_claude_code(SYSTEM_PROMPT, USER_MESSAGE, config)

        assert result == "ok"
        assert captured_cmd[0] in (
            "/opt/homebrew/bin/claude",
            "/usr/local/bin/claude",
            os.path.expanduser("~/.local/bin/claude"),
            "/usr/bin/claude",
        )

    def test_fallback_only_tried_when_claude_path_is_default(self):
        """
        The fallback path scan only runs when claude_path is the default 'claude'.
        A custom claude_path that isn't found raises immediately without scanning fallbacks.
        """
        config = make_config(backend="claude-code", claude_path="/custom/path/to/claude")

        with patch("shutil.which", return_value=None):
            with patch("os.path.isfile", return_value=True):
                with patch("os.access", return_value=True):
                    with pytest.raises(eb.BackendError, match="claude"):
                        eb._call_claude_code(SYSTEM_PROMPT, USER_MESSAGE, config)

    def test_raises_backend_error_when_all_fallbacks_absent(self):
        """
        When 'claude' is not on PATH and none of the fallback paths exist,
        BackendError is raised with a helpful message explaining the fix.
        """
        config = make_config(backend="claude-code")

        with patch("shutil.which", return_value=None):
            with patch("os.path.isfile", return_value=False):
                with pytest.raises(eb.BackendError) as exc_info:
                    eb._call_claude_code(SYSTEM_PROMPT, USER_MESSAGE, config)

        assert "claude_path" in str(exc_info.value) or "'claude'" in str(exc_info.value)

    def test_raises_backend_error_on_subprocess_exception(self):
        """
        If subprocess.run raises a generic exception (e.g. PermissionError),
        it is wrapped in BackendError rather than propagating raw.
        """
        def boom(cmd, **kwargs):
            raise PermissionError("Operation not permitted")

        config = make_config(backend="claude-code")

        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            with patch("subprocess.run", side_effect=boom):
                with pytest.raises(eb.BackendError, match="failed to start"):
                    eb._call_claude_code(SYSTEM_PROMPT, USER_MESSAGE, config)

    def test_raises_backend_error_on_empty_stdout(self):
        """
        If claude exits with code 0 but produces no output (auth issue, rate limit),
        BackendError is raised with a diagnostic message.
        """
        def fake_run(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stdout = "   \n"
            result.stderr = "Error: unauthorized"
            return result

        config = make_config(backend="claude-code")

        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            with patch("subprocess.run", side_effect=fake_run):
                with pytest.raises(eb.BackendError) as exc_info:
                    eb._call_claude_code(SYSTEM_PROMPT, USER_MESSAGE, config)

        msg = str(exc_info.value)
        assert "no output" in msg.lower() or "empty" in msg.lower() or "code 0" in msg.lower()

    def test_raises_backend_error_when_stdout_starts_with_error_prefix(self):
        """
        CLI-level error messages (e.g. 'Error: Reached max turns (3)') written
        to stdout are detected and raised as BackendError, not silently returned
        as if they were valid JSON output.
        """
        def fake_run(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stdout = "Error: Reached max turns (3)"
            result.stderr = ""
            return result

        config = make_config(backend="claude-code")

        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            with patch("subprocess.run", side_effect=fake_run):
                with pytest.raises(eb.BackendError, match="CLI error"):
                    eb._call_claude_code(SYSTEM_PROMPT, USER_MESSAGE, config)


# ===========================================================================
# bedrock — additional error paths (lines 157, 161, 168)
# ===========================================================================

class TestBedrockBackendErrorPaths:
    """Additional Bedrock error scenarios not covered by the main suite."""

    def _make_bedrock_mock(self, response_obj):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = response_obj
        mock_anthropic = MagicMock()
        mock_anthropic.AnthropicBedrock.return_value = mock_client
        return mock_anthropic

    def test_raises_backend_error_on_empty_content_array(self):
        """
        If the Bedrock response has content=[], no text block exists.
        BackendError is raised rather than an IndexError.
        """
        mock_response = MagicMock()
        mock_response.content = []
        mock_anthropic = self._make_bedrock_mock(mock_response)

        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            with pytest.raises(eb.BackendError, match="empty content"):
                eb._call_bedrock(SYSTEM_PROMPT, USER_MESSAGE, make_config(backend="bedrock"))

    def test_raises_backend_error_on_non_text_content_block(self):
        """
        If the Bedrock response returns an unexpected block type (no 'text' attribute),
        BackendError is raised with the block type name for diagnosis.
        """
        mock_block = MagicMock(spec=[])  # no 'text' attribute
        mock_response = MagicMock()
        mock_response.content = [mock_block]
        mock_anthropic = self._make_bedrock_mock(mock_response)

        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            with pytest.raises(eb.BackendError, match="unexpected content block"):
                eb._call_bedrock(SYSTEM_PROMPT, USER_MESSAGE, make_config(backend="bedrock"))

    def test_raises_backend_error_on_empty_text_response(self):
        """
        If the Bedrock response has a text block but the text is blank,
        BackendError is raised rather than returning an empty string to the caller.
        """
        mock_block = MagicMock()
        mock_block.text = "   "
        mock_response = MagicMock()
        mock_response.content = [mock_block]
        mock_anthropic = self._make_bedrock_mock(mock_response)

        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            with pytest.raises(eb.BackendError, match="empty response"):
                eb._call_bedrock(SYSTEM_PROMPT, USER_MESSAGE, make_config(backend="bedrock"))


# ===========================================================================
# ollama — additional error paths (lines 212–225)
# ===========================================================================

class TestOllamaBackendErrorPaths:
    """Additional Ollama error scenarios not covered by the main suite."""

    def _make_ollama_response(self, content: str) -> MagicMock:
        response_data = json.dumps({"message": {"content": content}}).encode("utf-8")
        mock_resp = MagicMock()
        mock_resp.read.return_value = response_data
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    def _make_ollama_raw_response(self, body: bytes) -> MagicMock:
        mock_resp = MagicMock()
        mock_resp.read.return_value = body
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    def test_raises_backend_error_on_timeout(self):
        """
        A TimeoutError (stdlib, not urllib) from urlopen is caught and raised
        as BackendError, not propagated raw.  This path is distinct from the
        urllib.error.URLError tested in the main suite.
        """
        config = make_config(backend="ollama")

        with patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
            with pytest.raises(eb.BackendError, match="timed out"):
                eb._call_ollama(SYSTEM_PROMPT, USER_MESSAGE, config)

    def test_raises_backend_error_on_invalid_json_response_body(self):
        """
        If Ollama returns a response body that is not valid JSON at all,
        BackendError is raised rather than propagating json.JSONDecodeError.
        """
        config = make_config(backend="ollama")
        raw_resp = self._make_ollama_raw_response(b"not json at all {{{")

        with patch("urllib.request.urlopen", return_value=raw_resp):
            with pytest.raises(eb.BackendError, match="invalid JSON"):
                eb._call_ollama(SYSTEM_PROMPT, USER_MESSAGE, config)

    def test_raises_backend_error_when_message_content_field_missing(self):
        """
        If the Ollama response JSON is valid but lacks the message.content field,
        BackendError is raised rather than raising KeyError.
        """
        config = make_config(backend="ollama")
        bad_body = json.dumps({"model": "llama3.2", "done": True}).encode("utf-8")
        raw_resp = self._make_ollama_raw_response(bad_body)

        with patch("urllib.request.urlopen", return_value=raw_resp):
            with pytest.raises(eb.BackendError, match="message.content"):
                eb._call_ollama(SYSTEM_PROMPT, USER_MESSAGE, config)

    def test_raises_backend_error_on_generic_urlopen_exception(self):
        """
        An unexpected exception from urlopen (not HTTPError or URLError) is
        caught and raised as BackendError.
        """
        config = make_config(backend="ollama")

        with patch("urllib.request.urlopen", side_effect=OSError("socket error")):
            with pytest.raises(eb.BackendError, match="request failed"):
                eb._call_ollama(SYSTEM_PROMPT, USER_MESSAGE, config)


# ===========================================================================
# claude-code subprocess hardening (start_new_session + neutral cwd)
# ===========================================================================

class TestClaudeCodeSubprocessHardening:
    """
    Verify that the subprocess is launched with the correct isolation settings.

    start_new_session=True detaches the subprocess from the parent process group
    so SIGHUP cannot leak. A neutral cwd prevents CLAUDE.md / project config
    injection into the extraction subprocess.
    """

    def _fake_run_capture(self, captured: dict):
        def fake_run(cmd, **kwargs):
            captured.update(kwargs)
            result = MagicMock()
            result.returncode = 0
            result.stdout = "ok"
            result.stderr = ""
            return result
        return fake_run

    def test_start_new_session_is_always_true(self):
        """
        start_new_session=True must be passed unconditionally to subprocess.run
        so the extraction subprocess is fully detached from the parent.
        """
        captured: dict = {}
        config = make_config(backend="claude-code")

        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            with patch("subprocess.run", side_effect=self._fake_run_capture(captured)):
                eb._call_claude_code(SYSTEM_PROMPT, USER_MESSAGE, config)

        assert captured.get("start_new_session") is True, (
            "start_new_session must be True to detach the subprocess from the parent "
            "process group (prevents SIGHUP leakage)"
        )

    def test_default_cwd_is_neutral_cyberbrain_dir(self, tmp_path, monkeypatch):
        """
        When subprocess_cwd is not in config, the cwd defaults to
        ~/.claude/cyberbrain/ to prevent project CLAUDE.md injection.
        """
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setenv("HOME", str(fake_home))
        # Ensure the neutral dir exists so it doesn't fall back
        neutral_dir = fake_home / ".claude" / "cyberbrain"
        neutral_dir.mkdir(parents=True)

        captured: dict = {}
        config = make_config(backend="claude-code")  # no subprocess_cwd key

        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            with patch("subprocess.run", side_effect=self._fake_run_capture(captured)):
                eb._call_claude_code(SYSTEM_PROMPT, USER_MESSAGE, config)

        expected = str(fake_home / ".claude" / "cyberbrain")
        assert captured.get("cwd") == expected, (
            f"Expected neutral cwd={expected!r}, got {captured.get('cwd')!r}. "
            "A neutral cwd prevents the subprocess from loading project CLAUDE.md files."
        )

    def test_config_subprocess_cwd_overrides_default(self):
        """
        If subprocess_cwd is set in config, it is used instead of the default.
        This lets users point to a custom neutral directory.
        """
        captured: dict = {}
        config = make_config(backend="claude-code", subprocess_cwd="/custom/neutral/dir")

        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            with patch("subprocess.run", side_effect=self._fake_run_capture(captured)):
                eb._call_claude_code(SYSTEM_PROMPT, USER_MESSAGE, config)

        assert captured.get("cwd") == "/custom/neutral/dir"

    def test_all_strip_vars_removed_unconditionally(self, monkeypatch):
        """
        All five env vars that cause hangs must be stripped, even if only some
        are present. This is a single code path — no conditional logic.
        """
        # Set only a subset of the dangerous vars to prove unconditional stripping
        monkeypatch.setenv("CLAUDECODE", "1")
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ACCESS_TOKEN", "secret-token")
        # Leave CLAUDE_CODE_ENTRYPOINT unset — but it should also not appear

        captured_env: dict = {}

        def fake_run(cmd, **kwargs):
            captured_env.update(kwargs.get("env", {}))
            result = MagicMock()
            result.returncode = 0
            result.stdout = "ok"
            result.stderr = ""
            return result

        config = make_config(backend="claude-code")
        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            with patch("subprocess.run", side_effect=fake_run):
                eb._call_claude_code(SYSTEM_PROMPT, USER_MESSAGE, config)

        for var in _backends_module._STRIP_VARS:
            assert var not in captured_env, (
                f"{var} must always be stripped — it was present in the subprocess env"
            )
