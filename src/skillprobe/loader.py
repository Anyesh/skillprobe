from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ScenarioStep:
    prompt: str
    assertions: list[dict[str, Any]]
    runs: int = 1
    min_pass_rate: float = 1.0


@dataclass
class Scenario:
    name: str
    workspace: str | None
    setup: list[dict[str, Any]]
    steps: list[ScenarioStep]
    after: list[dict[str, Any]]
    timeout: int | None


@dataclass
class ScenarioSuite:
    harness: str
    model: str | None
    timeout: int
    skills: list[str]
    scenarios: list[Scenario]


def load_scenario_suite(path: Path) -> ScenarioSuite:
    if not path.exists():
        raise FileNotFoundError(f"Scenario suite not found: {path}")
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    skill_single = data.get("skill")
    skills_raw = data.get("skills")
    if skill_single is not None and skills_raw is not None:
        raise ValueError(
            f"{path}: cannot specify both 'skill' and 'skills'; use one or the other"
        )
    if skills_raw is not None:
        if not isinstance(skills_raw, list):
            raise ValueError(f"{path}: 'skills' must be a list of paths")
        skills = [str(s) for s in skills_raw]
    elif skill_single is not None:
        skills = [str(skill_single)]
    else:
        skills = []

    scenarios = []
    for s in data.get("scenarios", []):
        steps = []
        for step in s.get("steps", []):
            steps.append(
                ScenarioStep(
                    prompt=step["prompt"],
                    assertions=step.get("assert", []),
                    runs=step.get("runs", 1),
                    min_pass_rate=step.get("min_pass_rate", 1.0),
                )
            )
        scenarios.append(
            Scenario(
                name=s["name"],
                workspace=s.get("workspace"),
                setup=s.get("setup", []),
                steps=steps,
                after=s.get("after", []),
                timeout=s.get("timeout"),
            )
        )

    return ScenarioSuite(
        harness=data.get("harness", "claude-code"),
        model=data.get("model"),
        timeout=data.get("timeout", 120),
        skills=skills,
        scenarios=scenarios,
    )
