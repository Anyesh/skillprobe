import math
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from skillprobe.adapters.base import HarnessAdapter, HarnessConfig
from skillprobe.assertions import check_harness_assertion
from skillprobe.loader import ScenarioSuite
from skillprobe.workspace import WorkspaceManager


class VarianceClass(Enum):
    DETERMINISTIC = "deterministic"
    PROBABILISTIC = "probabilistic"
    NOISY = "noisy"
    UNRELIABLE = "unreliable"


def classify_pass_rate(pass_rate: float) -> VarianceClass:
    if pass_rate >= 0.95:
        return VarianceClass.DETERMINISTIC
    if pass_rate >= 0.70:
        return VarianceClass.PROBABILISTIC
    if pass_rate >= 0.30:
        return VarianceClass.NOISY
    return VarianceClass.UNRELIABLE


def wilson_confidence_interval(
    passed: int, total: int, z: float = 1.96
) -> tuple[float, float]:
    if total == 0:
        return (0.0, 1.0)
    p_hat = passed / total
    denom = 1 + (z * z / total)
    center = (p_hat + (z * z / (2 * total))) / denom
    margin = (
        z * math.sqrt((p_hat * (1 - p_hat) / total) + (z * z / (4 * total * total)))
    ) / denom
    lo = max(0.0, center - margin)
    hi = min(1.0, center + margin)
    if passed == 0:
        lo = 0.0
    if passed == total:
        hi = 1.0
    return (lo, hi)


@dataclass
class AssertionVariance:
    assertion_index: int
    assertion_type: str
    assertion_value: str
    passed: int
    total: int
    pass_rate: float
    ci_low: float
    ci_high: float
    classification: VarianceClass


@dataclass
class ScenarioVariance:
    scenario_name: str
    prompt: str
    total_runs: int
    per_assertion: list[AssertionVariance]
    total_cost_usd: float | None


async def measure_suite(
    suite: ScenarioSuite,
    adapter: HarnessAdapter,
    config: HarnessConfig,
    runs: int,
    work_dir: Path,
) -> list[ScenarioVariance]:
    adapter.start(config)
    workspace_mgr = WorkspaceManager(work_dir)
    results: list[ScenarioVariance] = []
    try:
        for scenario in suite.scenarios:
            if not scenario.steps:
                continue
            step = scenario.steps[0]
            skills_paths = [Path(s) for s in suite.skills] if suite.skills else None
            workspace = workspace_mgr.create(
                fixture=Path(scenario.workspace) if scenario.workspace else None,
                skills=skills_paths,
                harness=config.harness,
            )
            try:
                if scenario.setup:
                    workspace_mgr.run_setup(workspace, scenario.setup)
                supported = adapter.supported_assertions()
                per_assertion_counts = [
                    {"passed": 0, "total": 0} for _ in step.assertions
                ]
                total_cost = 0.0
                any_cost = False
                for _ in range(runs):
                    evidence = await adapter.send_prompt(step.prompt, workspace, None)
                    if evidence.cost_usd is not None:
                        total_cost += evidence.cost_usd
                        any_cost = True
                    for i, assertion in enumerate(step.assertions):
                        atype = assertion.get("type", "")
                        if atype not in supported:
                            continue
                        result = check_harness_assertion(
                            assertion, evidence, workspace=workspace
                        )
                        per_assertion_counts[i]["total"] += 1
                        if result.passed:
                            per_assertion_counts[i]["passed"] += 1
                per_assertion = []
                for i, counts in enumerate(per_assertion_counts):
                    if counts["total"] == 0:
                        continue
                    pass_rate = counts["passed"] / counts["total"]
                    lo, hi = wilson_confidence_interval(
                        counts["passed"], counts["total"]
                    )
                    assertion = step.assertions[i]
                    per_assertion.append(
                        AssertionVariance(
                            assertion_index=i,
                            assertion_type=assertion.get("type", ""),
                            assertion_value=str(assertion.get("value", "")),
                            passed=counts["passed"],
                            total=counts["total"],
                            pass_rate=pass_rate,
                            ci_low=lo,
                            ci_high=hi,
                            classification=classify_pass_rate(pass_rate),
                        )
                    )
                results.append(
                    ScenarioVariance(
                        scenario_name=scenario.name,
                        prompt=step.prompt,
                        total_runs=runs,
                        per_assertion=per_assertion,
                        total_cost_usd=total_cost if any_cost else None,
                    )
                )
            finally:
                workspace_mgr.cleanup(workspace)
    finally:
        adapter.stop()
    return results


def format_variance_report(results: list[ScenarioVariance]) -> str:
    lines = []
    for scenario in results:
        lines.append(f"  {scenario.scenario_name}")
        lines.append(f"    prompt: {scenario.prompt[:60]}")
        lines.append(f"    runs:   {scenario.total_runs}")
        if scenario.total_cost_usd is not None:
            lines.append(f"    cost:   ${scenario.total_cost_usd:.4f}")
        for a in scenario.per_assertion:
            rate_str = f"{a.passed}/{a.total} ({a.pass_rate:.0%})"
            ci_str = f"[{a.ci_low:.2f}, {a.ci_high:.2f}]"
            cls = a.classification.value
            lines.append(
                f"    [{cls:13s}] {a.assertion_type:15s} {rate_str}  CI95 {ci_str}"
            )
        lines.append("")
    return "\n".join(lines)
