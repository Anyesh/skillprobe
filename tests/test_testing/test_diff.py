from datetime import datetime, timezone

from skillprobe.storage.models import Capture, CaptureStatus
from skillprobe.testing.diff import SessionResult, compute_session_results, format_diff
from skillprobe.testing.loader import TestCase, TestSuite


def make_capture(response_text: str, session: str = "v1") -> Capture:
    return Capture(
        timestamp=datetime.now(timezone.utc),
        provider="anthropic",
        method="POST",
        path="/v1/messages",
        request_body={"model": "test", "messages": [{"role": "user", "content": "hi"}]},
        response_body={"content": [{"type": "text", "text": response_text}]},
        response_status=200,
        status=CaptureStatus.COMPLETED,
        session=session,
    )


class TestComputeSessionResults:
    def test_computes_pass_rate(self):
        suite = TestSuite(skill=None, tests=[
            TestCase(name="has return", message="any", assertions=[{"type": "contains", "value": "return"}]),
        ])
        captures = [
            make_capture("def foo():\n    return 42"),
            make_capture("hello world"),
        ]
        result = compute_session_results(captures, suite)
        assert result.test_results["has return"] == 0.5

    def test_all_pass(self):
        suite = TestSuite(skill=None, tests=[
            TestCase(name="has hello", message="any", assertions=[{"type": "contains", "value": "hello"}]),
        ])
        captures = [make_capture("hello"), make_capture("hello world")]
        result = compute_session_results(captures, suite)
        assert result.test_results["has hello"] == 1.0

    def test_respects_when_conditions(self):
        suite = TestSuite(skill=None, tests=[
            TestCase(
                name="no docstrings",
                message="any",
                when=[{"type": "regex", "value": r"def \w+\("}],
                assertions=[{"type": "not_contains", "value": '"""'}],
            ),
        ])
        captures = [
            make_capture("def foo():\n    return 42"),
            make_capture("just text, no functions"),
        ]
        result = compute_session_results(captures, suite)
        assert result.test_results["no docstrings"] == 1.0


class TestFormatDiff:
    def test_two_sessions(self):
        results = [
            SessionResult(session="v1", test_results={"test_a": 0.5, "test_b": 0.8}, capture_count=10),
            SessionResult(session="v2", test_results={"test_a": 0.9, "test_b": 0.6}, capture_count=10),
        ]
        output = format_diff(results)
        assert "v1" in output
        assert "v2" in output
        assert "improved" in output
        assert "regressed" in output

    def test_needs_two_sessions(self):
        output = format_diff([SessionResult(session="v1", test_results={}, capture_count=0)])
        assert "Need at least 2" in output
