import asyncio
import json
from pathlib import Path

from skillprobe.adapters.base import HarnessConfig
from skillprobe.evidence import StepEvidence, ToolCallEvent

TOOL_CALL_KEYS = {
    "readToolCall": "Read",
    "shellToolCall": "Bash",
    "editToolCall": "Edit",
    "writeToolCall": "Write",
    "listToolCall": "LS",
    "searchToolCall": "Grep",
    "globToolCall": "Glob",
}


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
        is_error = False
        call_id_to_index = {}
        events_parsed = 0

        stripped = raw_output.strip()
        if stripped and not any(
            line.strip().startswith("{") for line in stripped.split("\n")
        ):
            raise RuntimeError(
                f"cursor subprocess produced non-stream-json output (exit "
                f"{returncode}); this usually means the model name is not "
                f"valid for cursor, or the cursor CLI errored before emitting "
                f"events. Raw output: {stripped[:500]}"
            )

        for line in stripped.split("\n"):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            events_parsed += 1

            etype = event.get("type", "")

            if etype == "system" and event.get("subtype") == "init":
                session_id = event.get("session_id", session_id)

            elif etype == "assistant":
                msg = event.get("message", {})
                for block in msg.get("content", []):
                    if block.get("type") == "text" and block.get("text"):
                        text_parts.append(block["text"])

            elif etype == "tool_call":
                call_id = event.get("call_id", "")
                tool_call_data = event.get("tool_call", {})
                tool_name, args = self._extract_tool_info(tool_call_data)

                if event.get("subtype") == "started":
                    if self._is_skill_read(tool_name, args):
                        tool_calls.append(
                            ToolCallEvent(
                                tool_name="Skill",
                                status="started",
                                arguments={"skill": self._extract_skill_name(args)},
                            )
                        )
                    else:
                        tool_calls.append(
                            ToolCallEvent(
                                tool_name=tool_name,
                                status="started",
                                arguments=args,
                            )
                        )
                    call_id_to_index[call_id] = len(tool_calls) - 1

                elif event.get("subtype") == "completed":
                    idx = call_id_to_index.get(call_id)
                    if idx is not None and idx < len(tool_calls):
                        tool_calls[idx].status = "completed"

            elif etype == "result":
                session_id = event.get("session_id", session_id)
                duration_ms = event.get("duration_ms", duration_ms)
                is_error = event.get("is_error", is_error)

        if events_parsed == 0 and stripped:
            raise RuntimeError(
                f"cursor subprocess produced output but no valid stream-json "
                f"events could be parsed (exit {returncode}). Raw output: "
                f"{stripped[:500]}"
            )

        return StepEvidence(
            response_text="".join(text_parts),
            tool_calls=tool_calls,
            session_id=session_id,
            duration_ms=duration_ms,
            cost_usd=None,
            exit_code=returncode,
            is_error=is_error or returncode != 0,
            raw_output=raw_output,
            capture_id=None,
        )

    def _extract_tool_info(self, tool_call_data: dict) -> tuple[str, dict | None]:
        for key, display_name in TOOL_CALL_KEYS.items():
            if key in tool_call_data:
                return display_name, tool_call_data[key].get("args")
        first_key = next(iter(tool_call_data), None)
        if first_key:
            return first_key, tool_call_data[first_key].get("args")
        return "unknown", None

    def _is_skill_read(self, tool_name: str, args: dict | None) -> bool:
        if tool_name != "Read" or not args:
            return False
        path = args.get("path", "")
        return path.endswith("SKILL.md")

    def _extract_skill_name(self, args: dict | None) -> str:
        if not args:
            return "unknown"
        path = args.get("path", "")
        parts = Path(path).parts
        for i, part in enumerate(parts):
            if part == "skills" and i + 1 < len(parts):
                return parts[i + 1]
        return Path(path).parent.name
