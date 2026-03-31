from dataclasses import dataclass

from skillprobe.harness.assertions import HarnessAssertionResult


@dataclass
class StepResult:
    step_index: int
    prompt: str
    assertions: list[HarnessAssertionResult]
    skipped_assertions: int


@dataclass
class ScenarioResult:
    scenario_name: str
    steps: list[StepResult]
    after_assertions: list[HarnessAssertionResult]
    passed: bool
    duration_ms: float
    cost_usd: float | None
    error: str | None


def format_harness_results(results: list[ScenarioResult]) -> str:
    lines = []
    total_pass = 0
    total_fail = 0
    total_cost = 0.0
    total_duration = 0.0
    total_skipped = 0
    has_cost = False

    for r in results:
        total_duration += r.duration_ms
        if r.cost_usd is not None:
            total_cost += r.cost_usd
            has_cost = True

        if r.error:
            lines.append(f"  [ERROR] {r.scenario_name}")
            lines.append(f"          {r.error}")
            total_fail += 1
            continue

        icon = "PASS" if r.passed else "FAIL"
        dur = f"{r.duration_ms / 1000:.1f}s"
        cost_str = f" ${r.cost_usd:.4f}" if r.cost_usd is not None else ""
        lines.append(f"  [{icon}] {r.scenario_name} ({dur}{cost_str})")

        if r.passed:
            total_pass += 1
        else:
            total_fail += 1

        for step in r.steps:
            failed = [a for a in step.assertions if not a.passed]
            if failed:
                lines.append(
                    f'         step {step.step_index + 1}: "{step.prompt[:50]}"'
                )
                for a in failed:
                    lines.append(f"           {a.details}")
            if step.skipped_assertions > 0:
                total_skipped += step.skipped_assertions

        failed_after = [a for a in r.after_assertions if not a.passed]
        for a in failed_after:
            lines.append(f"         after: {a.details}")

    lines.append("")
    total = total_pass + total_fail
    lines.append(f"  {total_pass}/{total} passed ({total_duration / 1000:.1f}s)")
    if has_cost:
        lines.append(f"  Total cost: ${total_cost:.2f}")
    if total_skipped > 0:
        lines.append(
            f"  {total_skipped} assertions skipped (unsupported on this harness)"
        )

    return "\n".join(lines)
