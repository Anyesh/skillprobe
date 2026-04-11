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
                "model": "Auto",
                "cwd": "/tmp/test",
            }
        ),
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "I'll read the file first."}],
                },
            }
        ),
        json.dumps(
            {
                "type": "tool_call",
                "subtype": "started",
                "call_id": "call_1",
                "tool_call": {"readToolCall": {"args": {"path": "/tmp/test/main.py"}}},
            }
        ),
        json.dumps(
            {
                "type": "tool_call",
                "subtype": "completed",
                "call_id": "call_1",
                "tool_call": {
                    "readToolCall": {
                        "args": {"path": "/tmp/test/main.py"},
                        "result": {"success": {"content": "x = 1"}},
                    }
                },
            }
        ),
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": " Done!"}],
                },
            }
        ),
        json.dumps(
            {
                "type": "result",
                "subtype": "success",
                "duration_ms": 2500,
                "session_id": "cur-789",
                "is_error": False,
            }
        ),
    ]
)

CURSOR_STREAM_WITH_SKILL = "\n".join(
    [
        json.dumps(
            {"type": "system", "subtype": "init", "session_id": "cur-skill-001"}
        ),
        json.dumps(
            {
                "type": "tool_call",
                "subtype": "started",
                "call_id": "call_sk1",
                "tool_call": {
                    "readToolCall": {
                        "args": {"path": "/tmp/ws/.cursor/skills/test-skill/SKILL.md"}
                    }
                },
            }
        ),
        json.dumps(
            {
                "type": "tool_call",
                "subtype": "completed",
                "call_id": "call_sk1",
                "tool_call": {
                    "readToolCall": {
                        "args": {"path": "/tmp/ws/.cursor/skills/test-skill/SKILL.md"},
                        "result": {"success": {"content": "skill content"}},
                    }
                },
            }
        ),
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "Following the skill instructions."}
                    ],
                },
            }
        ),
        json.dumps(
            {
                "type": "result",
                "subtype": "success",
                "duration_ms": 3000,
                "session_id": "cur-skill-001",
            }
        ),
    ]
)


def make_completed_process(stdout: str, returncode: int = 0, stderr: str = ""):
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(stdout.encode(), stderr.encode()))
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
        assert "skill_activated" in supported
        assert "file_exists" in supported

    @pytest.mark.asyncio
    async def test_parses_stream_text(self, tmp_path):
        adapter = CursorAdapter()
        adapter._config = HarnessConfig(harness="cursor", model="auto")

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=make_completed_process(CURSOR_STREAM_EVENTS),
        ):
            evidence = await adapter.send_prompt("read the file", tmp_path, None)

        assert "read the file first" in evidence.response_text
        assert "Done!" in evidence.response_text
        assert evidence.session_id == "cur-789"
        assert evidence.duration_ms == 2500

    @pytest.mark.asyncio
    async def test_parses_tool_calls(self, tmp_path):
        adapter = CursorAdapter()
        adapter._config = HarnessConfig(harness="cursor", model="auto")

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=make_completed_process(CURSOR_STREAM_EVENTS),
        ):
            evidence = await adapter.send_prompt("read the file", tmp_path, None)

        assert len(evidence.tool_calls) == 1
        assert evidence.tool_calls[0].tool_name == "Read"
        assert evidence.tool_calls[0].status == "completed"

    @pytest.mark.asyncio
    async def test_detects_skill_loading(self, tmp_path):
        adapter = CursorAdapter()
        adapter._config = HarnessConfig(harness="cursor", model="auto")

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=make_completed_process(CURSOR_STREAM_WITH_SKILL),
        ):
            evidence = await adapter.send_prompt("test", tmp_path, None)

        skill_calls = [tc for tc in evidence.tool_calls if tc.tool_name == "Skill"]
        assert len(skill_calls) == 1
        assert skill_calls[0].arguments["skill"] == "test-skill"
        assert skill_calls[0].status == "completed"

    @pytest.mark.asyncio
    async def test_workspace_flag(self, tmp_path):
        adapter = CursorAdapter()
        adapter._config = HarnessConfig(harness="cursor", model="auto")

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=make_completed_process(CURSOR_STREAM_EVENTS),
        ) as mock_exec:
            await adapter.send_prompt("test", tmp_path, None)
            args = mock_exec.call_args[0]
            assert "--workspace" in args
            idx = list(args).index("--workspace")
            assert args[idx + 1] == str(tmp_path)

    @pytest.mark.asyncio
    async def test_invalid_model_via_stderr_raises(self, tmp_path):
        adapter = CursorAdapter()
        adapter._config = HarnessConfig(harness="cursor", model="bogus")
        with patch(
            "asyncio.create_subprocess_exec",
            return_value=make_completed_process(
                stdout="",
                returncode=1,
                stderr="Cannot use this model: bogus. Available models: auto, composer-2",
            ),
        ):
            with pytest.raises(RuntimeError, match="exited with code 1"):
                await adapter.send_prompt("test", tmp_path, None)

    @pytest.mark.asyncio
    async def test_usage_limit_stderr_raises_when_no_assistant_content(self, tmp_path):
        adapter = CursorAdapter()
        adapter._config = HarnessConfig(harness="cursor", model="auto")
        stdout = "\n".join(
            [
                json.dumps(
                    {
                        "type": "system",
                        "subtype": "init",
                        "session_id": "s",
                    }
                ),
                json.dumps(
                    {
                        "type": "user",
                        "message": {
                            "role": "user",
                            "content": [{"type": "text", "text": "hi"}],
                        },
                    }
                ),
            ]
        )
        stderr = "b: You've hit your usage limit Get Cursor Pro for more."
        with patch(
            "asyncio.create_subprocess_exec",
            return_value=make_completed_process(
                stdout=stdout, returncode=0, stderr=stderr
            ),
        ):
            with pytest.raises(RuntimeError, match="no assistant content"):
                await adapter.send_prompt("test", tmp_path, None)


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
