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
        skill=None,
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
                                {"type": "skill_loaded", "value": "commit"},
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
