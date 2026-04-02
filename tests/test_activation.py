from pathlib import Path

import pytest

from skillprobe.activation import (
    ActivationResult,
    ActivationSuite,
    _find_activated_skills,
    _skill_matches,
    format_activation_results,
    load_activation_suite,
    run_activation_suite,
)
from skillprobe.adapters.base import HarnessConfig
from skillprobe.evidence import StepEvidence, ToolCallEvent


@pytest.fixture
def activation_file(tmp_path):
    content = """
harness: claude-code
model: claude-haiku-4-5-20251001
timeout: 60
skill: ./skills/commit

activation:
  skill_name: commit
  should_activate:
    - "commit my changes"
    - "save my work to git"
  should_not_activate:
    - "explain what this project does"
    - "write a hello world"
"""
    f = tmp_path / "test_activation.yaml"
    f.write_text(content)
    return f


class TestLoadActivationSuite:
    def test_loads_all_fields(self, activation_file):
        suite = load_activation_suite(activation_file)
        assert suite.harness == "claude-code"
        assert suite.model == "claude-haiku-4-5-20251001"
        assert suite.skill == "./skills/commit"
        assert suite.skill_name == "commit"
        assert len(suite.should_activate) == 2
        assert len(suite.should_not_activate) == 2

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_activation_suite(tmp_path / "nonexistent.yaml")

    def test_defaults(self, tmp_path):
        content = """
activation:
  skill_name: test
  should_activate:
    - "test prompt"
"""
        f = tmp_path / "minimal.yaml"
        f.write_text(content)
        suite = load_activation_suite(f)
        assert suite.harness == "claude-code"
        assert suite.model is None
        assert suite.timeout == 120
        assert suite.should_not_activate == []


class TestFindActivatedSkills:
    def test_finds_skill_tool_calls(self):
        evidence = StepEvidence(
            response_text="ok",
            tool_calls=[
                ToolCallEvent(
                    tool_name="Skill", status="completed", arguments={"skill": "commit"}
                ),
                ToolCallEvent(
                    tool_name="Bash",
                    status="completed",
                    arguments={"command": "git status"},
                ),
            ],
            session_id=None,
            duration_ms=0,
            cost_usd=None,
            exit_code=0,
            is_error=False,
            raw_output="",
            capture_id=None,
        )
        skills = _find_activated_skills(evidence)
        assert skills == ["commit"]

    def test_returns_empty_when_no_skill_calls(self):
        evidence = StepEvidence(
            response_text="ok",
            tool_calls=[
                ToolCallEvent(
                    tool_name="Bash", status="completed", arguments={"command": "ls"}
                ),
            ],
            session_id=None,
            duration_ms=0,
            cost_usd=None,
            exit_code=0,
            is_error=False,
            raw_output="",
            capture_id=None,
        )
        assert _find_activated_skills(evidence) == []

    def test_finds_multiple_skills(self):
        evidence = StepEvidence(
            response_text="ok",
            tool_calls=[
                ToolCallEvent(
                    tool_name="Skill", status="completed", arguments={"skill": "commit"}
                ),
                ToolCallEvent(
                    tool_name="Skill",
                    status="completed",
                    arguments={"skill": "clean-python"},
                ),
            ],
            session_id=None,
            duration_ms=0,
            cost_usd=None,
            exit_code=0,
            is_error=False,
            raw_output="",
            capture_id=None,
        )
        skills = _find_activated_skills(evidence)
        assert skills == ["commit", "clean-python"]


class TestSkillMatches:
    def test_exact_match(self):
        assert _skill_matches(["commit"], "commit") is True

    def test_partial_match(self):
        assert _skill_matches(["commit-commands:commit"], "commit") is True

    def test_no_match(self):
        assert _skill_matches(["clean-python"], "commit") is False

    def test_empty_list(self):
        assert _skill_matches([], "commit") is False

    def test_case_insensitive(self):
        assert _skill_matches(["Commit"], "commit") is True


class FakeActivationAdapter:
    def __init__(self, responses: dict[str, StepEvidence]):
        self._responses = responses
        self._default = StepEvidence(
            response_text="generic response",
            tool_calls=[],
            session_id=None,
            duration_ms=100.0,
            cost_usd=0.001,
            exit_code=0,
            is_error=False,
            raw_output="",
            capture_id=None,
        )

    def start(self, config: HarnessConfig) -> None:
        pass

    async def send_prompt(
        self, prompt: str, workspace: Path, session_id: str | None
    ) -> StepEvidence:
        return self._responses.get(prompt, self._default)

    def supported_assertions(self) -> set[str]:
        return {"contains", "tool_called", "skill_activated"}

    def stop(self) -> None:
        pass


