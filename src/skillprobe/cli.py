import asyncio
import json
import tempfile
from pathlib import Path

import click

from skillprobe.activation import (
    format_activation_results,
    load_activation_suite,
    run_activation_suite,
)
from skillprobe.adapters import get_adapter
from skillprobe.adapters.base import HarnessConfig
from skillprobe.cache import (
    RunCache,
    cache_disabled_from_env,
    default_cache_dir,
    ttl_hours_from_env,
)
from skillprobe.loader import ScenarioSuite, load_scenario_suite
from skillprobe.measure import format_variance_report, measure_suite
from skillprobe.orchestrator import ScenarioOrchestrator
from skillprobe.reporter import format_harness_results


def _expand_matrix(suite: ScenarioSuite) -> list[tuple[str, ScenarioSuite]]:
    if suite.matrix is None:
        return [("", suite)]

    expanded: list[tuple[str, ScenarioSuite]] = []
    for pair in suite.matrix.pair_with:
        skills = [suite.matrix.base, pair]
        label = f"{Path(suite.matrix.base).name} + {Path(pair).name}"
        expanded.append(
            (
                label,
                ScenarioSuite(
                    harness=suite.harness,
                    model=suite.model,
                    timeout=suite.timeout,
                    skills=skills,
                    scenarios=suite.scenarios,
                    matrix=None,
                ),
            )
        )
    return expanded


@click.group()
@click.version_option()
def main():
    pass


@main.command("run")
@click.argument("test_file", type=click.Path(exists=True))
@click.option(
    "--harness", "harness_name", default=None, help="Harness: claude-code or cursor"
)
@click.option("--model", default=None, help="Override model")
@click.option("--parallel", default=1, type=int, help="Concurrent scenarios")
@click.option(
    "--timeout", default=None, type=int, help="Per-scenario timeout (seconds)"
)
@click.option(
    "--max-cost", default=None, type=float, help="Max USD spend (Claude Code only)"
)
@click.option(
    "--no-cache",
    is_flag=True,
    default=False,
    help="Disable the run cache entirely for this invocation",
)
@click.option(
    "--force-refresh",
    is_flag=True,
    default=False,
    help="Bypass cache reads but still write fresh results",
)
@click.option(
    "--cache-dir",
    default=None,
    type=click.Path(),
    help="Override the cache directory",
)
def run(
    test_file: str,
    harness_name: str | None,
    model: str | None,
    parallel: int,
    timeout: int | None,
    max_cost: float | None,
    no_cache: bool,
    force_refresh: bool,
    cache_dir: str | None,
):
    suite = load_scenario_suite(Path(test_file))
    resolved_harness = harness_name or suite.harness
    resolved_model = model or suite.model
    resolved_timeout = timeout or suite.timeout

    if max_cost is not None and resolved_harness != "claude-code":
        click.echo(
            f"  warning: --max-cost is ignored for harness '{resolved_harness}'; "
            f"it is only wired up on claude-code",
            err=True,
        )
        max_cost = None

    cache_is_disabled = no_cache or cache_disabled_from_env()
    if cache_dir is not None:
        cache_path = Path(cache_dir)
    else:
        cache_path = default_cache_dir()
    cache = RunCache(
        cache_dir=cache_path,
        ttl_hours=ttl_hours_from_env(),
        disabled=cache_is_disabled,
    )
    if force_refresh and not cache_is_disabled:

        class _WriteOnlyCache(RunCache):
            def get(self, key):
                return None

        cache = _WriteOnlyCache(
            cache_dir=cache_path, ttl_hours=ttl_hours_from_env(), disabled=False
        )

    config = HarnessConfig(
        harness=resolved_harness,
        model=resolved_model,
        timeout=resolved_timeout,
        max_cost=max_cost,
        parallel=parallel,
    )

    adapter = get_adapter(resolved_harness)

    click.echo(f"Running: {test_file}")
    click.echo(f"  Harness: {resolved_harness}")
    click.echo(f"  Model: {resolved_model or 'default'}")
    click.echo(f"  Scenarios: {len(suite.scenarios)}")
    click.echo(f"  Parallel: {parallel}")
    if suite.skills:
        if len(suite.skills) == 1:
            click.echo(f"  Skill: {suite.skills[0]}")
        else:
            click.echo(f"  Skills: {len(suite.skills)} loaded")
            for s in suite.skills:
                click.echo(f"    - {s}")
    if cache_is_disabled:
        click.echo("  Cache: disabled")
    elif force_refresh:
        click.echo(f"  Cache: write-only at {cache_path}")
    else:
        click.echo(f"  Cache: {cache_path}")
    click.echo()

    orchestrator = ScenarioOrchestrator(
        adapter=adapter,
        config=config,
        work_dir=Path(tempfile.gettempdir()) / "skillprobe-workspaces",
        cache=cache,
    )
    expanded_suites = _expand_matrix(suite)

    any_failed = False

    for label, sub_suite in expanded_suites:
        if label:
            click.echo(f"  Matrix pairing: {label}")
            for s in sub_suite.skills:
                click.echo(f"    - {s}")
            click.echo()

        results = asyncio.run(orchestrator.run(sub_suite))
        click.echo(format_harness_results(results))
        if any(not r.passed for r in results):
            any_failed = True
        click.echo()

    raise SystemExit(1 if any_failed else 0)


