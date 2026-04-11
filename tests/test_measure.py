from skillprobe.measure import (
    VarianceClass,
    classify_pass_rate,
    wilson_confidence_interval,
)


class TestClassifyPassRate:
    def test_deterministic_at_1_0(self):
        assert classify_pass_rate(1.0) == VarianceClass.DETERMINISTIC

    def test_deterministic_at_high_values(self):
        assert classify_pass_rate(0.96) == VarianceClass.DETERMINISTIC

    def test_probabilistic_mid_range(self):
        assert classify_pass_rate(0.85) == VarianceClass.PROBABILISTIC

    def test_probabilistic_lower_bound(self):
        assert classify_pass_rate(0.70) == VarianceClass.PROBABILISTIC

    def test_noisy_at_half(self):
        assert classify_pass_rate(0.5) == VarianceClass.NOISY

    def test_noisy_lower_bound(self):
        assert classify_pass_rate(0.30) == VarianceClass.NOISY

    def test_unreliable_below_threshold(self):
        assert classify_pass_rate(0.10) == VarianceClass.UNRELIABLE

    def test_unreliable_at_zero(self):
        assert classify_pass_rate(0.0) == VarianceClass.UNRELIABLE


class TestWilsonConfidenceInterval:
    def test_all_pass_100_runs_is_tight(self):
        lo, hi = wilson_confidence_interval(passed=100, total=100)
        assert lo > 0.96
        assert hi == 1.0

    def test_half_pass_20_runs_is_wide(self):
        lo, hi = wilson_confidence_interval(passed=10, total=20)
        assert lo < 0.35
        assert hi > 0.65

    def test_all_fail_is_lower_bound_zero(self):
        lo, hi = wilson_confidence_interval(passed=0, total=20)
        assert lo == 0.0
        assert hi < 0.2

    def test_zero_total_returns_full_interval(self):
        lo, hi = wilson_confidence_interval(passed=0, total=0)
        assert lo == 0.0
        assert hi == 1.0


import pytest

from skillprobe.adapters.base import HarnessConfig
from skillprobe.loader import Scenario, ScenarioStep, ScenarioSuite
from skillprobe.measure import measure_suite


class FakeAdapter:
    def __init__(self, responses):
        self._responses = responses
        self._i = 0

    def start(self, config):
        pass

    async def send_prompt(self, prompt, workspace, session_id):
        from skillprobe.evidence import StepEvidence

        response = self._responses[self._i % len(self._responses)]
        self._i += 1
        return StepEvidence(
            response_text=response,
            tool_calls=[],
            session_id="s",
            duration_ms=10.0,
            cost_usd=0.001,
            exit_code=0,
            is_error=False,
            raw_output=response,
            capture_id=None,
        )

    def supported_assertions(self):
        return {
            "contains",
            "not_contains",
            "regex",
            "tool_called",
            "file_exists",
        }

    def stop(self):
        pass


@pytest.mark.asyncio
async def test_measure_suite_reports_pass_rate_per_assertion(tmp_path):
    adapter = FakeAdapter(
        [
            "I committed it",
            "I committed it",
            "I did something else",
            "I committed it",
            "I did something else",
        ]
    )
    config = HarnessConfig(harness="claude-code", model="m")
    suite = ScenarioSuite(
        harness="claude-code",
        model="m",
        timeout=60,
        skills=[],
        scenarios=[
            Scenario(
                name="commit variance",
                workspace=None,
                setup=[],
                steps=[
                    ScenarioStep(
                        prompt="commit",
                        assertions=[{"type": "contains", "value": "committed"}],
                    ),
                ],
                after=[],
                timeout=None,
            ),
        ],
    )
    results = await measure_suite(
        suite=suite, adapter=adapter, config=config, runs=5, work_dir=tmp_path
    )
    assert len(results) == 1
    scenario = results[0]
    assert scenario.scenario_name == "commit variance"
    assert scenario.total_runs == 5
    assert len(scenario.per_assertion) == 1
    assertion = scenario.per_assertion[0]
    assert assertion.total == 5
    assert assertion.passed == 3
    assert assertion.pass_rate == 0.6
