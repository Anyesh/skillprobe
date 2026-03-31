from datetime import datetime, timezone

from skillprobe.optimization.analyzer import FailurePattern, analyze_failures
from skillprobe.storage.models import Capture, CaptureStatus
from skillprobe.testing.loader import TestCase, TestSuite


def make_capture(response_text: str, session: str = "v1") -> Capture:
    return Capture(
        timestamp=datetime.now(timezone.utc),
        provider="anthropic", method="POST", path="/v1/messages",
        request_body={"model": "test", "messages": [{"role": "user", "content": "hi"}]},
        response_body={"content": [{"type": "text", "text": response_text}]},
        response_status=200,
        status=CaptureStatus.COMPLETED,
        session=session,
    )


class TestAnalyzeFailures:
    def test_finds_failing_assertions(self):
        suite = TestSuite(skill=None, tests=[
            TestCase(name="has return", message="any", assertions=[{"type": "contains", "value": "return"}]),
        ])
        captures = [make_capture("def foo(): return 42"), make_capture("hello world")]
        failures = analyze_failures(captures, suite)
        assert len(failures) == 1
        assert failures[0].test_name == "has return"
        assert failures[0].failure_rate == 0.5

    def test_no_failures_returns_empty(self):
        suite = TestSuite(skill=None, tests=[
            TestCase(name="has hello", message="any", assertions=[{"type": "contains", "value": "hello"}]),
        ])
        captures = [make_capture("hello"), make_capture("hello world")]
        assert analyze_failures(captures, suite) == []

    def test_respects_when_conditions(self):
        suite = TestSuite(skill=None, tests=[
            TestCase(
                name="no docstrings", message="any",
                when=[{"type": "regex", "value": r"def \w+\("}],
                assertions=[{"type": "not_contains", "value": '"""'}],
            ),
        ])
        captures = [make_capture("def foo():\n    return 42"), make_capture("just text")]
        failures = analyze_failures(captures, suite)
        assert failures == []

    def test_sorted_by_failure_rate(self):
        suite = TestSuite(skill=None, tests=[
            TestCase(name="low fail", message="any", assertions=[{"type": "contains", "value": "x"}]),
            TestCase(name="high fail", message="any", assertions=[{"type": "contains", "value": "zzz"}]),
        ])
        captures = [make_capture("x y z"), make_capture("x")]
        failures = analyze_failures(captures, suite)
        assert failures[0].test_name == "high fail"
