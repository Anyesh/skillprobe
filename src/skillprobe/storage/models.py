import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class CaptureStatus(Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    STREAMING = "streaming"


@dataclass
class Capture:
    timestamp: datetime
    provider: str
    method: str
    path: str
    request_body: dict[str, Any]
    status: CaptureStatus
    id: int | None = None
    response_body: dict[str, Any] | None = None
    response_status: int | None = None
    parsed_data: dict[str, Any] | None = None
    duration_ms: float | None = None
    session: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "provider": self.provider,
            "method": self.method,
            "path": self.path,
            "request_body": json.dumps(self.request_body),
            "response_body": json.dumps(self.response_body) if self.response_body else None,
            "response_status": self.response_status,
            "status": self.status.value,
            "parsed_data": json.dumps(self.parsed_data) if self.parsed_data else None,
            "duration_ms": self.duration_ms,
            "session": self.session,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Capture":
        return cls(
            id=d.get("id"),
            timestamp=datetime.fromisoformat(d["timestamp"]),
            provider=d["provider"],
            method=d["method"],
            path=d["path"],
            request_body=json.loads(d["request_body"]) if isinstance(d["request_body"], str) else d["request_body"],
            response_body=json.loads(d["response_body"]) if isinstance(d.get("response_body"), str) else d.get("response_body"),
            response_status=d.get("response_status"),
            status=CaptureStatus(d["status"]),
            parsed_data=json.loads(d["parsed_data"]) if isinstance(d.get("parsed_data"), str) else d.get("parsed_data"),
            duration_ms=d.get("duration_ms"),
            session=d.get("session"),
        )


@dataclass
class TestResult:
    test_name: str
    assertion_type: str
    passed: bool
    details: str
    run_index: int
    total_runs: int
    capture_id: int | None = None
