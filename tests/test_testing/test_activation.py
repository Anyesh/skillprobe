from datetime import datetime, timezone
from pathlib import Path

import pytest

from skillprobe.storage.models import Capture, CaptureStatus
from skillprobe.testing.activation import (
    ActivationCase,
    ActivationResult,
    check_activations,
    format_activation_results,
    load_activation_tests,
)


def make_capture(user_message: str, system_prompt: str, capture_id: int = 1) -> Capture:
    return Capture(
        id=capture_id,
        timestamp=datetime.now(timezone.utc),
        provider="anthropic",
        method="POST",
        path="/v1/messages",
        request_body={
            "model": "test",
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_message}],
        },
        response_body={"content": [{"type": "text", "text": "response"}]},
        response_status=200,
        status=CaptureStatus.COMPLETED,
    )


class TestLoadActivationTests:
    def test_loads_from_yaml(self, tmp_path):
        content = """
activations:
  - skill: clean-python
    should_load_when:
      - "write python code"
    should_not_load_when:
      - "hello"
"""
        f = tmp_path / "test.yaml"
        f.write_text(content)
        cases = load_activation_tests(f)
        assert len(cases) == 1
        assert cases[0].skill == "clean-python"
        assert cases[0].should_load_when == ["write python code"]
        assert cases[0].should_not_load_when == ["hello"]

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_activation_tests(tmp_path / "nonexistent.yaml")

    def test_empty_lists_default(self, tmp_path):
        content = """
activations:
  - skill: test-skill
"""
        f = tmp_path / "test.yaml"
        f.write_text(content)
        cases = load_activation_tests(f)
        assert cases[0].should_load_when == []
        assert cases[0].should_not_load_when == []


class TestCheckActivations:
    def test_skill_correctly_loaded(self):
        cases = [ActivationCase(
            skill="clean-python",
            should_load_when=["write python"],
            should_not_load_when=[],
        )]
        captures = [make_capture("write python code please", "You are helpful.\n\n## Skill: clean-python\nUse type hints.")]
        results = check_activations(cases, captures)
        assert len(results) == 1
        assert results[0].passed is True
        assert results[0].expected_loaded is True
        assert results[0].actually_loaded is True

    def test_skill_correctly_not_loaded(self):
        cases = [ActivationCase(
            skill="sqlalchemy",
            should_load_when=[],
            should_not_load_when=["hello"],
        )]
        captures = [make_capture("hello there", "You are a general assistant.")]
        results = check_activations(cases, captures)
        assert len(results) == 1
        assert results[0].passed is True
        assert results[0].expected_loaded is False
        assert results[0].actually_loaded is False

    def test_skill_should_load_but_missing(self):
        cases = [ActivationCase(
            skill="clean-python",
            should_load_when=["write python"],
            should_not_load_when=[],
        )]
        captures = [make_capture("write python code", "You are a general assistant. No skills here.")]
        results = check_activations(cases, captures)
        assert results[0].passed is False
        assert results[0].expected_loaded is True
        assert results[0].actually_loaded is False

    def test_skill_should_not_load_but_present(self):
        cases = [ActivationCase(
            skill="sqlalchemy",
            should_load_when=[],
            should_not_load_when=["hello"],
        )]
        captures = [make_capture("hello", "System prompt.\n\n## sqlalchemy guide\nUse ORM.")]
        results = check_activations(cases, captures)
        assert results[0].passed is False

    def test_no_matching_capture(self):
        cases = [ActivationCase(
            skill="test",
            should_load_when=["specific trigger"],
            should_not_load_when=[],
        )]
        captures = [make_capture("completely different message", "system")]
        results = check_activations(cases, captures)
        assert results[0].capture_id is None

    def test_multiple_skills(self):
        cases = [
            ActivationCase(skill="python", should_load_when=["write python"], should_not_load_when=[]),
            ActivationCase(skill="sqlalchemy", should_load_when=["database model"], should_not_load_when=[]),
        ]
        captures = [
            make_capture("write python function", "## python skill\nUse hints.", 1),
            make_capture("create database model", "## sqlalchemy\nUse ORM.", 2),
        ]
        results = check_activations(cases, captures)
        assert len(results) == 2
        assert all(r.passed for r in results)


class TestFormatActivationResults:
    def test_formats_mixed_results(self):
        results = [
            ActivationResult("skill-a", "trigger 1", True, True, 1),
            ActivationResult("skill-a", "trigger 2", False, True, 2),
            ActivationResult("skill-b", "trigger 3", True, True, 3),
        ]
        output = format_activation_results(results)
        assert "[OK]" in output
        assert "[!!]" in output
        assert "skill-a" in output
        assert "skill-b" in output

    def test_formats_no_capture(self):
        results = [ActivationResult("skill-a", "rare trigger", True, False, None)]
        output = format_activation_results(results)
        assert "[--]" in output
        assert "no matching capture" in output
