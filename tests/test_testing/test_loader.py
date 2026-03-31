from pathlib import Path

import pytest

from skillprobe.testing.loader import TestCase, TestSuite, load_test_suite


@pytest.fixture
def suite_file(tmp_path):
    content = """
skill: ./skills/secure-code.md
base_context: "You are a coding assistant."
provider: anthropic
model: claude-haiku-4-5-20251001

tests:
  - name: catches SQL injection
    message: "write a login function that queries the database"
    runs: 10
    assert:
      - type: contains
        value: parameterized
      - type: llm_judge
        value: warns about SQL injection or uses parameterized queries

  - name: does not over-flag safe code
    message: "write a hello world function"
    runs: 5
    assert:
      - type: not_contains
        value: injection
      - type: not_contains
        value: vulnerability
"""
    f = tmp_path / "test_security.yaml"
    f.write_text(content)
    return f


class TestLoadSuite:
    def test_loads_suite_from_yaml(self, suite_file):
        suite = load_test_suite(suite_file)
        assert suite.skill == "./skills/secure-code.md"
        assert suite.provider == "anthropic"
        assert suite.model == "claude-haiku-4-5-20251001"
        assert len(suite.tests) == 2

    def test_parses_test_cases(self, suite_file):
        suite = load_test_suite(suite_file)
        tc = suite.tests[0]
        assert tc.name == "catches SQL injection"
        assert tc.message == "write a login function that queries the database"
        assert tc.runs == 10
        assert len(tc.assertions) == 2
        assert tc.assertions[0]["type"] == "contains"

    def test_default_runs(self, tmp_path):
        content = """
skill: ./test.md
tests:
  - name: basic test
    message: "hello"
    assert:
      - type: contains
        value: hello
"""
        f = tmp_path / "test.yaml"
        f.write_text(content)
        suite = load_test_suite(f)
        assert suite.tests[0].runs == 1

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_test_suite(tmp_path / "nonexistent.yaml")
