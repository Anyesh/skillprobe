import pytest
from skillprobe.proxy.live_assertions import LiveAssertionEvaluator, LiveAssertionResult
from skillprobe.testing.loader import TestCase, TestSuite


def make_suite(tests: list[TestCase]) -> TestSuite:
    return TestSuite(skill=None, tests=tests, base_context="")


class TestLiveAssertionEvaluator:
    def test_passes_when_assertions_met(self):
        suite = make_suite([
            TestCase(name="has return", message="any", assertions=[{"type": "contains", "value": "return"}]),
        ])
        evaluator = LiveAssertionEvaluator(suite)
        results = evaluator.evaluate(1, "def foo():\n    return 42", "system prompt")
        assert len(results) == 1
        assert results[0].passed is True
        assert results[0].skipped is False

    def test_fails_when_assertions_not_met(self):
        suite = make_suite([
            TestCase(name="has return", message="any", assertions=[{"type": "contains", "value": "return"}]),
        ])
        evaluator = LiveAssertionEvaluator(suite)
        results = evaluator.evaluate(1, "Hello world", "")
        assert len(results) == 1
        assert results[0].passed is False
        assert len(results[0].details) == 1

    def test_skips_when_conditions_fail(self):
        suite = make_suite([
            TestCase(
                name="check functions",
                message="any",
                when=[{"type": "regex", "value": r"def \w+\("}],
                assertions=[{"type": "not_contains", "value": '"""'}],
            ),
        ])
        evaluator = LiveAssertionEvaluator(suite)
        results = evaluator.evaluate(1, "Just plain text, no code.", "")
        assert len(results) == 1
        assert results[0].skipped is True

    def test_multiple_test_cases(self):
        suite = make_suite([
            TestCase(name="t1", message="any", assertions=[{"type": "contains", "value": "hello"}]),
            TestCase(name="t2", message="any", assertions=[{"type": "contains", "value": "world"}]),
        ])
        evaluator = LiveAssertionEvaluator(suite)
        results = evaluator.evaluate(1, "hello world", "")
        assert len(results) == 2
        assert all(r.passed for r in results)

    def test_results_stored_in_log(self):
        suite = make_suite([
            TestCase(name="t1", message="any", assertions=[{"type": "contains", "value": "x"}]),
        ])
        evaluator = LiveAssertionEvaluator(suite)
        evaluator.evaluate(1, "x", "")
        evaluator.evaluate(2, "y", "")
        assert len(evaluator.log) == 2

    def test_log_bounded_at_maxlen(self):
        suite = make_suite([
            TestCase(name="t1", message="any", assertions=[{"type": "contains", "value": "x"}]),
        ])
        evaluator = LiveAssertionEvaluator(suite)
        for i in range(600):
            evaluator.evaluate(i, "x", "")
        assert len(evaluator.log) == 500

    def test_passes_parsed_data_to_assertions(self):
        suite = make_suite([
            TestCase(name="skill check", message="any", assertions=[{"type": "skill_loaded", "value": "test-skill"}]),
        ])
        evaluator = LiveAssertionEvaluator(suite)
        results = evaluator.evaluate(
            1, "response", "",
            parsed_data={"detected_skills": [{"name": "test-skill.md", "score": 0.9}]},
        )
        assert results[0].passed is True
