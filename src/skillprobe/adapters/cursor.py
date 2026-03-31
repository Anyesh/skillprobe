import asyncio
import json
from pathlib import Path

from skillprobe.adapters.base import HarnessConfig
from skillprobe.evidence import StepEvidence, ToolCallEvent


class CursorAdapter:
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
            "file_exists",
            "file_contains",
        }

    def stop(self) -> None:
        pass

    def _build_args(
        self, prompt: str, workspace: Path, session_id: str | None
    ) -> list[str]:
        args = [
            "agent",
            "-p",
            prompt,
            "--output-format",
            "stream-json",
            "--trust",
            "--force",
            "--workspace",
            str(workspace),
        ]
        if self._config and self._config.model:
            args.extend(["--model", self._config.model])
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
                msg = event.get("message", "")
                if msg:
                    text_parts.append(msg)

            elif etype == "tool_call":
                if event.get("subtype") == "started":
                    tool_calls.append(
                        ToolCallEvent(
                            tool_name=event.get("tool", "unknown"),
                            status="started",
                            arguments=event.get("arguments"),
                        )
                    )
                elif event.get("subtype") == "completed":
                    for tc in reversed(tool_calls):
                        if (
                            tc.tool_name == event.get("tool", "")
                            and tc.status == "started"
                        ):
                            tc.status = "completed"
                            break

            elif etype == "result":
                session_id = event.get("session_id", session_id)
                duration_ms = event.get("duration_ms", duration_ms)

        return StepEvidence(
            response_text="".join(text_parts),
            tool_calls=tool_calls,
            session_id=session_id,
            duration_ms=duration_ms,
            cost_usd=None,
            exit_code=returncode,
            is_error=returncode != 0,
            raw_output=raw_output,
            capture_id=None,
        )
