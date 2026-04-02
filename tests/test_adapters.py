import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from skillprobe.adapters import get_adapter
from skillprobe.adapters.base import HarnessConfig
from skillprobe.adapters.claude_code import ClaudeCodeAdapter
from skillprobe.adapters.cursor import CursorAdapter


CLAUDE_STREAM_SUCCESS = "\n".join(
    [
        json.dumps({"type": "system", "subtype": "init", "session_id": "abc-123-def"}),
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "text",
                            "text": "I committed your changes with message: feat: add login",
                        },
                    ]
                },
            }
        ),
        json.dumps(
            {
                "type": "result",
                "subtype": "success",
                "session_id": "abc-123-def",
                "duration_ms": 3200,
            }
        ),
    ]
)

CLAUDE_STREAM_WITH_SKILL = "\n".join(
    [
        json.dumps(
            {"type": "system", "subtype": "init", "session_id": "skill-test-001"}
        ),
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Skill",
                            "input": {"skill": "commit"},
                            "id": "toolu_1",
                        },
                    ]
                },
            }
        ),
        json.dumps(
            {
                "type": "user",
                "tool_use_result": {"success": True, "commandName": "commit"},
            }
        ),
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "text",
                            "text": "I'll commit using conventional format.",
                        },
                    ]
                },
            }
        ),
        json.dumps(
            {
                "type": "result",
                "subtype": "success",
                "session_id": "skill-test-001",
                "duration_ms": 5000,
            }
        ),
    ]
)

CLAUDE_STREAM_ERROR = "\n".join(
    [
        json.dumps({"type": "system", "subtype": "init", "session_id": "err-456"}),
        json.dumps(
            {
                "type": "result",
                "subtype": "error",
                "session_id": "err-456",
                "duration_ms": 500,
            }
        ),
    ]
)

CURSOR_STREAM_EVENTS = "\n".join(
    [
        json.dumps(
            {
                "type": "system",
                "subtype": "init",
                "session_id": "cur-789",
                "model": "sonnet-4",
            }
        ),
        json.dumps({"type": "assistant", "message": "I'll commit your changes now."}),
        json.dumps(
            {
                "type": "tool_call",
                "subtype": "started",
                "tool": "shell",
                "arguments": {"command": "git commit"},
            }
        ),
        json.dumps({"type": "tool_call", "subtype": "completed", "tool": "shell"}),
        json.dumps({"type": "assistant", "message": " Done!"}),
        json.dumps(
            {
                "type": "result",
                "subtype": "success",
                "result": "I'll commit your changes now. Done!",
                "duration_ms": 2500,
                "session_id": "cur-789",
            }
        ),
    ]
)


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
        assert "tool_called" in supported
        assert "skill_activated" in supported
        assert "file_exists" in supported

    @pytest.mark.asyncio
    async def test_parses_stream_text(self, tmp_path):
        adapter = ClaudeCodeAdapter()
        adapter._config = HarnessConfig(harness="claude-code", model="sonnet")

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=make_completed_process(CLAUDE_STREAM_SUCCESS),
        ):
            evidence = await adapter.send_prompt("commit my changes", tmp_path, None)

        assert (
            evidence.response_text
            == "I committed your changes with message: feat: add login"
        )
        assert evidence.session_id == "abc-123-def"
        assert evidence.duration_ms == 3200
        assert evidence.exit_code == 0

    @pytest.mark.asyncio
    async def test_parses_skill_tool_calls(self, tmp_path):
        adapter = ClaudeCodeAdapter()
        adapter._config = HarnessConfig(harness="claude-code", model="sonnet")

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=make_completed_process(CLAUDE_STREAM_WITH_SKILL),
        ):
            evidence = await adapter.send_prompt("commit my changes", tmp_path, None)

        assert len(evidence.tool_calls) == 1
        assert evidence.tool_calls[0].tool_name == "Skill"
        assert evidence.tool_calls[0].arguments["skill"] == "commit"
        assert evidence.tool_calls[0].status == "completed"
        assert "conventional format" in evidence.response_text

    @pytest.mark.asyncio
    async def test_handles_error(self, tmp_path):
        adapter = ClaudeCodeAdapter()
        adapter._config = HarnessConfig(harness="claude-code")

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=make_completed_process(CLAUDE_STREAM_ERROR, returncode=1),
        ):
            evidence = await adapter.send_prompt("bad request", tmp_path, None)

        assert evidence.is_error is True
        assert evidence.session_id == "err-456"

    @pytest.mark.asyncio
    async def test_resume_flag(self, tmp_path):
        adapter = ClaudeCodeAdapter()
        adapter._config = HarnessConfig(harness="claude-code", model="sonnet")

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=make_completed_process(CLAUDE_STREAM_SUCCESS),
        ) as mock_exec:
            await adapter.send_prompt("follow up", tmp_path, "abc-123-def")
            args = mock_exec.call_args[0]
            assert "--resume" in args
            assert "abc-123-def" in args

    @pytest.mark.asyncio
    async def test_uses_stream_json_verbose(self, tmp_path):
        adapter = ClaudeCodeAdapter()
        adapter._config = HarnessConfig(harness="claude-code", model="sonnet")

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=make_completed_process(CLAUDE_STREAM_SUCCESS),
        ) as mock_exec:
            await adapter.send_prompt("test", tmp_path, None)
            args = mock_exec.call_args[0]
            assert "--output-format" in args
            idx = list(args).index("--output-format")
            assert args[idx + 1] == "stream-json"
            assert "--verbose" in args


class TestCursorAdapter:
    def test_supported_assertions(self):
        adapter = CursorAdapter()
        supported = adapter.supported_assertions()
        assert "contains" in supported
        assert "tool_called" in supported
        assert "file_exists" in supported
        assert "skill_activated" not in supported

    @pytest.mark.asyncio
    async def test_parses_stream(self, tmp_path):
        adapter = CursorAdapter()
        adapter._config = HarnessConfig(harness="cursor", model="sonnet-4")

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=make_completed_process(CURSOR_STREAM_EVENTS),
        ):
            evidence = await adapter.send_prompt("commit my changes", tmp_path, None)

        assert "commit your changes" in evidence.response_text
        assert "Done!" in evidence.response_text
        assert evidence.session_id == "cur-789"
        assert evidence.duration_ms == 2500
        assert len(evidence.tool_calls) == 1
        assert evidence.tool_calls[0].tool_name == "shell"

    @pytest.mark.asyncio
    async def test_workspace_flag(self, tmp_path):
        adapter = CursorAdapter()
        adapter._config = HarnessConfig(harness="cursor", model="sonnet-4")

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=make_completed_process(CURSOR_STREAM_EVENTS),
        ) as mock_exec:
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
