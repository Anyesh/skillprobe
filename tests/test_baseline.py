import pytest

from skillprobe.baseline import (
    AssertionBaseline,
    BaselineClassification,
    classify_baseline,
)


def _mk(solo_a, solo_b, combined, total=10):
    return AssertionBaseline(
        assertion_index=0,
        assertion_type="regex",
        assertion_value="x",
        solo_a_passed=solo_a,
        solo_b_passed=solo_b,
        combined_passed=combined,
        total_runs=total,
    )


class TestClassifyBaseline:
    def test_ok_when_all_three_pass_equally(self):
        a = _mk(solo_a=9, solo_b=9, combined=9)
        assert classify_baseline(a, margin=0.15) == BaselineClassification.OK

    def test_regression_when_combined_drops_below_both_lowers(self):
        a = _mk(solo_a=10, solo_b=10, combined=3)
        assert classify_baseline(a, margin=0.15) == BaselineClassification.REGRESSION

    def test_shared_failure_when_both_solos_are_below_half(self):
        a = _mk(solo_a=2, solo_b=3, combined=1)
        assert (
            classify_baseline(a, margin=0.15) == BaselineClassification.SHARED_FAILURE
        )

    def test_flaky_when_drop_is_small(self):
        a = _mk(solo_a=10, solo_b=10, combined=8)
        assert classify_baseline(a, margin=0.15) == BaselineClassification.FLAKY

    def test_ok_when_combined_matches_solo(self):
        a = _mk(solo_a=8, solo_b=9, combined=8)
        assert classify_baseline(a, margin=0.15) == BaselineClassification.OK

    def test_regression_respects_tighter_margin(self):
        a = _mk(solo_a=10, solo_b=10, combined=7)
        assert classify_baseline(a, margin=0.05) == BaselineClassification.REGRESSION

    def test_flaky_at_larger_margin(self):
        a = _mk(solo_a=10, solo_b=10, combined=7)
        assert classify_baseline(a, margin=0.30) == BaselineClassification.FLAKY

    def test_shared_failure_takes_precedence_over_regression(self):
        a = _mk(solo_a=2, solo_b=2, combined=0)
        assert (
            classify_baseline(a, margin=0.15) == BaselineClassification.SHARED_FAILURE
        )


from skillprobe.adapters.base import HarnessConfig
from skillprobe.baseline import run_baseline_pairing
from skillprobe.loader import Scenario, ScenarioStep, ScenarioSuite


class BaselineFakeAdapter:
    def __init__(self, solo_a_responses, solo_b_responses, combined_responses):
        self._pools = {
            "a": solo_a_responses,
            "b": solo_b_responses,
            "combined": combined_responses,
        }
        self._mode = "a"
        self._idx = 0

    def set_mode(self, mode: str):
        self._mode = mode
        self._idx = 0

    def start(self, config):
        pass

    async def send_prompt(self, prompt, workspace, session_id):
        from skillprobe.evidence import StepEvidence

        pool = self._pools[self._mode]
        response = pool[self._idx % len(pool)]
        self._idx += 1
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
        return {"contains", "not_contains", "regex"}

    def stop(self):
        pass


@pytest.mark.asyncio
async def test_run_baseline_pairing_counts_three_configurations(tmp_path):
    skill_a = tmp_path / "skills" / "alpha"
    skill_a.mkdir(parents=True)
    (skill_a / "SKILL.md").write_text("---\nname: alpha\ndescription: first\n---\nA.")
    skill_b = tmp_path / "skills" / "beta"
    skill_b.mkdir(parents=True)
    (skill_b / "SKILL.md").write_text("---\nname: beta\ndescription: second\n---\nB.")

    adapter = BaselineFakeAdapter(
        solo_a_responses=["ok", "ok", "ok", "ok", "ok"],
        solo_b_responses=["ok", "ok", "ok", "ok", "ok"],
        combined_responses=["bad", "bad", "bad", "bad", "ok"],
    )
    config = HarnessConfig(harness="claude-code", model="m")
    suite = ScenarioSuite(
        harness="claude-code",
        model="m",
        timeout=60,
        skills=[],
        scenarios=[
            Scenario(
                name="demo",
                workspace=None,
                setup=[],
                steps=[
                    ScenarioStep(
                        prompt="go",
                        assertions=[{"type": "contains", "value": "ok"}],
                    ),
                ],
                after=[],
                timeout=None,
            ),
        ],
    )
    scenario_baselines = await run_baseline_pairing(
        suite=suite,
        adapter=adapter,
        config=config,
        base_skill=str(skill_a),
        paired_skill=str(skill_b),
        pairing_label="alpha + beta",
        runs=5,
        work_dir=tmp_path / "work",
    )
    assert len(scenario_baselines) == 1
    sb = scenario_baselines[0]
    assert sb.scenario_name == "demo"
    assert sb.pairing_label == "alpha + beta"
    assert len(sb.per_assertion) == 1
    a = sb.per_assertion[0]
    assert a.solo_a_passed == 5
    assert a.solo_b_passed == 5
    assert a.combined_passed == 1
    assert a.total_runs == 5
