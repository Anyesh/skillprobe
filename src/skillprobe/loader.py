from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from skillprobe.assertions import ASSERTION_TYPES


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
class MatrixConfig:
    base: str
    pair_with: list[str]


@dataclass
class ScenarioSuite:
    harness: str
    model: str | None
    timeout: int
    skills: list[str]
    scenarios: list[Scenario]
    matrix: MatrixConfig | None = None


def _target_dir_name(skill_path: str) -> str:
    name = Path(skill_path).name
    if name.endswith(".md"):
        return name[:-3]
    return name


def _validate_assertion_type(
    path: Path,
    scenario_name: str,
    assertion: dict[str, Any],
    in_after: bool = False,
) -> None:
    atype = assertion.get("type")
    if atype not in ASSERTION_TYPES:
        location = "after block" if in_after else "step"
        valid = ", ".join(sorted(ASSERTION_TYPES))
        raise ValueError(
            f"{path}: unknown assertion type {atype!r} in {location} of "
            f"scenario {scenario_name!r}. Valid types: {valid}"
        )


def load_scenario_suite(path: Path) -> ScenarioSuite:
    if not path.exists():
        raise FileNotFoundError(f"Scenario suite not found: {path}")
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError(
            f"{path}: scenario suite must be a YAML mapping at the top level"
        )

    if "activation" in data:
        raise ValueError(
            f"{path}: this file contains an 'activation:' block, which is the "
            f"format for `skillprobe activation` test files. Use "
            f"`load_activation_suite` or the `skillprobe activation` command, "
            f"or remove the 'activation:' block if this is meant to be a "
            f"behavioral test."
        )

    if "scenarios" not in data:
        raise ValueError(
            f"{path}: scenario suite is missing a 'scenarios:' block; this is "
            f"required for `skillprobe run` files"
        )

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

    matrix_raw = data.get("matrix")
    matrix: MatrixConfig | None = None
    if matrix_raw is not None:
        if not isinstance(matrix_raw, dict):
            raise ValueError(f"{path}: 'matrix' must be a mapping")
        if skills_raw is not None or skill_single is not None:
            raise ValueError(
                f"{path}: cannot specify both 'skills' and 'matrix' at suite level; "
                f"pick one"
            )
        base_raw = matrix_raw.get("base")
        if not isinstance(base_raw, str):
            raise ValueError(f"{path}: 'matrix.base' must be a string path")
        pair_with_raw = matrix_raw.get("pair_with")
        if not isinstance(pair_with_raw, list) or not pair_with_raw:
            raise ValueError(
                f"{path}: 'matrix.pair_with' must be a non-empty list of paths"
            )
        matrix = MatrixConfig(
            base=base_raw,
            pair_with=[str(p) for p in pair_with_raw],
        )

    seen: dict[str, list[str]] = {}
    for s in skills:
        seen.setdefault(_target_dir_name(s), []).append(s)
    collisions = {k: v for k, v in seen.items() if len(v) > 1}
    if collisions:
        lines = [
            f"{path}: skill name collision; multiple skills would map to the same workspace directory:"
        ]
        for target, sources in collisions.items():
            lines.append(f"  {target}: {', '.join(sources)}")
        raise ValueError("\n".join(lines))

    scenarios = []
    for s in data.get("scenarios", []):
        steps = []
        for step in s.get("steps", []):
            raw_assertions = step.get("assert", [])
            for a in raw_assertions:
                _validate_assertion_type(path, s.get("name", "?"), a)
            steps.append(
                ScenarioStep(
                    prompt=step["prompt"],
                    assertions=raw_assertions,
                    runs=step.get("runs", 1),
                    min_pass_rate=step.get("min_pass_rate", 1.0),
                )
            )
        after_assertions = s.get("after", [])
        for a in after_assertions:
            _validate_assertion_type(path, s.get("name", "?"), a, in_after=True)
        scenarios.append(
            Scenario(
                name=s["name"],
                workspace=s.get("workspace"),
                setup=s.get("setup", []),
                steps=steps,
                after=after_assertions,
                timeout=s.get("timeout"),
            )
        )

    return ScenarioSuite(
        harness=data.get("harness", "claude-code"),
        model=data.get("model"),
        timeout=data.get("timeout", 120),
        skills=skills,
        scenarios=scenarios,
        matrix=matrix,
    )
