import pytest

from skillprobe.testing.assertions import check_assertion, AssertionResult


class TestContains:
    def test_passes_when_present(self):
        result = check_assertion({"type": "contains", "value": "hello"}, "hello world")
        assert result.passed is True

    def test_fails_when_absent(self):
        result = check_assertion({"type": "contains", "value": "goodbye"}, "hello world")
        assert result.passed is False

    def test_case_insensitive(self):
        result = check_assertion({"type": "contains", "value": "HELLO"}, "hello world")
        assert result.passed is True


class TestNotContains:
    def test_passes_when_absent(self):
        result = check_assertion({"type": "not_contains", "value": "error"}, "all good")
        assert result.passed is True

    def test_fails_when_present(self):
        result = check_assertion({"type": "not_contains", "value": "error"}, "there was an error")
        assert result.passed is False


class TestRegex:
    def test_passes_on_match(self):
        result = check_assertion({"type": "regex", "value": r"def \w+\("}, "def login(username):")
        assert result.passed is True

    def test_fails_on_no_match(self):
        result = check_assertion({"type": "regex", "value": r"class \w+"}, "def login():")
        assert result.passed is False


class TestSkillPresent:
    def test_passes_when_skill_in_context(self):
        result = check_assertion(
            {"type": "skill_present", "value": "secure-code"},
            "response text",
            system_prompt="## Skill: secure-code\nCheck for injections.",
        )
        assert result.passed is True

    def test_fails_when_skill_not_in_context(self):
        result = check_assertion(
            {"type": "skill_present", "value": "secure-code"},
            "response text",
            system_prompt="You are a general assistant.",
        )
        assert result.passed is False


class TestUnknownAssertion:
    def test_unknown_type_fails(self):
        result = check_assertion({"type": "nonexistent", "value": "x"}, "response")
        assert result.passed is False
        assert "unknown" in result.details.lower()


class TestWhenConditions:
    def test_empty_conditions_returns_true(self):
        from skillprobe.testing.assertions import check_when_conditions
        assert check_when_conditions([], "any text") is True

    def test_single_matching_condition(self):
        from skillprobe.testing.assertions import check_when_conditions
        assert check_when_conditions(
            [{"type": "contains", "value": "def"}],
            "def foo(): pass"
        ) is True

    def test_single_non_matching_condition(self):
        from skillprobe.testing.assertions import check_when_conditions
        assert check_when_conditions(
            [{"type": "contains", "value": "class"}],
            "def foo(): pass"
        ) is False

    def test_all_conditions_must_match(self):
        from skillprobe.testing.assertions import check_when_conditions
        assert check_when_conditions(
            [
                {"type": "contains", "value": "def"},
                {"type": "contains", "value": "return"},
            ],
            "def foo(): pass"
        ) is False

    def test_regex_in_when(self):
        from skillprobe.testing.assertions import check_when_conditions
        assert check_when_conditions(
            [{"type": "regex", "value": r"def \w+\("}],
            "def login(username):"
        ) is True
