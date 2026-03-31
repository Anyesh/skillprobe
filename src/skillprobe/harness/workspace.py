import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any

SKILL_PATHS = {
    "claude-code": ".claude/skills",
    "cursor": ".cursor/skills",
}


class WorkspaceManager:
    def __init__(self, work_dir: Path):
        self._work_dir = work_dir
        self._work_dir.mkdir(parents=True, exist_ok=True)

    def create(
        self,
        fixture: Path | None,
        skill: Path | None,
        harness: str,
    ) -> Path:
        workspace = self._work_dir / uuid.uuid4().hex[:12]
        if fixture and fixture.exists():
            shutil.copytree(fixture, workspace)
        else:
            workspace.mkdir(parents=True)

        if skill and skill.exists():
            skill_name = skill.name
            skill_base = SKILL_PATHS.get(harness, SKILL_PATHS["claude-code"])
            target = workspace / skill_base / skill_name
            shutil.copytree(skill, target)

        return workspace

    def run_setup(self, workspace: Path, setup_commands: list[dict[str, Any]]) -> None:
        for cmd in setup_commands:
            run_str = cmd.get("run", "")
            if not run_str:
                continue
            result = subprocess.run(
                ["sh", "-c", run_str],
                cwd=workspace,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"Setup command failed: {run_str}\n"
                    f"stdout: {result.stdout}\n"
                    f"stderr: {result.stderr}"
                )

    def cleanup(self, workspace: Path) -> None:
        if workspace.exists():
            shutil.rmtree(workspace)
