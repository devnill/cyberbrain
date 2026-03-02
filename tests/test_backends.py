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
        """BackendError is raised when the claude binary is not in PATH."""
        config = make_config(backend="claude-code")

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
        with patch.object(eb, "_call_claude_code", return_value="response") as mock:
            result = eb.call_model(SYSTEM_PROMPT, USER_MESSAGE, config)
        mock.assert_called_once()
        assert result == "response"

    def test_routes_bedrock_backend(self):
        """call_model routes to _call_bedrock when backend=bedrock."""
        config = make_config(backend="bedrock")
        with patch.object(eb, "_call_bedrock", return_value="response") as mock:
            result = eb.call_model(SYSTEM_PROMPT, USER_MESSAGE, config)
        mock.assert_called_once()
        assert result == "response"

    def test_routes_ollama_backend(self):
        """call_model routes to _call_ollama when backend=ollama."""
        config = make_config(backend="ollama")
        with patch.object(eb, "_call_ollama", return_value="response") as mock:
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
        with patch.object(eb, "_call_claude_code", return_value="response") as mock:
            eb.call_model(SYSTEM_PROMPT, USER_MESSAGE, config)
        mock.assert_called_once()
