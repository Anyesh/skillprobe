import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from skillprobe.adapters.base import HarnessAdapter, HarnessConfig
from skillprobe.evidence import StepEvidence
from skillprobe.workspace import WorkspaceManager


@dataclass
class ActivationSuite:
    harness: str
    model: str | None
    timeout: int
    skill: str | None
    skill_name: str
    should_activate: list[str]
    should_not_activate: list[str]


@dataclass
class ActivationResult:
    prompt: str
    expected_active: bool
    actually_active: bool
    activated_skills: list[str]
    duration_ms: float
    cost_usd: float | None

    @property
    def passed(self) -> bool:
        return self.expected_active == self.actually_active


def load_activation_suite(path: Path) -> ActivationSuite:
    if not path.exists():
        raise FileNotFoundError(f"Activation suite not found: {path}")
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    activation = data.get("activation", {})

    return ActivationSuite(
        harness=data.get("harness", "claude-code"),
        model=data.get("model"),
        timeout=data.get("timeout", 120),
        skill=data.get("skill"),
        skill_name=activation.get("skill_name", ""),
        should_activate=activation.get("should_activate", []),
        should_not_activate=activation.get("should_not_activate", []),
    )


def _find_activated_skills(evidence: StepEvidence) -> list[str]:
    skills = []
    for tc in evidence.tool_calls:
        if tc.tool_name != "Skill":
            continue
        skill_arg = (tc.arguments or {}).get("skill", "")
        if skill_arg:
            skills.append(skill_arg)
    return skills


def _skill_matches(activated_skills: list[str], skill_name: str) -> bool:
    for activated in activated_skills:
        if skill_name.lower() in activated.lower():
            return True
    return False


async def run_activation_suite(
    suite: ActivationSuite,
    adapter: HarnessAdapter,
    config: HarnessConfig,
    work_dir: Path,
) -> list[ActivationResult]:
    adapter.start(config)
    workspace_mgr = WorkspaceManager(work_dir)
    results = []

    skill_paths = [Path(suite.skill)] if suite.skill else None

    try:
        all_prompts = [(prompt, True) for prompt in suite.should_activate] + [
            (prompt, False) for prompt in suite.should_not_activate
        ]

        for prompt, expected_active in all_prompts:
            workspace = workspace_mgr.create(
                fixture=None, skills=skill_paths, harness=config.harness
            )
            try:
                start = time.monotonic()
                evidence = await adapter.send_prompt(prompt, workspace, None)
                duration_ms = (time.monotonic() - start) * 1000

                activated_skills = _find_activated_skills(evidence)
                actually_active = _skill_matches(activated_skills, suite.skill_name)

                results.append(
                    ActivationResult(
                        prompt=prompt,
                        expected_active=expected_active,
                        actually_active=actually_active,
                        activated_skills=activated_skills,
                        duration_ms=duration_ms,
                        cost_usd=evidence.cost_usd,
                    )
                )
            except Exception:
                results.append(
                    ActivationResult(
                        prompt=prompt,
                        expected_active=expected_active,
                        actually_active=False,
                        activated_skills=[],
                        duration_ms=0,
                        cost_usd=None,
                    )
                )
            finally:
                workspace_mgr.cleanup(workspace)
    finally:
        adapter.stop()

    return results


def format_activation_results(results: list[ActivationResult], skill_name: str) -> str:
    lines = [f"  {skill_name}:"]
    passed = 0
    failed = 0
    total_cost = 0.0
    has_cost = False

    for r in results:
        if r.cost_usd is not None:
            total_cost += r.cost_usd
            has_cost = True

        dur = f"{r.duration_ms / 1000:.1f}s"
        cost_str = f" ${r.cost_usd:.4f}" if r.cost_usd is not None else ""

        if r.passed:
            action = "activated" if r.expected_active else "did not activate"
            lines.append(f'    [OK] "{r.prompt}" ({dur}{cost_str})')
            lines.append(f"         correctly {action}")
            if r.activated_skills:
                lines.append(f"         loaded: {', '.join(r.activated_skills)}")
            passed += 1
        else:
            expected = "activate" if r.expected_active else "not activate"
            actual = "activated" if r.actually_active else "did not activate"
            lines.append(f'    [!!] "{r.prompt}" ({dur}{cost_str})')
            lines.append(f"         expected to {expected}, but {actual}")
            if r.activated_skills:
                lines.append(f"         loaded: {', '.join(r.activated_skills)}")
            failed += 1

    lines.append("")
    total = passed + failed
    lines.append(f"  {passed}/{total} passed")
    if has_cost:
        lines.append(f"  Total cost: ${total_cost:.2f}")

    return "\n".join(lines)
