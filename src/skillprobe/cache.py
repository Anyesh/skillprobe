import hashlib
import json
import os
import time
from pathlib import Path

from skillprobe.evidence import StepEvidence, ToolCallEvent


def compute_cache_key(
    skills: list[Path],
    prompt: str,
    model: str | None,
    harness: str,
    version: str,
) -> str:
    h = hashlib.sha256()
    h.update(f"version={version}\n".encode())
    h.update(f"harness={harness}\n".encode())
    h.update(f"model={model or ''}\n".encode())
    h.update(f"prompt={prompt}\n".encode())
    h.update(b"---\n")
    for skill_path in sorted(str(p) for p in skills):
        p = Path(skill_path)
        h.update(f"skill={skill_path}\n".encode())
        if not p.exists():
            h.update(b"missing\n")
            continue
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file():
                    rel = f.relative_to(p)
                    h.update(f"file={rel}\n".encode())
                    h.update(f.read_bytes())
                    h.update(b"\n")
        else:
            h.update(p.read_bytes())
            h.update(b"\n")
    return h.hexdigest()


class RunCache:
    def __init__(
        self,
        cache_dir: Path,
        ttl_hours: int = 24,
        disabled: bool = False,
    ) -> None:
        self._cache_dir = cache_dir
        self._ttl_seconds = ttl_hours * 3600
        self._disabled = disabled
        if not disabled:
            self._cache_dir.mkdir(parents=True, exist_ok=True)

    def get(self, key: str) -> StepEvidence | None:
        if self._disabled:
            return None
        path = self._path_for(key)
        if not path.exists():
            return None
        try:
            with open(path, encoding="utf-8") as f:
                entry = json.load(f)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return None
        stored_at = entry.get("stored_at", 0)
        if self._ttl_seconds <= 0 or time.time() - stored_at > self._ttl_seconds:
            return None
        ev = entry.get("evidence")
        if not isinstance(ev, dict):
            return None
        tool_calls = [
            ToolCallEvent(
                tool_name=tc.get("tool_name", ""),
                status=tc.get("status", ""),
                arguments=tc.get("arguments"),
            )
            for tc in ev.get("tool_calls", [])
        ]
        return StepEvidence(
            response_text=ev.get("response_text", ""),
            tool_calls=tool_calls,
            session_id=ev.get("session_id"),
            duration_ms=ev.get("duration_ms", 0.0),
            cost_usd=ev.get("cost_usd"),
            exit_code=ev.get("exit_code", 0),
            is_error=ev.get("is_error", False),
            raw_output=ev.get("raw_output", ""),
            capture_id=ev.get("capture_id"),
        )

    def put(self, key: str, evidence: StepEvidence) -> None:
        if self._disabled:
            return
        entry = {
            "stored_at": time.time(),
            "evidence": {
                "response_text": evidence.response_text,
                "tool_calls": [
                    {
                        "tool_name": tc.tool_name,
                        "status": tc.status,
                        "arguments": tc.arguments,
                    }
                    for tc in evidence.tool_calls
                ],
                "session_id": evidence.session_id,
                "duration_ms": evidence.duration_ms,
                "cost_usd": evidence.cost_usd,
                "exit_code": evidence.exit_code,
                "is_error": evidence.is_error,
                "raw_output": evidence.raw_output,
                "capture_id": evidence.capture_id,
            },
        }
        tmp = self._path_for(key).with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(entry, f)
        tmp.replace(self._path_for(key))

    def _path_for(self, key: str) -> Path:
        return self._cache_dir / f"{key}.json"


def default_cache_dir() -> Path:
    xdg = os.environ.get("XDG_CACHE_HOME")
    if xdg:
        return Path(xdg) / "skillprobe" / "runs"
    return Path.home() / ".cache" / "skillprobe" / "runs"


def cache_disabled_from_env() -> bool:
    return os.environ.get("SKILLPROBE_NO_CACHE", "").lower() in ("1", "true", "yes")


def ttl_hours_from_env(default: int = 24) -> int:
    raw = os.environ.get("SKILLPROBE_CACHE_TTL_HOURS")
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default
