from pathlib import Path

import pytest

from skillprobe.assertions import (
    check_harness_assertion,
    HarnessAssertionResult,
)
from skillprobe.evidence import StepEvidence, ToolCallEvent


def make_evidence(
    response_text: str = "hello",
    tool_calls: list[ToolCallEvent] | None = None,
) -> StepEvidence:
    return StepEvidence(
        response_text=response_text,
        tool_calls=tool_calls or [],
        session_id=None,
        duration_ms=100.0,
        cost_usd=None,
        exit_code=0,
        is_error=False,
        raw_output="",
        capture_id=None,
    )


class TestToolCalled:
    def test_passes_when_tool_was_called(self):
        evidence = make_evidence(
            tool_calls=[
                ToolCallEvent(tool_name="Bash", status="completed", arguments=None),
            ]
        )
        result = check_harness_assertion(
            {"type": "tool_called", "value": "Bash"}, evidence
        )
        assert result.passed is True

    def test_fails_when_tool_not_called(self):
        evidence = make_evidence(tool_calls=[])
        result = check_harness_assertion(
            {"type": "tool_called", "value": "Bash"}, evidence
        )
        assert result.passed is False

    def test_case_insensitive(self):
        evidence = make_evidence(
            tool_calls=[
                ToolCallEvent(tool_name="Bash", status="completed", arguments=None),
            ]
        )
        result = check_harness_assertion(
            {"type": "tool_called", "value": "bash"}, evidence
        )
        assert result.passed is True


class TestFileExists:
    def test_passes_when_file_exists(self, tmp_path):
        (tmp_path / "output.txt").write_text("data")
        result = check_harness_assertion(
            {"type": "file_exists", "value": "output.txt"},
            make_evidence(),
            workspace=tmp_path,
        )
        assert result.passed is True

    def test_fails_when_file_missing(self, tmp_path):
        result = check_harness_assertion(
            {"type": "file_exists", "value": "missing.txt"},
            make_evidence(),
            workspace=tmp_path,
        )
        assert result.passed is False

    def test_nested_path(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("code")
        result = check_harness_assertion(
            {"type": "file_exists", "value": "src/main.py"},
            make_evidence(),
            workspace=tmp_path,
        )
        assert result.passed is True


class TestFileContains:
    def test_passes_when_content_found(self, tmp_path):
        (tmp_path / "main.py").write_text("def hello():\n    return 42")
        result = check_harness_assertion(
            {"type": "file_contains", "value": "main.py:def hello"},
            make_evidence(),
            workspace=tmp_path,
        )
        assert result.passed is True

    def test_fails_when_content_missing(self, tmp_path):
        (tmp_path / "main.py").write_text("x = 1")
        result = check_harness_assertion(
            {"type": "file_contains", "value": "main.py:def hello"},
            make_evidence(),
            workspace=tmp_path,
        )
        assert result.passed is False

    def test_fails_when_file_missing(self, tmp_path):
        result = check_harness_assertion(
            {"type": "file_contains", "value": "missing.py:anything"},
            make_evidence(),
            workspace=tmp_path,
        )
        assert result.passed is False


class TestSkillActivated:
    def test_passes_when_skill_tool_called(self):
        evidence = make_evidence(
            tool_calls=[
                ToolCallEvent(
                    tool_name="Skill", status="completed", arguments={"skill": "commit"}
                ),
            ]
        )
        result = check_harness_assertion(
            {"type": "skill_activated", "value": "commit"}, evidence
        )
        assert result.passed is True

    def test_fails_when_no_skill_call(self):
        evidence = make_evidence(
            tool_calls=[
                ToolCallEvent(
                    tool_name="Bash", status="completed", arguments={"command": "ls"}
                ),
            ]
        )
        result = check_harness_assertion(
            {"type": "skill_activated", "value": "commit"}, evidence
        )
        assert result.passed is False

    def test_partial_match_on_qualified_name(self):
        evidence = make_evidence(
            tool_calls=[
                ToolCallEvent(
                    tool_name="Skill",
                    status="completed",
                    arguments={"skill": "commit-commands:commit"},
                ),
            ]
        )
        result = check_harness_assertion(
            {"type": "skill_activated", "value": "commit"}, evidence
        )
        assert result.passed is True

    def test_wrong_skill_fails(self):
        evidence = make_evidence(
            tool_calls=[
                ToolCallEvent(
                    tool_name="Skill",
                    status="completed",
                    arguments={"skill": "clean-python"},
                ),
            ]
        )
        result = check_harness_assertion(
            {"type": "skill_activated", "value": "commit"}, evidence
        )
        assert result.passed is False

    def test_negate_skill_activated(self):
        evidence = make_evidence(tool_calls=[])
        result = check_harness_assertion(
            {"type": "skill_activated", "value": "commit", "negate": True}, evidence
        )
        assert result.passed is True


class TestNegate:
    def test_negate_inverts_contains(self):
        evidence = make_evidence(response_text="hello world")
        result = check_harness_assertion(
            {"type": "contains", "value": "hello", "negate": True},
            evidence,
        )
        assert result.passed is False

    def test_negate_inverts_tool_called(self):
        evidence = make_evidence(tool_calls=[])
        result = check_harness_assertion(
            {"type": "tool_called", "value": "Bash", "negate": True},
            evidence,
        )
        assert result.passed is True

    def test_negate_inverts_file_exists(self, tmp_path):
        result = check_harness_assertion(
            {"type": "file_exists", "value": "missing.txt", "negate": True},
            make_evidence(),
            workspace=tmp_path,
        )
        assert result.passed is True


class TestDelegatesToExisting:
    def test_contains_passes(self):
        evidence = make_evidence(response_text="hello world")
        result = check_harness_assertion(
            {"type": "contains", "value": "hello"}, evidence
        )
        assert result.passed is True

    def test_not_contains_passes(self):
        evidence = make_evidence(response_text="hello world")
        result = check_harness_assertion(
            {"type": "not_contains", "value": "goodbye"}, evidence
        )
        assert result.passed is True

    def test_regex_passes(self):
        evidence = make_evidence(response_text="def foo():")
        result = check_harness_assertion(
            {"type": "regex", "value": r"def \w+\("}, evidence
        )
        assert result.passed is True

    def test_unknown_type_fails(self):
        result = check_harness_assertion(
            {"type": "bogus", "value": "x"}, make_evidence()
        )
        assert result.passed is False
