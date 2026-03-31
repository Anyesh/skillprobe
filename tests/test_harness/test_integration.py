from pathlib import Path

import pytest

from skillprobe.harness.adapters.base import HarnessConfig
from skillprobe.harness.evidence import StepEvidence, ToolCallEvent
from skillprobe.harness.loader import load_scenario_suite
from skillprobe.harness.orchestrator import ScenarioOrchestrator
from skillprobe.harness.reporter import format_harness_results


class FakeIntegrationAdapter:
    def __init__(self):
        self._responses = {
            "commit my changes": StepEvidence(
                response_text="I've committed your changes with message: feat: add login feature",
                tool_calls=[
                    ToolCallEvent(
                        tool_name="Bash",
                        status="completed",
                        arguments={"command": "git commit"},
                    )
                ],
                session_id="int-test-001",
                duration_ms=2500.0,
                cost_usd=0.012,
                exit_code=0,
                is_error=False,
                raw_output="{}",
                capture_id=None,
            ),
            "explain what this project does": StepEvidence(
                response_text="This project is a web application that manages user accounts.",
                tool_calls=[],
                session_id="int-test-002",
                duration_ms=1200.0,
                cost_usd=0.005,
                exit_code=0,
                is_error=False,
                raw_output="{}",
                capture_id=None,
            ),
        }
        self._default = StepEvidence(
            response_text="I can help with that.",
            tool_calls=[],
            session_id="int-default",
            duration_ms=500.0,
            cost_usd=0.002,
            exit_code=0,
            is_error=False,
            raw_output="{}",
            capture_id=None,
        )

    def start(self, config: HarnessConfig) -> None:
        pass

    async def send_prompt(
        self, prompt: str, workspace: Path, session_id: str | None
    ) -> StepEvidence:
        return self._responses.get(prompt, self._default)

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


@pytest.fixture
def scenario_file(tmp_path):
    content = """
harness: claude-code
model: test-model
timeout: 60

scenarios:
  - name: "commit skill works"
    steps:
      - prompt: "commit my changes"
        assert:
          - type: contains
            value: "committed"
          - type: tool_called
            value: "Bash"

  - name: "no commit on unrelated"
    steps:
      - prompt: "explain what this project does"
        assert:
          - type: not_contains
            value: "commit"
          - type: contains
            value: "project"
"""
    f = tmp_path / "integration_test.yaml"
    f.write_text(content)
    return f


class TestEndToEnd:
    @pytest.mark.asyncio
    async def test_full_pipeline(self, scenario_file, tmp_path):
        suite = load_scenario_suite(scenario_file)
        adapter = FakeIntegrationAdapter()
        config = HarnessConfig(harness="claude-code", parallel=1)
        orchestrator = ScenarioOrchestrator(
            adapter=adapter, config=config, work_dir=tmp_path / "work"
        )

        results = await orchestrator.run(suite)

        assert len(results) == 2
        assert results[0].passed is True
        assert results[0].scenario_name == "commit skill works"
        assert results[1].passed is True
        assert results[1].scenario_name == "no commit on unrelated"

        output = format_harness_results(results)
        assert "2/2 passed" in output
        assert "PASS" in output
