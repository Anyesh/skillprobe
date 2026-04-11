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
          - type: skill_activated
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
          - type: skill_activated
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
        assert suite.skills == ["./skills/commit"]
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
        assert suite.skills == []
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

    def test_parses_skills_list(self, tmp_path):
        content = """
skills:
  - ./skills/commit
  - ./skills/verify
scenarios:
  - name: "combo"
    steps:
      - prompt: "go"
        assert:
          - type: contains
            value: "ok"
"""
        f = tmp_path / "combo.yaml"
        f.write_text(content)
        suite = load_scenario_suite(f)
        assert suite.skills == ["./skills/commit", "./skills/verify"]

    def test_single_skill_key_parses_to_single_element_list(self, tmp_path):
        content = """
skill: ./skills/commit
scenarios:
  - name: "legacy"
    steps:
      - prompt: "go"
        assert:
          - type: contains
            value: "ok"
"""
        f = tmp_path / "legacy.yaml"
        f.write_text(content)
        suite = load_scenario_suite(f)
        assert suite.skills == ["./skills/commit"]

    def test_both_skill_and_skills_raises(self, tmp_path):
        content = """
skill: ./skills/a
skills:
  - ./skills/b
scenarios:
  - name: "bad"
    steps:
      - prompt: "go"
        assert:
          - type: contains
            value: "ok"
"""
        f = tmp_path / "bad.yaml"
        f.write_text(content)
        with pytest.raises(ValueError, match="both 'skill' and 'skills'"):
            load_scenario_suite(f)

    def test_skills_must_be_a_list(self, tmp_path):
        content = """
skills: ./skills/not-a-list
scenarios:
  - name: "bad"
    steps:
      - prompt: "go"
        assert:
          - type: contains
            value: "ok"
"""
        f = tmp_path / "bad.yaml"
        f.write_text(content)
        with pytest.raises(ValueError, match="'skills' must be a list"):
            load_scenario_suite(f)

    def test_skill_name_collision_raises(self, tmp_path):
        content = """
skills:
  - ./first/commit
  - ./second/commit
scenarios:
  - name: "bad"
    steps:
      - prompt: "go"
        assert:
          - type: contains
            value: "ok"
"""
        f = tmp_path / "collide.yaml"
        f.write_text(content)
        with pytest.raises(ValueError, match="collision"):
            load_scenario_suite(f)

    def test_skill_name_collision_dir_vs_md_file_raises(self, tmp_path):
        content = """
skills:
  - ./skills/commit
  - ./other/commit.md
scenarios:
  - name: "bad"
    steps:
      - prompt: "go"
        assert:
          - type: contains
            value: "ok"
"""
        f = tmp_path / "collide.yaml"
        f.write_text(content)
        with pytest.raises(ValueError, match="collision"):
            load_scenario_suite(f)

    def test_unknown_assertion_type_raises(self, tmp_path):
        content = """
scenarios:
  - name: "typo scenario"
    steps:
      - prompt: "go"
        assert:
          - type: skill_loaded
            value: "commit"
"""
        f = tmp_path / "typo.yaml"
        f.write_text(content)
        with pytest.raises(ValueError, match="unknown assertion type 'skill_loaded'"):
            load_scenario_suite(f)

    def test_unknown_assertion_type_in_after_block_raises(self, tmp_path):
        content = """
scenarios:
  - name: "bad after"
    steps:
      - prompt: "go"
        assert:
          - type: contains
            value: "ok"
    after:
      - type: file_does_not_exist
        value: "x"
"""
        f = tmp_path / "bad-after.yaml"
        f.write_text(content)
        with pytest.raises(
            ValueError, match="unknown assertion type 'file_does_not_exist'"
        ):
            load_scenario_suite(f)

    def test_activation_block_in_scenario_file_raises(self, tmp_path):
        content = """
skill: ./skills/commit
activation:
  skill_name: commit
  should_activate:
    - "commit"
"""
        f = tmp_path / "wrong-format.yaml"
        f.write_text(content)
        with pytest.raises(ValueError, match="contains an 'activation:' block"):
            load_scenario_suite(f)

    def test_missing_scenarios_block_raises(self, tmp_path):
        content = """
harness: claude-code
skill: ./skills/commit
"""
        f = tmp_path / "no-scenarios.yaml"
        f.write_text(content)
        with pytest.raises(ValueError, match="missing a 'scenarios:' block"):
            load_scenario_suite(f)

    def test_parses_matrix_block(self, tmp_path):
        content = """
harness: claude-code
matrix:
  base: ./skills/commit
  pair_with:
    - ./skills/verify
    - ./skills/lint
scenarios:
  - name: "commit"
    steps:
      - prompt: "go"
        assert:
          - type: contains
            value: "ok"
"""
        f = tmp_path / "matrix.yaml"
        f.write_text(content)
        suite = load_scenario_suite(f)
        assert suite.matrix is not None
        assert suite.matrix.base == "./skills/commit"
        assert suite.matrix.pair_with == ["./skills/verify", "./skills/lint"]

    def test_matrix_requires_base(self, tmp_path):
        content = """
matrix:
  pair_with:
    - ./skills/verify
scenarios:
  - name: "bad"
    steps:
      - prompt: "go"
        assert:
          - type: contains
            value: "ok"
"""
        f = tmp_path / "bad.yaml"
        f.write_text(content)
        with pytest.raises(ValueError, match="matrix.base"):
            load_scenario_suite(f)

    def test_matrix_requires_pair_with_list(self, tmp_path):
        content = """
matrix:
  base: ./skills/commit
  pair_with: not-a-list
scenarios:
  - name: "bad"
    steps:
      - prompt: "go"
        assert:
          - type: contains
            value: "ok"
"""
        f = tmp_path / "bad.yaml"
        f.write_text(content)
        with pytest.raises(ValueError, match="matrix.pair_with"):
            load_scenario_suite(f)

    def test_matrix_and_skills_conflict(self, tmp_path):
        content = """
skills:
  - ./skills/a
matrix:
  base: ./skills/commit
  pair_with:
    - ./skills/verify
scenarios:
  - name: "bad"
    steps:
      - prompt: "go"
        assert:
          - type: contains
            value: "ok"
"""
        f = tmp_path / "bad.yaml"
        f.write_text(content)
        with pytest.raises(
            ValueError, match="cannot specify both 'skills' and 'matrix'"
        ):
            load_scenario_suite(f)

    def test_absent_matrix_is_none(self, tmp_path):
        content = """
skill: ./skills/one
scenarios:
  - name: "ok"
    steps:
      - prompt: "go"
        assert:
          - type: contains
            value: "ok"
"""
        f = tmp_path / "nomatrix.yaml"
        f.write_text(content)
        suite = load_scenario_suite(f)
        assert suite.matrix is None
