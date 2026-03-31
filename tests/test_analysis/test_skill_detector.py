from pathlib import Path

import pytest

from skillprobe.analysis.skill_detector import SkillDetector


@pytest.fixture
def skill_dir(tmp_path):
    skill1 = tmp_path / "secure-code.md"
    skill1.write_text(
        "---\ndescription: Security review skill\n---\n"
        "Always check for SQL injection and XSS."
    )
    skill2 = tmp_path / "code-style.md"
    skill2.write_text(
        "---\ndescription: Code style enforcement\n---\n"
        "Use snake_case for Python."
    )
    subdir = tmp_path / "nested"
    subdir.mkdir()
    skill3 = subdir / "review.md"
    skill3.write_text("Review all pull requests carefully.")
    return tmp_path


class TestSkillDetectorLoad:
    def test_loads_skills_from_directory(self, skill_dir):
        detector = SkillDetector([skill_dir])
        assert len(detector.skills) == 3

    def test_loads_skill_content(self, skill_dir):
        detector = SkillDetector([skill_dir])
        names = {s.name for s in detector.skills}
        assert "secure-code.md" in names

    def test_empty_directory(self, tmp_path):
        detector = SkillDetector([tmp_path])
        assert len(detector.skills) == 0


class TestSkillDetectorMatch:
    def test_detects_skill_in_system_prompt(self, skill_dir):
        detector = SkillDetector([skill_dir])
        system_prompt = (
            "You are a coding assistant.\n\n"
            "Always check for SQL injection and XSS.\n\n"
            "Use snake_case for Python."
        )
        matches = detector.detect(system_prompt)
        matched_names = {m.name for m in matches}
        assert "secure-code.md" in matched_names
        assert "code-style.md" in matched_names

    def test_no_match_when_skill_absent(self, skill_dir):
        detector = SkillDetector([skill_dir])
        system_prompt = "You are a general assistant. Be helpful."
        matches = detector.detect(system_prompt)
        assert len(matches) == 0

    def test_partial_match_with_score(self, skill_dir):
        detector = SkillDetector([skill_dir])
        system_prompt = "Always check for SQL injection."
        matches = detector.detect(system_prompt)
        assert any(m.name == "secure-code.md" for m in matches)
