import asyncio
from pathlib import Path

import click

from skillprobe.activation import (
    format_activation_results,
    load_activation_suite,
    run_activation_suite,
)
from skillprobe.adapters import get_adapter
from skillprobe.adapters.base import HarnessConfig
from skillprobe.init_generator import generate_test_scaffold
from skillprobe.loader import load_scenario_suite
from skillprobe.orchestrator import ScenarioOrchestrator
from skillprobe.reporter import format_harness_results


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
def run(
    test_file: str,
    harness_name: str | None,
    model: str | None,
    parallel: int,
    timeout: int | None,
    max_cost: float | None,
):
    suite = load_scenario_suite(Path(test_file))
    resolved_harness = harness_name or suite.harness
    resolved_model = model or suite.model
    resolved_timeout = timeout or suite.timeout

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
    click.echo()

    orchestrator = ScenarioOrchestrator(
        adapter=adapter,
        config=config,
        work_dir=Path(".skillprobe-workspaces"),
    )
    results = asyncio.run(orchestrator.run(suite))
    click.echo(format_harness_results(results))

    any_failed = any(not r.passed for r in results)
    raise SystemExit(1 if any_failed else 0)


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
            Path(".skillprobe-workspaces"),
        )
    )
    click.echo(format_activation_results(results, skill_name))

    any_failed = any(not r.passed for r in results)
    raise SystemExit(1 if any_failed else 0)


@main.command("init")
@click.argument("skill_dir", type=click.Path(exists=True))
@click.option("--harness", "harness_name", default="claude-code", help="Target harness")
@click.option("--output", default=None, type=click.Path(), help="Output YAML path")
@click.option(
    "--provider",
    default="anthropic",
    type=click.Choice(["anthropic", "openai"]),
    help="LLM provider for generation",
)
@click.option("--model", default=None, help="Model for generation")
@click.option(
    "--anthropic-key", envvar="ANTHROPIC_API_KEY", default="", help="Anthropic API key"
)
@click.option(
    "--openai-key", envvar="OPENAI_API_KEY", default="", help="OpenAI API key"
)
@click.option("--base-url", default=None, help="Custom API base URL")
@click.option(
    "--fixtures-dir",
    default="fixtures",
    type=click.Path(),
    help="Fixture output directory",
)
def init_tests(
    skill_dir: str,
    harness_name: str,
    output: str | None,
    provider: str,
    model: str | None,
    anthropic_key: str,
    openai_key: str,
    base_url: str | None,
    fixtures_dir: str,
):
    skill_path = Path(skill_dir)
    output_path = Path(output) if output else Path(f"tests/{skill_path.name}.yaml")

    if model is None:
        model = "claude-sonnet-4-6" if provider == "anthropic" else "gpt-4o"

    click.echo(f"Generating tests for: {skill_path}")
    click.echo(f"  Harness: {harness_name}")
    click.echo(f"  Provider: {provider}")
    click.echo(f"  Model: {model}")
    click.echo()

    result = asyncio.run(
        generate_test_scaffold(
            skill_path=skill_path,
            harness=harness_name,
            model=model,
            output_path=output_path,
            fixtures_dir=Path(fixtures_dir),
            provider=provider,
            anthropic_api_key=anthropic_key,
            openai_api_key=openai_key,
            base_url=base_url,
        )
    )

    click.echo(result)
