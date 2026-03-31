from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from skillprobe.evidence import StepEvidence


@dataclass
class HarnessConfig:
    harness: str
    model: str | None = None
    timeout: int = 120
    max_cost: float | None = None
    parallel: int = 1
    permission_mode: str = "dangerously-skip-permissions"
    extra_flags: list[str] = field(default_factory=list)


class HarnessAdapter(Protocol):
    def start(self, config: HarnessConfig) -> None: ...
    async def send_prompt(
        self, prompt: str, workspace: Path, session_id: str | None
    ) -> StepEvidence: ...
    def supported_assertions(self) -> set[str]: ...
    def stop(self) -> None: ...
