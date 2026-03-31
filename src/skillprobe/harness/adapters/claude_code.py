import asyncio
import atexit
import json
import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from skillprobe.harness.adapters.base import HarnessConfig
from skillprobe.harness.evidence import StepEvidence, ToolCallEvent

log = logging.getLogger("skillprobe.harness.claude_code")


class ClaudeCodeAdapter:
    def __init__(self):
        self._config: HarnessConfig | None = None
        self._proxy_proc: subprocess.Popen | None = None
        self._db_path: Path | None = None

    def start(self, config: HarnessConfig) -> None:
        self._config = config
        self._start_proxy()

    async def send_prompt(
        self, prompt: str, workspace: Path, session_id: str | None
    ) -> StepEvidence:
        args = self._build_args(prompt, workspace, session_id)
        env = self._build_env()

        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=workspace,
            env=env,
        )
        stdout_bytes, _ = await proc.communicate()
        raw_output = stdout_bytes.decode("utf-8", errors="replace")

        return self._parse_json_output(raw_output, proc.returncode)

    def supported_assertions(self) -> set[str]:
        return {
            "contains",
            "not_contains",
            "regex",
            "skill_present",
            "skill_loaded",
            "tool_called",
            "file_exists",
            "file_contains",
        }

    def stop(self) -> None:
        self._stop_proxy()

    def _start_proxy(self) -> None:
        port = self._config.proxy_port if self._config else 9339
        self._db_path = Path(f".skillprobe-harness-{port}.db")

        self._proxy_proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "skillprobe.harness.adapters._proxy_worker",
                "--port",
                str(port),
                "--db",
                str(self._db_path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        atexit.register(self._stop_proxy)

        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if self._proxy_proc.poll() is not None:
                stderr = (
                    self._proxy_proc.stderr.read().decode()
                    if self._proxy_proc.stderr
                    else ""
                )
                raise RuntimeError(f"Proxy process exited early: {stderr}")
            try:
                import httpx

                resp = httpx.get(f"http://127.0.0.1:{port}/health", timeout=1.0)
                if resp.status_code == 200:
                    log.info(
                        "Proxy started on port %d (pid %d)", port, self._proxy_proc.pid
                    )
                    return
            except Exception:
                time.sleep(0.2)

        self._stop_proxy()
        raise RuntimeError(f"Proxy failed to start on port {port} within 10s")

    def _stop_proxy(self) -> None:
        if self._proxy_proc and self._proxy_proc.poll() is None:
            self._proxy_proc.terminate()
            try:
                self._proxy_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proxy_proc.kill()
                self._proxy_proc.wait(timeout=2)
            log.info("Proxy stopped (pid %d)", self._proxy_proc.pid)
        self._proxy_proc = None

        if self._db_path and self._db_path.exists():
            self._db_path.unlink(missing_ok=True)
            self._db_path = None

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

    def _build_env(self) -> dict[str, str]:
        env = os.environ.copy()
        if self._config:
            env["ANTHROPIC_BASE_URL"] = f"http://127.0.0.1:{self._config.proxy_port}"
        return env

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
