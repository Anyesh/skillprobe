from pathlib import Path

import pytest

from skillprobe.adapters.base import HarnessConfig
from skillprobe.evidence import StepEvidence, ToolCallEvent
from skillprobe.loader import Scenario, ScenarioStep, ScenarioSuite
from skillprobe.orchestrator import ScenarioOrchestrator


class FakeAdapter:
    def __init__(self, responses: list[str]):
        self._responses = responses
        self._call_index = 0

    def start(self, config: HarnessConfig) -> None:
        pass

    async def send_prompt(
        self, prompt: str, workspace: Path, session_id: str | None
    ) -> StepEvidence:
        idx = self._call_index % len(self._responses)
        self._call_index += 1
        return StepEvidence(
            response_text=self._responses[idx],
            tool_calls=[],
            session_id="fake-session",
            duration_ms=100.0,
            cost_usd=0.001,
            exit_code=0,
            is_error=False,
            raw_output=self._responses[idx],
            capture_id=None,
        )

    def supported_assertions(self) -> set[str]:
        return {
            "contains",
            "not_contains",
            "regex",
            "tool_called",
            "file_exists",
            "file_contains",
        }

    def stop(self) -> None:
        pass


class FakeFailAdapter:
    def start(self, config: HarnessConfig) -> None:
        pass

    async def send_prompt(
        self, prompt: str, workspace: Path, session_id: str | None
    ) -> StepEvidence:
        raise TimeoutError("Process timed out")

    def supported_assertions(self) -> set[str]:
        return {"contains"}

    def stop(self) -> None:
        pass


def make_suite(scenarios: list[Scenario]) -> ScenarioSuite:
    return ScenarioSuite(
        harness="claude-code",
        model="test",
        timeout=120,
        skills=[],
        scenarios=scenarios,
    )


