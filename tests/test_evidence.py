from skillprobe.evidence import StepEvidence, ToolCallEvent


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
