from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class TestCase:
    name: str
    message: str
    assertions: list[dict[str, Any]]
    runs: int = 1
    code_context: str | None = None
    when: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class TestSuite:
    skill: str | None
    tests: list[TestCase]
    base_context: str = ""
    provider: str = "anthropic"
    model: str = "claude-haiku-4-5-20251001"


def load_test_suite(path: Path) -> TestSuite:
    if not path.exists():
        raise FileNotFoundError(f"Test suite not found: {path}")
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    tests = []
    for t in data.get("tests", []):
        tests.append(TestCase(
            name=t["name"],
            message=t["message"],
            assertions=t.get("assert", []),
            runs=t.get("runs", 1),
            code_context=t.get("code_context"),
            when=t.get("when", []),
        ))

    return TestSuite(
        skill=data.get("skill"),
        tests=tests,
        base_context=data.get("base_context", ""),
        provider=data.get("provider", "anthropic"),
        model=data.get("model", "claude-haiku-4-5-20251001"),
    )
