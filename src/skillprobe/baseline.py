from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from skillprobe.adapters.base import HarnessAdapter, HarnessConfig
from skillprobe.assertions import check_harness_assertion
from skillprobe.measure import wilson_confidence_interval
from skillprobe.workspace import WorkspaceManager


class BaselineClassification(Enum):
    OK = "ok"
    REGRESSION = "regression"
    SHARED_FAILURE = "shared_failure"
    FLAKY = "flaky"


@dataclass
class AssertionBaseline:
    assertion_index: int
    assertion_type: str
    assertion_value: str
    solo_a_passed: int
    solo_b_passed: int
    combined_passed: int
    total_runs: int
    solo_a_skills_activated: list[str] = field(default_factory=list)
    solo_b_skills_activated: list[str] = field(default_factory=list)
    combined_skills_activated: list[str] = field(default_factory=list)


@dataclass
class ScenarioBaseline:
    scenario_name: str
    prompt: str
    pairing_label: str
    per_assertion: list[AssertionBaseline]
    total_cost_usd: float | None = None


def classify_baseline(
    assertion: AssertionBaseline, margin: float
) -> BaselineClassification:
    total = assertion.total_runs
    if total == 0:
        return BaselineClassification.OK

    solo_a_rate = assertion.solo_a_passed / total
    solo_b_rate = assertion.solo_b_passed / total
    combined_rate = assertion.combined_passed / total

    if solo_a_rate < 0.5 and solo_b_rate < 0.5:
        return BaselineClassification.SHARED_FAILURE

    min_solo_rate = min(solo_a_rate, solo_b_rate)
    raw_drop = min_solo_rate - combined_rate

    comb_lo, comb_hi = wilson_confidence_interval(assertion.combined_passed, total)
    ci_half = (comb_hi - comb_lo) / 2

    if raw_drop - margin > ci_half:
        return BaselineClassification.REGRESSION

    if combined_rate < min_solo_rate:
        return BaselineClassification.FLAKY

    return BaselineClassification.OK


async def _run_scenario_n_times(
    adapter: HarnessAdapter,
    workspace_mgr: WorkspaceManager,
    scenario,
    skills: list[str],
    harness: str,
    runs: int,
) -> tuple[list[dict[str, int]], float]:
    skills_paths = [Path(s) for s in skills] if skills else None
    workspace = workspace_mgr.create(
        fixture=Path(scenario.workspace) if scenario.workspace else None,
        skills=skills_paths,
        harness=harness,
    )
    try:
        if scenario.setup:
            workspace_mgr.run_setup(workspace, scenario.setup)
        supported = adapter.supported_assertions()
        step = scenario.steps[0]
        counts: list[dict[str, int]] = [
            {"passed": 0, "total": 0} for _ in step.assertions
        ]
        cost_total = 0.0
        for _ in range(runs):
            evidence = await adapter.send_prompt(step.prompt, workspace, None)
            if evidence.cost_usd is not None:
                cost_total += evidence.cost_usd
            for i, assertion in enumerate(step.assertions):
                atype = assertion.get("type", "")
                if atype not in supported:
                    continue
                result = check_harness_assertion(
                    assertion, evidence, workspace=workspace
                )
                counts[i]["total"] += 1
                if result.passed:
                    counts[i]["passed"] += 1
        return counts, cost_total
    finally:
        workspace_mgr.cleanup(workspace)


async def run_baseline_pairing(
    suite: "ScenarioSuite",
    adapter: HarnessAdapter,
    config: HarnessConfig,
    base_skill: str,
    paired_skill: str,
    pairing_label: str,
    runs: int,
    work_dir: Path,
) -> list[ScenarioBaseline]:
    adapter.start(config)
    workspace_mgr = WorkspaceManager(work_dir)
    results: list[ScenarioBaseline] = []
    try:
        for scenario in suite.scenarios:
            if not scenario.steps:
                continue
            if hasattr(adapter, "set_mode"):
                adapter.set_mode("a")
            solo_a_counts, solo_a_cost = await _run_scenario_n_times(
                adapter, workspace_mgr, scenario, [base_skill], config.harness, runs
            )
            if hasattr(adapter, "set_mode"):
                adapter.set_mode("b")
            solo_b_counts, solo_b_cost = await _run_scenario_n_times(
                adapter,
                workspace_mgr,
                scenario,
                [paired_skill],
                config.harness,
                runs,
            )
            if hasattr(adapter, "set_mode"):
                adapter.set_mode("combined")
            combined_counts, combined_cost = await _run_scenario_n_times(
                adapter,
                workspace_mgr,
                scenario,
                [base_skill, paired_skill],
                config.harness,
                runs,
            )
            total_cost = solo_a_cost + solo_b_cost + combined_cost
            cost_reportable = total_cost if total_cost > 0 else None

            step = scenario.steps[0]
            per_assertion = []
            for i, assertion in enumerate(step.assertions):
                per_assertion.append(
                    AssertionBaseline(
                        assertion_index=i,
                        assertion_type=assertion.get("type", ""),
                        assertion_value=str(assertion.get("value", "")),
                        solo_a_passed=solo_a_counts[i]["passed"],
                        solo_b_passed=solo_b_counts[i]["passed"],
                        combined_passed=combined_counts[i]["passed"],
                        total_runs=runs,
                    )
                )
            results.append(
                ScenarioBaseline(
                    scenario_name=scenario.name,
                    prompt=step.prompt,
                    pairing_label=pairing_label,
                    per_assertion=per_assertion,
                    total_cost_usd=cost_reportable,
                )
            )
    finally:
        adapter.stop()
    return results