@main.command("measure")
@click.argument("test_file", type=click.Path(exists=True))
@click.option("--runs", default=20, type=int, help="Number of runs per scenario")
@click.option(
    "--harness", "harness_name", default=None, help="Harness: claude-code or cursor"
)
@click.option("--model", default=None, help="Override model")
@click.option("--timeout", default=None, type=int, help="Per-prompt timeout (seconds)")
@click.option("--json", "as_json", is_flag=True, default=False, help="Emit JSON output")
def measure(
    test_file: str,
    runs: int,
    harness_name: str | None,
    model: str | None,
    timeout: int | None,
    as_json: bool,
):
    suite = load_scenario_suite(Path(test_file))
    resolved_harness = harness_name or suite.harness
    resolved_model = model or suite.model
    resolved_timeout = timeout or suite.timeout

    config = HarnessConfig(
        harness=resolved_harness,
        model=resolved_model,
        timeout=resolved_timeout,
    )
    adapter = get_adapter(resolved_harness)

    click.echo(f"Measuring: {test_file}")
    click.echo(f"  Harness: {resolved_harness}")
    click.echo(f"  Model: {resolved_model or 'default'}")
    click.echo(f"  Runs per scenario: {runs}")
    click.echo(f"  Scenarios: {len(suite.scenarios)}")
    click.echo()

    results = asyncio.run(
        measure_suite(
            suite=suite,
            adapter=adapter,
            config=config,
            runs=runs,
            work_dir=Path(tempfile.gettempdir()) / "skillprobe-workspaces",
        )
    )

    if as_json:
        payload = [
            {
                "scenario_name": r.scenario_name,
                "prompt": r.prompt,
                "total_runs": r.total_runs,
                "total_cost_usd": r.total_cost_usd,
                "per_assertion": [
                    {
                        "index": a.assertion_index,
                        "type": a.assertion_type,
                        "value": a.assertion_value,
                        "passed": a.passed,
                        "total": a.total,
                        "pass_rate": a.pass_rate,
                        "ci_low": a.ci_low,
                        "ci_high": a.ci_high,
                        "classification": a.classification.value,
                    }
                    for a in r.per_assertion
                ],
            }
            for r in results
        ]
        click.echo(json.dumps(payload, indent=2))
    else:
        click.echo(format_variance_report(results))


@main.command("activation")
@click.argument("test_file", type=click.Path(exists=True))
@click.option(
    "--harness", "harness_name", default=None, help="Harness: claude-code or cursor"
)
@click.option("--model", default=None, help="Override model")
@click.option("--timeout", default=None, type=int, help="Per-prompt timeout (seconds)")
def activation(
    test_file: str, harness_name: str | None, model: str | None, timeout: int | None
):
    suite = load_activation_suite(Path(test_file))
    resolved_harness = harness_name or suite.harness
    resolved_model = model or suite.model
    resolved_timeout = timeout or suite.timeout

    config = HarnessConfig(
        harness=resolved_harness,
        model=resolved_model,
        timeout=resolved_timeout,
    )

    adapter = get_adapter(resolved_harness)
    total_prompts = len(suite.should_activate) + len(suite.should_not_activate)
    skill_name = Path(suite.skill).name if suite.skill else "unknown"

    click.echo(f"Activation test: {test_file}")
    click.echo(f"  Harness: {resolved_harness}")
    click.echo(f"  Skill: {skill_name}")
    click.echo(f"  Prompts: {total_prompts}")
    click.echo()

    results = asyncio.run(
        run_activation_suite(
            suite,
            adapter,
            config,
            Path(tempfile.gettempdir()) / "skillprobe-workspaces",
        )
    )
    click.echo(format_activation_results(results, skill_name))

    any_failed = any(not r.passed for r in results)
    raise SystemExit(1 if any_failed else 0)
