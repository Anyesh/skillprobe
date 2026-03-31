from skillprobe.harness.assertions import HarnessAssertionResult
from skillprobe.harness.reporter import (
    ScenarioResult,
    StepResult,
    format_harness_results,
)


class TestFormatHarnessResults:
    def test_all_passing(self):
        results = [
            ScenarioResult(
                scenario_name="skill activates",
                steps=[
                    StepResult(
                        step_index=0,
                        prompt="commit my changes",
                        assertions=[
                            HarnessAssertionResult("contains", True, "'commit' found")
                        ],
                        skipped_assertions=0,
                    ),
                ],
                after_assertions=[],
                passed=True,
                duration_ms=3000.0,
                cost_usd=0.01,
                error=None,
            ),
        ]
        output = format_harness_results(results)
        assert "PASS" in output
        assert "skill activates" in output

    def test_failing_scenario(self):
        results = [
            ScenarioResult(
                scenario_name="negative test",
                steps=[
                    StepResult(
                        step_index=0,
                        prompt="hello",
                        assertions=[
                            HarnessAssertionResult(
                                "not_contains", False, "'commit' found in response"
                            )
                        ],
                        skipped_assertions=0,
                    ),
                ],
                after_assertions=[],
                passed=False,
                duration_ms=2000.0,
                cost_usd=None,
                error=None,
            ),
        ]
        output = format_harness_results(results)
        assert "FAIL" in output
        assert "'commit' found in response" in output

    def test_skipped_assertions_shown(self):
        results = [
            ScenarioResult(
                scenario_name="cursor test",
                steps=[
                    StepResult(
                        step_index=0,
                        prompt="test",
                        assertions=[HarnessAssertionResult("contains", True, "ok")],
                        skipped_assertions=2,
                    ),
                ],
                after_assertions=[],
                passed=True,
                duration_ms=1000.0,
                cost_usd=None,
                error=None,
            ),
        ]
        output = format_harness_results(results)
        assert "skipped" in output.lower()

    def test_summary_line(self):
        results = [
            ScenarioResult("s1", [], [], True, 1000.0, 0.01, None),
            ScenarioResult("s2", [], [], False, 2000.0, 0.02, None),
            ScenarioResult("s3", [], [], True, 1500.0, None, None),
        ]
        output = format_harness_results(results)
        assert "2/3 passed" in output

    def test_cost_summary_when_available(self):
        results = [
            ScenarioResult("s1", [], [], True, 1000.0, 0.05, None),
            ScenarioResult("s2", [], [], True, 2000.0, 0.03, None),
        ]
        output = format_harness_results(results)
        assert "$0.08" in output

    def test_error_scenario(self):
        results = [
            ScenarioResult("broken", [], [], False, 0, None, "Timeout after 120s"),
        ]
        output = format_harness_results(results)
        assert "ERROR" in output
        assert "Timeout" in output
