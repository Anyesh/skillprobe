import asyncio
import json
from pathlib import Path

from skillprobe.adapters.base import HarnessConfig
from skillprobe.evidence import StepEvidence, ToolCallEvent


class ClaudeCodeAdapter:
    def __init__(self):
        self._config: HarnessConfig | None = None

    def start(self, config: HarnessConfig) -> None:
        self._config = config

    async def send_prompt(
        self, prompt: str, workspace: Path, session_id: str | None
    ) -> StepEvidence:
        args = self._build_args(prompt, workspace, session_id)
        timeout = self._config.timeout if self._config else 120

        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=workspace,
        )
        try:
            stdout_bytes, _ = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except (asyncio.TimeoutError, asyncio.CancelledError):
            proc.kill()
            await proc.wait()
            return StepEvidence(
                response_text="",
                tool_calls=[],
                session_id=None,
                duration_ms=timeout * 1000,
                cost_usd=None,
                exit_code=-1,
                is_error=True,
                raw_output=f"Process timed out after {timeout}s",
                capture_id=None,
            )
        raw_output = stdout_bytes.decode("utf-8", errors="replace")

        return self._parse_stream_output(raw_output, proc.returncode)

    def supported_assertions(self) -> set[str]:
        return {
            "contains",
            "not_contains",
            "regex",
            "tool_called",
            "skill_activated",
            "file_exists",
            "file_contains",
        }

    def stop(self) -> None:
        pass

    def _build_args(
        self, prompt: str, workspace: Path, session_id: str | None
    ) -> list[str]:
        args = [
            "claude",
            "-p",
            prompt,
            "--output-format",
            "stream-json",
            "--verbose",
            "--dangerously-skip-permissions",
        ]
        if self._config and self._config.model:
            args.extend(["--model", self._config.model])
        if self._config and self._config.max_cost is not None:
            args.extend(["--max-budget-usd", str(self._config.max_cost)])
        if session_id:
            args.extend(["--resume", session_id])
        if self._config:
            args.extend(self._config.extra_flags)
        return args

    def _parse_stream_output(self, raw_output: str, returncode: int) -> StepEvidence:
        text_parts = []
        tool_calls = []
        session_id = None
        duration_ms = 0.0
        cost_usd = None
        is_error = False

        for line in raw_output.strip().split("\n"):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            etype = event.get("type", "")

            if etype == "system" and event.get("subtype") == "init":
                session_id = event.get("session_id", session_id)

            elif etype == "assistant":
                msg = event.get("message", {})
                for block in msg.get("content", []):
                    if block.get("type") == "text":
                        text_parts.append(block["text"])
                    elif block.get("type") == "tool_use":
                        tool_calls.append(
                            ToolCallEvent(
                                tool_name=block.get("name", "unknown"),
                                status="started",
                                arguments=block.get("input"),
                            )
                        )

            elif etype == "user":
                tool_result = event.get("tool_use_result")
                if tool_result:
                    command_name = tool_result.get("commandName", "")
                    for tc in reversed(tool_calls):
                        if tc.status == "started":
                            tc.status = "completed"
                            if command_name:
                                tc.arguments = tc.arguments or {}
                                tc.arguments["_command_name"] = command_name
                            break

            elif etype == "result":
                session_id = event.get("session_id", session_id)
                duration_ms = event.get("duration_ms", duration_ms)
                cost_usd = event.get("total_cost_usd", cost_usd)
                is_error = event.get("is_error", is_error)

        response_text = "".join(text_parts)

        return StepEvidence(
            response_text=response_text,
            tool_calls=tool_calls,
            session_id=session_id,
            duration_ms=duration_ms,
            cost_usd=cost_usd,
            exit_code=returncode,
            is_error=is_error or returncode != 0,
            raw_output=raw_output,
            capture_id=None,
        )
