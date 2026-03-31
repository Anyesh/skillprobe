import asyncio
import time
from pathlib import Path

from skillprobe.adapters.base import HarnessAdapter, HarnessConfig
from skillprobe.assertions import check_harness_assertion
from skillprobe.evidence import StepEvidence
from skillprobe.loader import Scenario, ScenarioSuite
from skillprobe.reporter import ScenarioResult, StepResult
from skillprobe.workspace import WorkspaceManager


class ScenarioOrchestrator:
    def __init__(self, adapter: HarnessAdapter, config: HarnessConfig, work_dir: Path):
        self._adapter = adapter
        self._config = config
        self._workspace_mgr = WorkspaceManager(work_dir)

    async def run(self, suite: ScenarioSuite) -> list[ScenarioResult]:
        self._adapter.start(self._config)
        semaphore = asyncio.Semaphore(self._config.parallel)

        async def run_with_semaphore(scenario: Scenario) -> ScenarioResult:
            async with semaphore:
                return await self._run_scenario(scenario, suite.skill)

        try:
            tasks = [run_with_semaphore(s) for s in suite.scenarios]
            return list(await asyncio.gather(*tasks))
        finally:
            self._adapter.stop()

    async def _run_scenario(
        self, scenario: Scenario, skill: str | None
    ) -> ScenarioResult:
        start = time.monotonic()
        fixture = Path(scenario.workspace) if scenario.workspace else None
        skill_path = Path(skill) if skill else None
        workspace = self._workspace_mgr.create(
            fixture, skill_path, self._config.harness
        )

        try:
            if scenario.setup:
                self._workspace_mgr.run_setup(workspace, scenario.setup)

            step_results = []
            step_costs = []
            session_id = None
            all_passed = True

            for i, step in enumerate(scenario.steps):
                try:
                    evidence = await self._adapter.send_prompt(
                        step.prompt, workspace, session_id
                    )
                except Exception as e:
                    duration_ms = (time.monotonic() - start) * 1000
                    return ScenarioResult(
                        scenario_name=scenario.name,
                        steps=step_results,
                        after_assertions=[],
                        passed=False,
                        duration_ms=duration_ms,
                        cost_usd=None,
                        error=str(e),
                    )

                session_id = evidence.session_id
                if evidence.cost_usd is not None:
                    step_costs.append(evidence.cost_usd)

                supported = self._adapter.supported_assertions()
                assertion_results = []
                skipped = 0

                for assertion in step.assertions:
                    atype = assertion.get("type", "")
                    if atype not in supported:
                        skipped += 1
                        continue
                    result = check_harness_assertion(
                        assertion, evidence, workspace=workspace
                    )
                    assertion_results.append(result)

                if not all(r.passed for r in assertion_results):
                    all_passed = False

                step_results.append(
                    StepResult(
                        step_index=i,
                        prompt=step.prompt,
                        assertions=assertion_results,
                        skipped_assertions=skipped,
                    )
                )

            after_results = []
            for assertion in scenario.after:
                atype = assertion.get("type", "")
                if atype not in self._adapter.supported_assertions():
                    continue
                empty_evidence = StepEvidence(
                    response_text="",
                    tool_calls=[],
                    session_id=None,
                    duration_ms=0,
                    cost_usd=None,
                    exit_code=0,
                    is_error=False,
                    raw_output="",
                    capture_id=None,
                )
                result = check_harness_assertion(
                    assertion, empty_evidence, workspace=workspace
                )
                after_results.append(result)
                if not result.passed:
                    all_passed = False

            duration_ms = (time.monotonic() - start) * 1000
            total_cost = sum(step_costs) if step_costs else None
            return ScenarioResult(
                scenario_name=scenario.name,
                steps=step_results,
                after_assertions=after_results,
                passed=all_passed,
                duration_ms=duration_ms,
                cost_usd=total_cost,
                error=None,
            )

        finally:
            self._workspace_mgr.cleanup(workspace)
