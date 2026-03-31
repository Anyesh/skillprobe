import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from skillprobe.harness.adapters import get_adapter
from skillprobe.harness.adapters.base import HarnessConfig
from skillprobe.harness.adapters.claude_code import ClaudeCodeAdapter
from skillprobe.harness.adapters.cursor import CursorAdapter


CLAUDE_JSON_SUCCESS = json.dumps({
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "result": "I committed your changes with message: feat: add login",
    "session_id": "abc-123-def",
    "total_cost_usd": 0.015,
    "duration_ms": 3200,
    "num_turns": 2,
})

CLAUDE_JSON_ERROR = json.dumps({
    "type": "result",
    "subtype": "success",
    "is_error": True,
    "result": "API error occurred",
    "session_id": "err-456",
    "total_cost_usd": 0.001,
    "duration_ms": 500,
})

CURSOR_STREAM_EVENTS = "\n".join([
    json.dumps({"type": "system", "subtype": "init", "session_id": "cur-789", "model": "sonnet-4"}),
    json.dumps({"type": "assistant", "message": "I'll commit your changes now."}),
    json.dumps({"type": "tool_call", "subtype": "started", "tool": "shell", "arguments": {"command": "git commit"}}),
    json.dumps({"type": "tool_call", "subtype": "completed", "tool": "shell"}),
    json.dumps({"type": "assistant", "message": " Done!"}),
    json.dumps({"type": "result", "subtype": "success", "result": "I'll commit your changes now. Done!", "duration_ms": 2500, "session_id": "cur-789"}),
])


def make_completed_process(stdout: str, returncode: int = 0):
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(stdout.encode(), b""))
    proc.returncode = returncode
    proc.pid = 12345
    return proc


class TestClaudeCodeAdapter:
    def test_supported_assertions(self):
        adapter = ClaudeCodeAdapter()
        supported = adapter.supported_assertions()
        assert "contains" in supported
        assert "skill_loaded" in supported
        assert "skill_present" in supported
        assert "tool_called" in supported
        assert "file_exists" in supported

    @pytest.mark.asyncio
    async def test_send_prompt_parses_json(self, tmp_path):
        adapter = ClaudeCodeAdapter()
        adapter._config = HarnessConfig(harness="claude-code", model="sonnet")

        with patch("asyncio.create_subprocess_exec", return_value=make_completed_process(CLAUDE_JSON_SUCCESS)):
            evidence = await adapter.send_prompt("commit my changes", tmp_path, None)

        assert evidence.response_text == "I committed your changes with message: feat: add login"
        assert evidence.session_id == "abc-123-def"
        assert evidence.cost_usd == 0.015
        assert evidence.duration_ms == 3200
        assert evidence.is_error is False
        assert evidence.exit_code == 0

    @pytest.mark.asyncio
    async def test_send_prompt_handles_error(self, tmp_path):
        adapter = ClaudeCodeAdapter()
        adapter._config = HarnessConfig(harness="claude-code")

        with patch("asyncio.create_subprocess_exec", return_value=make_completed_process(CLAUDE_JSON_ERROR)):
            evidence = await adapter.send_prompt("bad request", tmp_path, None)

        assert evidence.is_error is True
        assert evidence.response_text == "API error occurred"

    @pytest.mark.asyncio
    async def test_send_prompt_with_resume(self, tmp_path):
        adapter = ClaudeCodeAdapter()
        adapter._config = HarnessConfig(harness="claude-code", model="sonnet")

        with patch("asyncio.create_subprocess_exec", return_value=make_completed_process(CLAUDE_JSON_SUCCESS)) as mock_exec:
            await adapter.send_prompt("follow up", tmp_path, "abc-123-def")
            args = mock_exec.call_args[0]
            assert "--resume" in args
            assert "abc-123-def" in args


class TestCursorAdapter:
    def test_supported_assertions(self):
        adapter = CursorAdapter()
        supported = adapter.supported_assertions()
        assert "contains" in supported
        assert "tool_called" in supported
        assert "file_exists" in supported
        assert "skill_loaded" not in supported
        assert "skill_present" not in supported

    @pytest.mark.asyncio
    async def test_send_prompt_parses_stream(self, tmp_path):
        adapter = CursorAdapter()
        adapter._config = HarnessConfig(harness="cursor", model="sonnet-4")

        with patch("asyncio.create_subprocess_exec", return_value=make_completed_process(CURSOR_STREAM_EVENTS)):
            evidence = await adapter.send_prompt("commit my changes", tmp_path, None)

        assert "commit your changes" in evidence.response_text
        assert "Done!" in evidence.response_text
        assert evidence.session_id == "cur-789"
        assert evidence.duration_ms == 2500
        assert len(evidence.tool_calls) == 1
        assert evidence.tool_calls[0].tool_name == "shell"

    @pytest.mark.asyncio
    async def test_send_prompt_with_workspace(self, tmp_path):
        adapter = CursorAdapter()
        adapter._config = HarnessConfig(harness="cursor", model="sonnet-4")

        with patch("asyncio.create_subprocess_exec", return_value=make_completed_process(CURSOR_STREAM_EVENTS)) as mock_exec:
            await adapter.send_prompt("test", tmp_path, None)
            args = mock_exec.call_args[0]
            assert "--workspace" in args
            idx = list(args).index("--workspace")
            assert args[idx + 1] == str(tmp_path)


class TestGetAdapter:
    def test_returns_claude_code(self):
        adapter = get_adapter("claude-code")
        assert isinstance(adapter, ClaudeCodeAdapter)

    def test_returns_cursor(self):
        adapter = get_adapter("cursor")
        assert isinstance(adapter, CursorAdapter)

    def test_unknown_raises(self):
        with pytest.raises(ValueError):
            get_adapter("unknown")
