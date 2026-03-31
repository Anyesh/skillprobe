import json
from datetime import datetime, timezone

from skillprobe.storage.models import Capture, TestResult, CaptureStatus


class TestCapture:
    def test_create_capture(self):
        capture = Capture(
            timestamp=datetime.now(timezone.utc),
            provider="anthropic",
            method="POST",
            path="/v1/messages",
            request_body={"model": "claude-sonnet-4-6-20250514", "messages": []},
            status=CaptureStatus.COMPLETED,
        )
        assert capture.provider == "anthropic"
        assert capture.id is None

    def test_capture_serializes_to_dict(self):
        capture = Capture(
            timestamp=datetime.now(timezone.utc),
            provider="anthropic",
            method="POST",
            path="/v1/messages",
            request_body={"model": "claude-sonnet-4-6-20250514"},
            status=CaptureStatus.COMPLETED,
        )
        d = capture.to_dict()
        assert d["provider"] == "anthropic"
        assert isinstance(d["request_body"], str)

    def test_capture_from_dict_roundtrip(self):
        original = Capture(
            timestamp=datetime.now(timezone.utc),
            provider="openai",
            method="POST",
            path="/v1/chat/completions",
            request_body={"model": "gpt-4o"},
            response_body={"choices": []},
            status=CaptureStatus.COMPLETED,
            response_status=200,
        )
        d = original.to_dict()
        restored = Capture.from_dict(d)
        assert restored.provider == original.provider
        assert restored.request_body == original.request_body
        assert restored.response_body == original.response_body


class TestTestResult:
    def test_create_result(self):
        result = TestResult(
            test_name="catches SQL injection",
            assertion_type="llm_judge",
            passed=True,
            details="Model warned about SQL injection",
            run_index=0,
            total_runs=10,
        )
        assert result.passed is True
        assert result.run_index == 0
