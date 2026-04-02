from pathlib import Path

import pytest

from skillprobe.loader import (
    Scenario,
    ScenarioStep,
    ScenarioSuite,
    load_scenario_suite,
)


@pytest.fixture
def suite_file(tmp_path):
    content = """
harness: claude-code
model: claude-sonnet-4-6
timeout: 120
skill: ./skills/commit

scenarios:
  - name: "commit skill activates"
    workspace: fixtures/dirty-repo
    setup:
      - run: "echo change >> file.txt && git add ."
    steps:
      - prompt: "commit my changes"
        assert:
          - type: skill_loaded
            value: "commit"
          - type: contains
            value: "commit"
          - type: tool_called
            value: "Bash"
    after:
      - type: file_exists
        value: ".git/COMMIT_EDITMSG"

  - name: "multi-turn refinement"
    workspace: fixtures/dirty-repo
    steps:
      - prompt: "commit my changes"
        assert:
          - type: contains
            value: "commit"
      - prompt: "use conventional commits"
        assert:
          - type: regex
            value: "(feat|fix|chore)"
    timeout: 180

  - name: "negative activation"
    steps:
      - prompt: "explain the project"
        assert:
          - type: not_contains
            value: "commit"
          - type: skill_loaded
            negate: true
            value: "commit"
"""
    f = tmp_path / "test_commit.yaml"
    f.write_text(content)
    return f


class TestLoadScenarioSuite:
    def test_loads_top_level_fields(self, suite_file):
        suite = load_scenario_suite(suite_file)
        assert suite.harness == "claude-code"
        assert suite.model == "claude-sonnet-4-6"
        assert suite.timeout == 120
        assert suite.skill == "./skills/commit"
        assert len(suite.scenarios) == 3

    def test_parses_scenario_with_setup_and_after(self, suite_file):
        suite = load_scenario_suite(suite_file)
        s = suite.scenarios[0]
        assert s.name == "commit skill activates"
        assert s.workspace == "fixtures/dirty-repo"
        assert len(s.setup) == 1
        assert s.setup[0]["run"] == "echo change >> file.txt && git add ."
        assert len(s.steps) == 1
        assert s.steps[0].prompt == "commit my changes"
        assert len(s.steps[0].assertions) == 3
        assert len(s.after) == 1
        assert s.after[0]["type"] == "file_exists"

    def test_parses_multi_step_scenario(self, suite_file):
        suite = load_scenario_suite(suite_file)
        s = suite.scenarios[1]
        assert len(s.steps) == 2
        assert s.steps[1].prompt == "use conventional commits"
        assert s.timeout == 180

    def test_defaults_for_missing_fields(self, suite_file):
        suite = load_scenario_suite(suite_file)
        s = suite.scenarios[2]
        assert s.workspace is None
        assert s.setup == []
        assert s.after == []
        assert s.timeout is None

    def test_negate_flag_preserved(self, suite_file):
        suite = load_scenario_suite(suite_file)
        s = suite.scenarios[2]
        assertion = s.steps[0].assertions[1]
        assert assertion["negate"] is True

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_scenario_suite(tmp_path / "nonexistent.yaml")

    def test_defaults_when_optional_fields_omitted(self, tmp_path):
        content = """
scenarios:
  - name: "minimal"
    steps:
      - prompt: "hello"
        assert:
          - type: contains
            value: "hi"
"""
        f = tmp_path / "minimal.yaml"
        f.write_text(content)
        suite = load_scenario_suite(f)
        assert suite.harness == "claude-code"
        assert suite.model is None
        assert suite.timeout == 120
        assert suite.skill is None
        assert suite.scenarios[0].steps[0].runs == 1
        assert suite.scenarios[0].steps[0].min_pass_rate == 1.0

    def test_parses_runs_and_min_pass_rate(self, tmp_path):
        content = """
scenarios:
  - name: "multi-run"
    steps:
      - prompt: "test"
        runs: 5
        min_pass_rate: 0.8
        assert:
          - type: contains
            value: "hello"
"""
        f = tmp_path / "multi.yaml"
        f.write_text(content)
        suite = load_scenario_suite(f)
        step = suite.scenarios[0].steps[0]
        assert step.runs == 5
        assert step.min_pass_rate == 0.8
