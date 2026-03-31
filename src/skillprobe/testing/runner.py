from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from skillprobe.testing.assertions import AssertionResult, check_assertion
from skillprobe.testing.loader import TestCase, TestSuite


class LLMClient(Protocol):
    async def call(self, system: str, message: str, model: str, provider: str) -> str: ...


@dataclass
class RunResult:
    test_name: str
    total_runs: int
    passed_runs: int
    failed_runs: int
    assertion_results: list[list[AssertionResult]]

    @property
    def pass_rate(self) -> float:
        if self.total_runs == 0:
            return 0.0
        return self.passed_runs / self.total_runs


class TestRunner:
    def __init__(self, client: LLMClient):
        self._client = client

    async def run_case(self, case: TestCase, system_prompt: str) -> RunResult:
        all_results: list[list[AssertionResult]] = []
        passed = 0
        for _ in range(case.runs):
            message = case.message
            if case.code_context:
                message = f"{case.code_context}\n\n{message}"
            response = await self._client.call(
                system=system_prompt,
                message=message,
                model="",
                provider="",
            )
            run_assertions = [
                check_assertion(a, response, system_prompt)
                for a in case.assertions
            ]
            all_results.append(run_assertions)
            if all(r.passed for r in run_assertions):
                passed += 1
        return RunResult(
            test_name=case.name,
            total_runs=case.runs,
            passed_runs=passed,
            failed_runs=case.runs - passed,
            assertion_results=all_results,
        )

    async def run_suite(self, suite: TestSuite) -> list[RunResult]:
        system_prompt = suite.base_context
        if suite.skill:
            skill_path = Path(suite.skill)
            if skill_path.exists():
                system_prompt += "\n\n" + skill_path.read_text(encoding="utf-8")
        results = []
        for case in suite.tests:
            result = await self.run_case(case, system_prompt)
            results.append(result)
        return results
