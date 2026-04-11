import pytest

from skillprobe.adapters.base import HarnessConfig
from skillprobe.cli import _expand_matrix
from skillprobe.loader import load_scenario_suite
from skillprobe.orchestrator import ScenarioOrchestrator


class FakeAdapter:
    def __init__(self, response):
        self._response = response

    def start(self, config):
        pass

    async def send_prompt(self, prompt, workspace, session_id):
        from skillprobe.evidence import StepEvidence

        return StepEvidence(
            response_text=self._response,
            tool_calls=[],
            session_id="s",
            duration_ms=10.0,
            cost_usd=0.001,
            exit_code=0,
            is_error=False,
            raw_output=self._response,
            capture_id=None,
        )

    def supported_assertions(self):
        return {"contains", "not_contains", "regex"}

    def stop(self):
        pass


@pytest.fixture
def matrix_yaml(tmp_path):
    content = """
harness: claude-code
matrix:
  base: ./skills/base
  pair_with:
    - ./skills/alpha
    - ./skills/beta
    - ./skills/gamma
scenarios:
  - name: "answers with ok"
    steps:
      - prompt: "go"
        assert:
          - type: contains
            value: "ok"
"""
    f = tmp_path / "matrix.yaml"
    f.write_text(content)
    return f


def _create_fake_skill_dirs(tmp_path):
    for name in ("base", "alpha", "beta", "gamma"):
        skill_dir = tmp_path / "skills" / name
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: fake\n---\nrule."
        )


def test_expand_matrix_produces_pair_per_entry(matrix_yaml, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _create_fake_skill_dirs(tmp_path)

    suite = load_scenario_suite(matrix_yaml)
    expanded = _expand_matrix(suite)
    assert len(expanded) == 3
    labels = [label for label, _ in expanded]
    assert "base + alpha" in labels
    assert "base + beta" in labels
    assert "base + gamma" in labels
    for _, sub in expanded:
        assert sub.matrix is None
        assert len(sub.skills) == 2
        assert sub.skills[0] == "./skills/base"


def test_expand_matrix_on_non_matrix_suite_returns_single(tmp_path):
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
    f = tmp_path / "plain.yaml"
    f.write_text(content)
    suite = load_scenario_suite(f)
    expanded = _expand_matrix(suite)
    assert len(expanded) == 1
    label, sub = expanded[0]
    assert label == ""
    assert sub is suite


@pytest.mark.asyncio
async def test_matrix_orchestrator_runs_once_per_pair(
    tmp_path, matrix_yaml, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    _create_fake_skill_dirs(tmp_path)

    suite = load_scenario_suite(matrix_yaml)
    expanded = _expand_matrix(suite)
    adapter = FakeAdapter(response="ok everyone")
    config = HarnessConfig(harness="claude-code", model="m")
    orchestrator = ScenarioOrchestrator(
        adapter=adapter, config=config, work_dir=tmp_path / "work"
    )
    total_results = []
    for label, sub in expanded:
        results = await orchestrator.run(sub)
        total_results.append((label, results))
    assert len(total_results) == 3
    for label, results in total_results:
        assert len(results) == 1
        assert results[0].passed is True
