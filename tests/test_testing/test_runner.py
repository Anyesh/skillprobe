import pytest

from skillprobe.testing.assertions import AssertionResult
from skillprobe.testing.loader import TestCase, TestSuite
from skillprobe.testing.runner import TestRunner, RunResult


class FakeLLMClient:
    def __init__(self, responses: list[str]):
        self._responses = responses
        self._call_count = 0

    async def call(self, system: str, message: str, model: str, provider: str) -> str:
        idx = self._call_count % len(self._responses)
        self._call_count += 1
        return self._responses[idx]


class TestRunnerSingleCase:
    @pytest.mark.asyncio
    async def test_passes_when_assertions_met(self):
        client = FakeLLMClient(["Use parameterized queries to avoid SQL injection."])
        runner = TestRunner(client)
        tc = TestCase(
            name="test_sql",
            message="write login",
            assertions=[
                {"type": "contains", "value": "parameterized"},
                {"type": "contains", "value": "SQL"},
            ],
            runs=1,
        )
        result = await runner.run_case(tc, system_prompt="Be secure.")
        assert result.pass_rate == 1.0
        assert result.total_runs == 1

    @pytest.mark.asyncio
    async def test_fails_when_assertion_not_met(self):
        client = FakeLLMClient(["Hello world"])
        runner = TestRunner(client)
        tc = TestCase(
            name="test_fail",
            message="write login",
            assertions=[{"type": "contains", "value": "parameterized"}],
            runs=1,
        )
        result = await runner.run_case(tc, system_prompt="")
        assert result.pass_rate == 0.0


class TestRunnerMultipleRuns:
    @pytest.mark.asyncio
    async def test_statistical_pass_rate(self):
        client = FakeLLMClient([
            "Use parameterized queries.",
            "Here is a simple login function.",
            "Use parameterized queries.",
        ])
        runner = TestRunner(client)
        tc = TestCase(
            name="test_stats",
            message="write login",
            assertions=[{"type": "contains", "value": "parameterized"}],
            runs=3,
        )
        result = await runner.run_case(tc, system_prompt="")
        assert result.total_runs == 3
        assert result.passed_runs == 2
        assert abs(result.pass_rate - 2 / 3) < 0.01


class TestRunnerWhenConditions:
    @pytest.mark.asyncio
    async def test_skips_when_conditions_fail(self):
        client = FakeLLMClient(["Hello world, no code here."])
        runner = TestRunner(client)
        tc = TestCase(
            name="test_skip",
            message="hello",
            when=[{"type": "regex", "value": r"def \w+\("}],
            assertions=[{"type": "not_contains", "value": '"""'}],
            runs=1,
        )
        result = await runner.run_case(tc, system_prompt="")
        assert result.skipped_runs == 1
        assert result.evaluated_runs == 0
        assert result.passed_runs == 0

    @pytest.mark.asyncio
    async def test_evaluates_when_conditions_pass(self):
        client = FakeLLMClient(["def foo():\n    return 42"])
        runner = TestRunner(client)
        tc = TestCase(
            name="test_eval",
            message="write code",
            when=[{"type": "regex", "value": r"def \w+\("}],
            assertions=[{"type": "contains", "value": "return"}],
            runs=1,
        )
        result = await runner.run_case(tc, system_prompt="")
        assert result.skipped_runs == 0
        assert result.passed_runs == 1


class TestRunnerSuite:
    @pytest.mark.asyncio
    async def test_runs_full_suite(self):
        client = FakeLLMClient(["Use parameterized queries."])
        runner = TestRunner(client)
        suite = TestSuite(
            skill=None,
            base_context="You are helpful.",
            tests=[
                TestCase(name="t1", message="m1", assertions=[{"type": "contains", "value": "parameterized"}], runs=1),
                TestCase(name="t2", message="m2", assertions=[{"type": "contains", "value": "parameterized"}], runs=1),
            ],
        )
        results = await runner.run_suite(suite)
        assert len(results) == 2
        assert all(r.pass_rate == 1.0 for r in results)
