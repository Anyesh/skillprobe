import asyncio
import time
from pathlib import Path

from skillprobe import __version__ as _SKILLPROBE_VERSION
from skillprobe.adapters.base import HarnessAdapter, HarnessConfig
from skillprobe.assertions import check_harness_assertion
from skillprobe.cache import RunCache, compute_cache_key
from skillprobe.evidence import StepEvidence
from skillprobe.loader import Scenario, ScenarioSuite
from skillprobe.reporter import ScenarioResult, StepResult
from skillprobe.workspace import WorkspaceManager


class ScenarioOrchestrator:
    def __init__(
        self,
        adapter: HarnessAdapter,
        config: HarnessConfig,
        work_dir: Path,
        cache: RunCache | None = None,
    ):
        self._adapter = adapter
        self._config = config
        self._workspace_mgr = WorkspaceManager(work_dir)
        self._cache = cache

    async def _send_prompt_cached(
        self,
        prompt: str,
        workspace: Path,
        session_id: str | None,
        skills: list[str],
    ) -> tuple[StepEvidence, bool]:
        if self._cache is None:
            evidence = await self._adapter.send_prompt(prompt, workspace, session_id)
            return evidence, False

        skill_paths = [Path(s) for s in skills]
        key = compute_cache_key(
            skills=skill_paths,
            prompt=prompt,
            model=self._config.model,
            harness=self._config.harness,
            version=_SKILLPROBE_VERSION,
        )
        cached = self._cache.get(key)
        if cached is not None:
            return cached, True

        evidence = await self._adapter.send_prompt(prompt, workspace, session_id)
        if not evidence.is_error:
            self._cache.put(key, evidence)
        return evidence, False

    async def run(self, suite: ScenarioSuite) -> list[ScenarioResult]:
        self._adapter.start(self._config)
        semaphore = asyncio.Semaphore(self._config.parallel)

        async def run_with_semaphore(scenario: Scenario) -> ScenarioResult:
            async with semaphore:
                return await self._run_scenario(scenario, suite.skills)

        try:
            tasks = [run_with_semaphore(s) for s in suite.scenarios]
            return list(await asyncio.gather(*tasks))
        finally:
            self._adapter.stop()

    async def _run_scenario(
        self, scenario: Scenario, skills: list[str]
    ) -> ScenarioResult:
        start = time.monotonic()
        fixture = Path(scenario.workspace) if scenario.workspace else None
        skill_paths = [Path(s) for s in skills] if skills else None
        workspace = self._workspace_mgr.create(
            fixture, skill_paths, self._config.harness
        )

        try:
            if scenario.setup:
                self._workspace_mgr.run_setup(workspace, scenario.setup)

            step_results = []
            step_costs = []
            session_id = None
            all_passed = True

            for i, step in enumerate(scenario.steps):
                if step.runs > 1:
                    step_result = await self._run_multi(
                        step,
                        i,
                        workspace,
                        session_id,
                        step_costs,
                        skills,
                    )
                    if not step_result.meets_threshold:
                        all_passed = False
                    step_results.append(step_result)
                    continue

                try:
                    evidence, cache_hit = await self._send_prompt_cached(
                        step.prompt, workspace, session_id, skills
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
                        cache_hits=1 if cache_hit else 0,
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

    async def _run_multi(
        self,
        step: "ScenarioStep",
        step_index: int,
        workspace: Path,
        session_id: str | None,
        step_costs: list[float],
        skills: list[str],
    ) -> StepResult:
        supported = self._adapter.supported_assertions()
        passed_runs = 0
        skipped = 0
        cache_hit_count = 0
        last_assertion_results = []

        for _ in range(step.runs):
            try:
                evidence, cache_hit = await self._send_prompt_cached(
                    step.prompt, workspace, session_id, skills
                )
            except Exception:
                continue

            if cache_hit:
                cache_hit_count += 1

            if evidence.cost_usd is not None:
                step_costs.append(evidence.cost_usd)

            run_assertions = []
            for assertion in step.assertions:
                atype = assertion.get("type", "")
                if atype not in supported:
                    skipped = 1
                    continue
                result = check_harness_assertion(
                    assertion, evidence, workspace=workspace
                )
                run_assertions.append(result)

            if all(r.passed for r in run_assertions):
                passed_runs += 1
            last_assertion_results = run_assertions

        return StepResult(
            step_index=step_index,
            prompt=step.prompt,
            assertions=last_assertion_results,
            skipped_assertions=skipped,
            total_runs=step.runs,
            passed_runs=passed_runs,
            min_pass_rate=step.min_pass_rate,
            cache_hits=cache_hit_count,
        )
