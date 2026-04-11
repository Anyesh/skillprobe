import os
import subprocess
from pathlib import Path

import pytest

from skillprobe.workspace import WorkspaceManager


@pytest.fixture
def fixture_dir(tmp_path):
    fixture = tmp_path / "fixtures" / "sample-repo"
    fixture.mkdir(parents=True)
    (fixture / "README.md").write_text("# Sample")
    (fixture / "src").mkdir()
    (fixture / "src" / "main.py").write_text("print('hello')")
    env = {
        **os.environ,
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "test@test.com",
    }
    subprocess.run(["git", "init"], cwd=fixture, capture_output=True, env=env)
    subprocess.run(["git", "add", "."], cwd=fixture, capture_output=True, env=env)
    subprocess.run(
        ["git", "commit", "-m", "init", "--author", "test <test@test.com>"],
        cwd=fixture,
        capture_output=True,
        env=env,
    )
    return fixture


@pytest.fixture
def skill_dir(tmp_path):
    skill = tmp_path / "skills" / "test-skill"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: test-skill\ndescription: A test skill\n---\nDo stuff."
    )
    return skill


@pytest.fixture
def manager(tmp_path):
    return WorkspaceManager(work_dir=tmp_path / "workspaces")


class TestCreate:
    def test_copies_fixture_to_workspace(self, manager, fixture_dir):
        ws = manager.create(fixture=fixture_dir, skills=None, harness="claude-code")
        assert (ws / "README.md").exists()
        assert (ws / "src" / "main.py").read_text() == "print('hello')"

    def test_installs_skill_for_claude_code(self, manager, fixture_dir, skill_dir):
        ws = manager.create(
            fixture=fixture_dir, skills=[skill_dir], harness="claude-code"
        )
        skill_installed = ws / ".claude" / "skills" / "test-skill" / "SKILL.md"
        assert skill_installed.exists()
        assert "test skill" in skill_installed.read_text().lower()

    def test_installs_skill_for_cursor(self, manager, fixture_dir, skill_dir):
        ws = manager.create(fixture=fixture_dir, skills=[skill_dir], harness="cursor")
        skill_installed = ws / ".cursor" / "skills" / "test-skill" / "SKILL.md"
        assert skill_installed.exists()

    def test_installs_skill_from_single_file(self, manager, fixture_dir, tmp_path):
        skill_file = tmp_path / "clean-python.md"
        skill_file.write_text(
            "---\nname: clean-python\ndescription: test\n---\nBe clean."
        )
        ws = manager.create(
            fixture=fixture_dir, skills=[skill_file], harness="claude-code"
        )
        skill_installed = ws / ".claude" / "skills" / "clean-python" / "SKILL.md"
        assert skill_installed.exists()
        assert "be clean" in skill_installed.read_text().lower()

    def test_creates_workspace_without_fixture(self, manager):
        ws = manager.create(fixture=None, skills=None, harness="claude-code")
        assert ws.exists()
        assert ws.is_dir()

    def test_installs_multiple_skills(self, manager, fixture_dir, tmp_path):
        skill_a = tmp_path / "skills" / "alpha"
        skill_a.mkdir(parents=True)
        (skill_a / "SKILL.md").write_text(
            "---\nname: alpha\ndescription: alpha skill\n---\nAlpha rules."
        )
        skill_b = tmp_path / "skills" / "beta"
        skill_b.mkdir(parents=True)
        (skill_b / "SKILL.md").write_text(
            "---\nname: beta\ndescription: beta skill\n---\nBeta rules."
        )
        ws = manager.create(
            fixture=fixture_dir, skills=[skill_a, skill_b], harness="claude-code"
        )
        assert (ws / ".claude" / "skills" / "alpha" / "SKILL.md").exists()
        assert (ws / ".claude" / "skills" / "beta" / "SKILL.md").exists()

    def test_empty_skills_list_installs_nothing(self, manager, fixture_dir):
        ws = manager.create(fixture=fixture_dir, skills=[], harness="claude-code")
        assert not (ws / ".claude" / "skills").exists()


class TestSetup:
    def test_runs_setup_commands(self, manager, fixture_dir):
        ws = manager.create(fixture=fixture_dir, skills=None, harness="claude-code")
        manager.run_setup(ws, [{"run": "echo 'new content' > new_file.txt"}])
        assert (ws / "new_file.txt").exists()
        assert "new content" in (ws / "new_file.txt").read_text()

    def test_empty_setup_is_noop(self, manager, fixture_dir):
        ws = manager.create(fixture=fixture_dir, skills=None, harness="claude-code")
        manager.run_setup(ws, [])

    def test_setup_failure_raises(self, manager, fixture_dir):
        ws = manager.create(fixture=fixture_dir, skills=None, harness="claude-code")
        with pytest.raises(RuntimeError):
            manager.run_setup(ws, [{"run": "exit 1"}])


class TestCleanup:
    def test_removes_workspace(self, manager, fixture_dir):
        ws = manager.create(fixture=fixture_dir, skills=None, harness="claude-code")
        assert ws.exists()
        manager.cleanup(ws)
        assert not ws.exists()

    def test_cleanup_nonexistent_is_noop(self, manager, tmp_path):
        manager.cleanup(tmp_path / "nonexistent")
