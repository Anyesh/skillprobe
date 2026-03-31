from dataclasses import dataclass
from typing import Any


@dataclass
class ToolCallEvent:
    tool_name: str
    status: str
    arguments: dict[str, Any] | None


@dataclass
class StepEvidence:
    response_text: str
    tool_calls: list[ToolCallEvent]
    session_id: str | None
    duration_ms: float
    cost_usd: float | None
    exit_code: int
    is_error: bool
    raw_output: str
    capture_id: int | None