class TestOrchestrator:
    @pytest.mark.asyncio
    async def test_single_passing_scenario(self, tmp_path):
        adapter = FakeAdapter(["I committed your changes"])
        config = HarnessConfig(harness="claude-code")
        suite = make_suite(
            [
                Scenario(
                    name="commit test",
                    workspace=None,
                    setup=[],
                    steps=[
                        ScenarioStep(
                            prompt="commit",
                            assertions=[{"type": "contains", "value": "committed"}],
                        ),
                    ],
                    after=[],
                    timeout=None,
                ),
            ]
        )
        orchestrator = ScenarioOrchestrator(
            adapter=adapter, config=config, work_dir=tmp_path
        )
        results = await orchestrator.run(suite)
        assert len(results) == 1
        assert results[0].passed is True

    @pytest.mark.asyncio
    async def test_failing_assertion(self, tmp_path):
        adapter = FakeAdapter(["hello world"])
        config = HarnessConfig(harness="claude-code")
        suite = make_suite(
            [
                Scenario(
                    name="should fail",
                    workspace=None,
                    setup=[],
                    steps=[
                        ScenarioStep(
                            prompt="test",
                            assertions=[{"type": "contains", "value": "committed"}],
                        ),
                    ],
                    after=[],
                    timeout=None,
                ),
            ]
        )
        orchestrator = ScenarioOrchestrator(
            adapter=adapter, config=config, work_dir=tmp_path
        )
        results = await orchestrator.run(suite)
        assert results[0].passed is False

    @pytest.mark.asyncio
    async def test_multi_step_carries_session(self, tmp_path):
        adapter = FakeAdapter(["first response", "second response"])
        config = HarnessConfig(harness="claude-code")
        suite = make_suite(
            [
                Scenario(
                    name="multi-turn",
                    workspace=None,
                    setup=[],
                    steps=[
                        ScenarioStep(
                            prompt="step 1",
                            assertions=[{"type": "contains", "value": "first"}],
                        ),
                        ScenarioStep(
                            prompt="step 2",
                            assertions=[{"type": "contains", "value": "second"}],
                        ),
                    ],
                    after=[],
                    timeout=None,
                ),
            ]
        )
        orchestrator = ScenarioOrchestrator(
            adapter=adapter, config=config, work_dir=tmp_path
        )
        results = await orchestrator.run(suite)
        assert results[0].passed is True
        assert len(results[0].steps) == 2

    @pytest.mark.asyncio
    async def test_after_assertions(self, tmp_path):
        fixture = tmp_path / "fixture"
        fixture.mkdir()
        adapter = FakeAdapter(["done"])
        config = HarnessConfig(harness="claude-code")
        suite = make_suite(
            [
                Scenario(
                    name="after test",
                    workspace=str(fixture),
                    setup=[{"run": "touch output.txt"}],
                    steps=[
                        ScenarioStep(
                            prompt="do it",
                            assertions=[{"type": "contains", "value": "done"}],
                        ),
                    ],
                    after=[{"type": "file_exists", "value": "output.txt"}],
                    timeout=None,
                ),
            ]
        )
        orchestrator = ScenarioOrchestrator(
            adapter=adapter, config=config, work_dir=tmp_path / "work"
        )
        results = await orchestrator.run(suite)
        assert results[0].passed is True

    @pytest.mark.asyncio
    async def test_adapter_error_captured(self, tmp_path):
        adapter = FakeFailAdapter()
        config = HarnessConfig(harness="claude-code")
        suite = make_suite(
            [
                Scenario(
                    name="timeout scenario",
                    workspace=None,
                    setup=[],
                    steps=[
                        ScenarioStep(
                            prompt="test",
                            assertions=[{"type": "contains", "value": "x"}],
                        ),
                    ],
                    after=[],
                    timeout=None,
                ),
            ]
        )
        orchestrator = ScenarioOrchestrator(
            adapter=adapter, config=config, work_dir=tmp_path
        )
        results = await orchestrator.run(suite)
        assert results[0].passed is False
        assert results[0].error is not None

    @pytest.mark.asyncio
    async def test_skips_unsupported_assertions(self, tmp_path):
        adapter = FakeAdapter(["response"])
        adapter.supported_assertions = lambda: {"contains"}
        config = HarnessConfig(harness="cursor")
        suite = make_suite(
            [
                Scenario(
                    name="cursor test",
                    workspace=None,
                    setup=[],
                    steps=[
                        ScenarioStep(
                            prompt="test",
                            assertions=[
                                {"type": "contains", "value": "response"},
                                {"type": "skill_activated", "value": "commit"},
                            ],
                        ),
                    ],
                    after=[],
                    timeout=None,
                ),
            ]
        )
        orchestrator = ScenarioOrchestrator(
            adapter=adapter, config=config, work_dir=tmp_path
        )
        results = await orchestrator.run(suite)
        assert results[0].passed is True
        assert results[0].steps[0].skipped_assertions == 1

    @pytest.mark.asyncio
    async def test_multiple_scenarios_parallel(self, tmp_path):
        adapter = FakeAdapter(["committed", "hello world"])
        config = HarnessConfig(harness="claude-code", parallel=2)
        suite = make_suite(
            [
                Scenario(
                    name="passes",
                    workspace=None,
                    setup=[],
                    steps=[
                        ScenarioStep(
                            prompt="commit",
                            assertions=[{"type": "contains", "value": "committed"}],
                        ),
                    ],
                    after=[],
                    timeout=None,
                ),
                Scenario(
                    name="also passes",
                    workspace=None,
                    setup=[],
                    steps=[
                        ScenarioStep(
                            prompt="hello",
                            assertions=[{"type": "contains", "value": "hello"}],
                        ),
                    ],
                    after=[],
                    timeout=None,
                ),
            ]
        )
        orchestrator = ScenarioOrchestrator(
            adapter=adapter, config=config, work_dir=tmp_path
        )
        results = await orchestrator.run(suite)
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_multi_run_all_pass(self, tmp_path):
        adapter = FakeAdapter(["I committed your changes"])
        config = HarnessConfig(harness="claude-code")
        suite = make_suite(
            [
                Scenario(
                    name="multi-run pass",
                    workspace=None,
                    setup=[],
                    steps=[
                        ScenarioStep(
                            prompt="commit",
                            assertions=[{"type": "contains", "value": "committed"}],
                            runs=3,
                            min_pass_rate=1.0,
                        ),
                    ],
                    after=[],
                    timeout=None,
                ),
            ]
        )
        orchestrator = ScenarioOrchestrator(
            adapter=adapter, config=config, work_dir=tmp_path
        )
        results = await orchestrator.run(suite)
        assert results[0].passed is True
        assert results[0].steps[0].total_runs == 3
        assert results[0].steps[0].passed_runs == 3
        assert results[0].steps[0].pass_rate == 1.0

    @pytest.mark.asyncio
    async def test_multi_run_partial_pass_meets_threshold(self, tmp_path):
        adapter = FakeAdapter(
            ["I committed your changes", "hello world", "I committed again"]
        )
        config = HarnessConfig(harness="claude-code")
        suite = make_suite(
            [
                Scenario(
                    name="partial ok",
                    workspace=None,
                    setup=[],
                    steps=[
                        ScenarioStep(
                            prompt="commit",
                            assertions=[{"type": "contains", "value": "committed"}],
                            runs=3,
                            min_pass_rate=0.6,
                        ),
                    ],
                    after=[],
                    timeout=None,
                ),
            ]
        )
        orchestrator = ScenarioOrchestrator(
            adapter=adapter, config=config, work_dir=tmp_path
        )
        results = await orchestrator.run(suite)
        assert results[0].passed is True
        assert results[0].steps[0].passed_runs == 2
        assert results[0].steps[0].total_runs == 3
        assert results[0].steps[0].meets_threshold is True

    @pytest.mark.asyncio
    async def test_multi_run_below_threshold_fails(self, tmp_path):
        adapter = FakeAdapter(["hello world", "hello world", "I committed"])
        config = HarnessConfig(harness="claude-code")
        suite = make_suite(
            [
                Scenario(
                    name="below threshold",
                    workspace=None,
                    setup=[],
                    steps=[
                        ScenarioStep(
                            prompt="commit",
                            assertions=[{"type": "contains", "value": "committed"}],
                            runs=3,
                            min_pass_rate=0.8,
                        ),
                    ],
                    after=[],
                    timeout=None,
                ),
            ]
        )
        orchestrator = ScenarioOrchestrator(
            adapter=adapter, config=config, work_dir=tmp_path
        )
        results = await orchestrator.run(suite)
        assert results[0].passed is False
        assert results[0].steps[0].passed_runs == 1
        assert results[0].steps[0].meets_threshold is False

    @pytest.mark.asyncio
    async def test_multiple_skills_installed_in_workspace(self, tmp_path):
        skill_a = tmp_path / "skills" / "sk-a"
        skill_a.mkdir(parents=True)
        (skill_a / "SKILL.md").write_text(
            "---\nname: sk-a\ndescription: first\n---\nA."
        )
        skill_b = tmp_path / "skills" / "sk-b"
        skill_b.mkdir(parents=True)
        (skill_b / "SKILL.md").write_text(
            "---\nname: sk-b\ndescription: second\n---\nB."
        )
        skill_files_seen: list[tuple[bool, bool]] = []

        class RecordingAdapter(FakeAdapter):
            async def send_prompt(self, prompt, workspace, session_id):
                skill_files_seen.append(
                    (
                        (
                            workspace / ".claude" / "skills" / "sk-a" / "SKILL.md"
                        ).exists(),
                        (
                            workspace / ".claude" / "skills" / "sk-b" / "SKILL.md"
                        ).exists(),
                    )
                )
                return await FakeAdapter.send_prompt(
                    self, prompt, workspace, session_id
                )

        adapter = RecordingAdapter(["ok"])
        config = HarnessConfig(harness="claude-code")
        suite = ScenarioSuite(
            harness="claude-code",
            model="test",
            timeout=120,
            skills=[str(skill_a), str(skill_b)],
            scenarios=[
                Scenario(
                    name="combo",
                    workspace=None,
                    setup=[],
                    steps=[
                        ScenarioStep(
                            prompt="go",
                            assertions=[{"type": "contains", "value": "ok"}],
                        ),
                    ],
                    after=[],
                    timeout=None,
                ),
            ],
        )
        orchestrator = ScenarioOrchestrator(
            adapter=adapter, config=config, work_dir=tmp_path / "work"
        )
        await orchestrator.run(suite)
        assert len(skill_files_seen) == 1
        sk_a_present, sk_b_present = skill_files_seen[0]
        assert sk_a_present
        assert sk_b_present
