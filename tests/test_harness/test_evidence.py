from pathlib import Path

from skillprobe.harness.evidence import ScenarioEvidence, StepEvidence, ToolCallEvent


class TestStepEvidence:
    def test_construction(self):
        tool = ToolCallEvent(
            tool_name="Bash", status="completed", arguments={"command": "ls"}
        )
        evidence = StepEvidence(
            response_text="Hello",
            tool_calls=[tool],
            session_id="abc-123",
            duration_ms=1500.0,
            cost_usd=0.01,
            exit_code=0,
            is_error=False,
            raw_output='{"result": "Hello"}',
            capture_id=1,
        )
        assert evidence.response_text == "Hello"
        assert len(evidence.tool_calls) == 1
        assert evidence.tool_calls[0].tool_name == "Bash"
        assert evidence.cost_usd == 0.01

    def test_defaults_for_cursor(self):
        evidence = StepEvidence(
            response_text="Hi",
            tool_calls=[],
            session_id=None,
            duration_ms=500.0,
            cost_usd=None,
            exit_code=0,
            is_error=False,
            raw_output="Hi",
            capture_id=None,
        )
        assert evidence.cost_usd is None
        assert evidence.capture_id is None


class TestScenarioEvidence:
    def test_total_cost_sums_steps(self):
        s1 = StepEvidence(
            response_text="a",
            tool_calls=[],
            session_id=None,
            duration_ms=100.0,
            cost_usd=0.01,
            exit_code=0,
            is_error=False,
            raw_output="",
            capture_id=None,
        )
        s2 = StepEvidence(
            response_text="b",
            tool_calls=[],
            session_id=None,
            duration_ms=200.0,
            cost_usd=0.02,
            exit_code=0,
            is_error=False,
            raw_output="",
            capture_id=None,
        )
        scenario = ScenarioEvidence(
            scenario_name="test",
            steps=[s1, s2],
            workspace_path=Path("/tmp/test"),
            total_duration_ms=300.0,
            total_cost_usd=0.03,
        )
        assert scenario.total_cost_usd == 0.03
        assert len(scenario.steps) == 2