class TestRunActivationSuite:
    @pytest.mark.asyncio
    async def test_correct_activation(self, tmp_path):
        adapter = FakeActivationAdapter(
            {
                "commit my changes": StepEvidence(
                    response_text="I'll commit",
                    tool_calls=[
                        ToolCallEvent(
                            tool_name="Skill",
                            status="completed",
                            arguments={"skill": "commit"},
                        )
                    ],
                    session_id=None,
                    duration_ms=100.0,
                    cost_usd=0.001,
                    exit_code=0,
                    is_error=False,
                    raw_output="",
                    capture_id=None,
                ),
                "explain the project": StepEvidence(
                    response_text="This project does X",
                    tool_calls=[],
                    session_id=None,
                    duration_ms=100.0,
                    cost_usd=0.001,
                    exit_code=0,
                    is_error=False,
                    raw_output="",
                    capture_id=None,
                ),
            }
        )
        suite = ActivationSuite(
            harness="claude-code",
            model="test",
            timeout=60,
            skill=None,
            skill_name="commit",
            should_activate=["commit my changes"],
            should_not_activate=["explain the project"],
        )
        config = HarnessConfig(harness="claude-code")
        results = await run_activation_suite(suite, adapter, config, tmp_path)
        assert len(results) == 2
        assert all(r.passed for r in results)

    @pytest.mark.asyncio
    async def test_skill_not_loaded_when_expected(self, tmp_path):
        adapter = FakeActivationAdapter(
            {
                "commit my changes": StepEvidence(
                    response_text="Here is some code",
                    tool_calls=[],
                    session_id=None,
                    duration_ms=100.0,
                    cost_usd=0.001,
                    exit_code=0,
                    is_error=False,
                    raw_output="",
                    capture_id=None,
                ),
            }
        )
        suite = ActivationSuite(
            harness="claude-code",
            model="test",
            timeout=60,
            skill=None,
            skill_name="commit",
            should_activate=["commit my changes"],
            should_not_activate=[],
        )
        config = HarnessConfig(harness="claude-code")
        results = await run_activation_suite(suite, adapter, config, tmp_path)
        assert results[0].passed is False
        assert results[0].expected_active is True
        assert results[0].actually_active is False

    @pytest.mark.asyncio
    async def test_unwanted_activation(self, tmp_path):
        adapter = FakeActivationAdapter(
            {
                "hello": StepEvidence(
                    response_text="I'll commit",
                    tool_calls=[
                        ToolCallEvent(
                            tool_name="Skill",
                            status="completed",
                            arguments={"skill": "commit"},
                        )
                    ],
                    session_id=None,
                    duration_ms=100.0,
                    cost_usd=0.001,
                    exit_code=0,
                    is_error=False,
                    raw_output="",
                    capture_id=None,
                ),
            }
        )
        suite = ActivationSuite(
            harness="claude-code",
            model="test",
            timeout=60,
            skill=None,
            skill_name="commit",
            should_activate=[],
            should_not_activate=["hello"],
        )
        config = HarnessConfig(harness="claude-code")
        results = await run_activation_suite(suite, adapter, config, tmp_path)
        assert results[0].passed is False
        assert results[0].expected_active is False
        assert results[0].actually_active is True


class TestFormatActivationResults:
    def test_mixed_results(self):
        results = [
            ActivationResult("commit my changes", True, True, ["commit"], 5000.0, 0.02),
            ActivationResult("hello world", False, False, [], 3000.0, 0.01),
            ActivationResult("save to git", True, False, [], 4000.0, 0.015),
        ]
        output = format_activation_results(results, "commit")
        assert "[OK]" in output
        assert "[!!]" in output
        assert "2/3 passed" in output

    def test_shows_loaded_skills(self):
        results = [
            ActivationResult(
                "commit my changes",
                True,
                True,
                ["commit-commands:commit"],
                5000.0,
                0.02,
            ),
        ]
        output = format_activation_results(results, "commit")
        assert "commit-commands:commit" in output
