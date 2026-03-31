from skillprobe.harness.adapters.base import HarnessAdapter, HarnessConfig
from skillprobe.harness.adapters.claude_code import ClaudeCodeAdapter
from skillprobe.harness.adapters.cursor import CursorAdapter


def get_adapter(harness: str) -> HarnessAdapter:
    if harness == "claude-code":
        return ClaudeCodeAdapter()
    if harness == "cursor":
        return CursorAdapter()
    raise ValueError(f"Unknown harness: {harness}")
