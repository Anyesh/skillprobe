from skillprobe.adapters.base import HarnessAdapter, HarnessConfig
from skillprobe.adapters.claude_code import ClaudeCodeAdapter
from skillprobe.adapters.cursor import CursorAdapter


def get_adapter(harness: str) -> HarnessAdapter:
    if harness == "claude-code":
        return ClaudeCodeAdapter()
    if harness == "cursor":
        return CursorAdapter()
    raise ValueError(f"Unknown harness: {harness}")
