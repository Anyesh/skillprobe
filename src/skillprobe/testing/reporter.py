from skillprobe.testing.runner import RunResult


def format_results(results: list[RunResult]) -> str:
    lines = []
    total_pass = 0
    total_fail = 0
    total_skip = 0
    for r in results:
        if r.evaluated_runs == 0:
            icon = "SKIP"
        elif r.pass_rate == 1.0:
            icon = "PASS"
        elif r.pass_rate == 0.0:
            icon = "FAIL"
        else:
            icon = "PARTIAL"

        if r.skipped_runs > 0:
            lines.append(f"  [{icon}] {r.test_name} ({r.passed_runs}/{r.evaluated_runs}, {r.pass_rate:.0%}, {r.skipped_runs} skipped)")
        else:
            lines.append(f"  [{icon}] {r.test_name} ({r.passed_runs}/{r.total_runs}, {r.pass_rate:.0%})")

        if r.pass_rate < 1.0 and r.evaluated_runs > 0:
            for run_idx, run_assertions in enumerate(r.assertion_results):
                failed = [a for a in run_assertions if not a.passed]
                if failed:
                    for a in failed:
                        lines.append(f"         run {run_idx + 1}: {a.details}")
        total_pass += r.passed_runs
        total_fail += r.failed_runs
        total_skip += r.skipped_runs
    total_evaluated = total_pass + total_fail
    overall = total_pass / total_evaluated if total_evaluated > 0 else 0
    lines.append("")
    lines.append(f"  Overall: {total_pass}/{total_evaluated} passed ({overall:.0%}), {total_skip} skipped")
    return "\n".join(lines)
