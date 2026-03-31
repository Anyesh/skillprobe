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

        return self._parse_json_output(raw_output, proc.returncode)

    def supported_assertions(self) -> set[str]:
        return {
            "contains",
            "not_contains",
            "regex",
            "tool_called",
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
            "json",
            "--no-session-persistence",
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

    def _parse_json_output(self, raw_output: str, returncode: int) -> StepEvidence:
        try:
            data = json.loads(raw_output)
        except json.JSONDecodeError:
            return StepEvidence(
                response_text=raw_output,
                tool_calls=[],
                session_id=None,
                duration_ms=0,
                cost_usd=None,
                exit_code=returncode,
                is_error=True,
                raw_output=raw_output,
                capture_id=None,
            )

        return StepEvidence(
            response_text=data.get("result", ""),
            tool_calls=[],
            session_id=data.get("session_id"),
            duration_ms=data.get("duration_ms", 0),
            cost_usd=data.get("total_cost_usd"),
            exit_code=returncode,
            is_error=data.get("is_error", False),
            raw_output=raw_output,
            capture_id=None,
        )
