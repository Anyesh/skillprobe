from pathlib import Path

from skillprobe.optimization.analyzer import FailurePattern
from skillprobe.optimization.mutations import (
    Mutation,
    apply_mutation,
    revert_mutation,
    suggest_mutations,
)


class TestSuggestMutations:
    def test_not_contains_failure_suggests_negative_example(self):
        failures = [FailurePattern(
            test_name="no docstrings", assertion_type="not_contains",
            assertion_value='"""', failure_rate=0.5, evaluated_count=10,
            sample_failures=["found in response"],
        )]
        mutations = suggest_mutations("Some skill content", failures)
        assert len(mutations) >= 1
        assert mutations[0].operator == "add_negative_example"
        assert '"""' in mutations[0].addition

    def test_regex_failure_suggests_constraint(self):
        failures = [FailurePattern(
            test_name="type hints", assertion_type="regex",
            assertion_value="-> ", failure_rate=0.6, evaluated_count=10,
            sample_failures=[],
        )]
        mutations = suggest_mutations("content", failures)
        assert len(mutations) >= 1
        assert mutations[0].operator == "add_constraint"

    def test_contains_failure_suggests_constraint(self):
        failures = [FailurePattern(
            test_name="has return", assertion_type="contains",
            assertion_value="return", failure_rate=0.3, evaluated_count=10,
            sample_failures=[],
        )]
        mutations = suggest_mutations("content", failures)
        assert any(m.operator == "add_constraint" for m in mutations)

    def test_deduplicates_mutations(self):
        failures = [
            FailurePattern("t1", "not_contains", "foo", 0.5, 10, []),
            FailurePattern("t2", "not_contains", "foo", 0.3, 10, []),
        ]
        mutations = suggest_mutations("content", failures)
        additions = [m.addition for m in mutations]
        assert len(additions) == len(set(additions))


class TestApplyMutation:
    def test_applies_mutation_to_skill(self, tmp_path):
        skill = tmp_path / "test.md"
        skill.write_text("---\ndescription: test\n---\nOriginal content.")
        mutation = Mutation("add_constraint", "test", "- New rule here.")
        apply_mutation(skill, mutation)
        content = skill.read_text()
        assert "- New rule here." in content
        assert "Original content." in content

    def test_creates_backup(self, tmp_path):
        skill = tmp_path / "test.md"
        skill.write_text("Original content.")
        mutation = Mutation("add_constraint", "test", "- New rule.")
        apply_mutation(skill, mutation)
        backup = tmp_path / "test.md.bak"
        assert backup.exists()
        assert backup.read_text() == "Original content."

    def test_inserts_after_frontmatter(self, tmp_path):
        skill = tmp_path / "test.md"
        skill.write_text("---\ndescription: test\n---\nBody content.")
        mutation = Mutation("add_constraint", "test", "- New rule.")
        apply_mutation(skill, mutation)
        lines = skill.read_text().split("\n")
        frontmatter_end = None
        for i, line in enumerate(lines):
            if i > 0 and line.strip() == "---":
                frontmatter_end = i
                break
        assert lines[frontmatter_end + 1] == "- New rule."


class TestRevertMutation:
    def test_reverts_to_backup(self, tmp_path):
        skill = tmp_path / "test.md"
        skill.write_text("Modified content.")
        backup = tmp_path / "test.md.bak"
        backup.write_text("Original content.")
        assert revert_mutation(skill) is True
        assert skill.read_text() == "Original content."
        assert not backup.exists()

    def test_returns_false_when_no_backup(self, tmp_path):
        skill = tmp_path / "test.md"
        skill.write_text("Content.")
        assert revert_mutation(skill) is False
