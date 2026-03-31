from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ScenarioStep:
    prompt: str
    assertions: list[dict[str, Any]]


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
    skill: str | None
    scenarios: list[Scenario]


def load_scenario_suite(path: Path) -> ScenarioSuite:
    if not path.exists():
        raise FileNotFoundError(f"Scenario suite not found: {path}")
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    scenarios = []
    for s in data.get("scenarios", []):
        steps = []
        for step in s.get("steps", []):
            steps.append(
                ScenarioStep(
                    prompt=step["prompt"],
                    assertions=step.get("assert", []),
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
        skill=data.get("skill"),
        scenarios=scenarios,
    )
