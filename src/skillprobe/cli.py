from pathlib import Path

import click

from skillprobe.config import ProxyConfig


@click.group()
@click.version_option()
def main():
    pass


@main.command()
@click.option("--host", default="127.0.0.1", help="Proxy listen host")
@click.option("--port", default=9339, type=int, help="Proxy listen port")
@click.option("--db", default="skillprobe.db", type=click.Path(), help="Database path")
@click.option(
    "--skills",
    multiple=True,
    type=click.Path(exists=True),
    help="Skill directories to monitor",
)
@click.option(
    "--watch",
    default=None,
    type=click.Path(exists=True),
    help="Test YAML file for live assertion checking",
)
@click.option("--session", default=None, help="Tag captures with session name")
def start(
    host: str,
    port: int,
    db: str,
    skills: tuple[str, ...],
    watch: str | None,
    session: str | None,
):
    from skillprobe.proxy.server import run_proxy

    config = ProxyConfig(
        host=host,
        port=port,
        db_path=Path(db),
        skill_dirs=[Path(s) for s in skills],
        watch_test_file=Path(watch) if watch else None,
        session=session,
    )
    run_proxy(config)


@main.command()
@click.option("--db", default="skillprobe.db", type=click.Path(), help="Database path")
@click.option("--limit", default=20, type=int, help="Number of captures to show")
@click.option("--provider", default=None, help="Filter by provider (anthropic/openai)")
def captures(db: str, limit: int, provider: str | None):
    from skillprobe.storage.database import Database

    database = Database(Path(db))
    database.initialize()
    results = database.list_captures(limit=limit, provider=provider)
    database.close()

    if not results:
        click.echo("No captures found.")
        return

    click.echo(
        f"{'ID':>5} {'Time':>20} {'Provider':>10} {'Model':>30} {'Status':>6} {'Duration':>10}"
    )
    click.echo("-" * 85)
    for c in results:
        model = c.request_body.get("model", "?")[:30]
        ts = c.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        dur = f"{c.duration_ms:.0f}ms" if c.duration_ms else "?"
        click.echo(
            f"{c.id:>5} {ts:>20} {c.provider:>10} {model:>30} {c.response_status or '?':>6} {dur:>10}"
        )


@main.command()
@click.argument("capture_id", type=int)
@click.option("--db", default="skillprobe.db", type=click.Path(), help="Database path")
@click.option("--full", is_flag=True, help="Show full system prompt")
@click.option(
    "--skills",
    multiple=True,
    type=click.Path(exists=True),
    help="Skill directories for detection",
)
def inspect(capture_id: int, db: str, full: bool, skills: tuple[str, ...]):
    from skillprobe.analysis.skill_detector import SkillDetector
    from skillprobe.parsers import parse_request
    from skillprobe.storage.database import Database

    database = Database(Path(db))
    database.initialize()
    capture = database.get_capture(capture_id)
    database.close()

    if not capture:
        click.echo(f"Capture {capture_id} not found.")
        return

    parsed = parse_request(capture.path, capture.request_body)
    if not parsed:
        click.echo("Could not parse this capture.")
        return

    click.echo(f"Capture #{capture_id}")
    click.echo(f"  Provider: {parsed.provider}")
    click.echo(f"  Model: {parsed.model}")
    click.echo(f"  System prompt: {len(parsed.system_prompt):,} chars")
    click.echo(f"  Sections: {len(parsed.system_sections)}")
    for s in parsed.system_sections:
        click.echo(f"    {s.title}")
    click.echo(f"  Tools: {len(parsed.tools)}")
    for t in parsed.tools:
        click.echo(f"    {t.name}: {t.description[:60]}")
    click.echo(f"  Messages: {len(parsed.messages)}")
    click.echo(f"  Stream: {parsed.stream}")

    if full:
        click.echo(f"\n--- System Prompt ---\n{parsed.system_prompt}\n--- End ---")

    if skills:
        detector = SkillDetector([Path(s) for s in skills])
        matches = detector.detect(parsed.system_prompt)
        if matches:
            click.echo(f"\nDetected skills:")
            for m in matches:
                click.echo(f"  {m.name} (score: {m.score:.0%})")
        else:
            click.echo(f"\nNo skills detected from provided directories.")


@main.command("test")
@click.argument("test_file", type=click.Path(exists=True))
@click.option("--model", default=None, help="Override model from test suite")
@click.option("--provider", default=None, help="Override provider")
@click.option(
    "--anthropic-key", envvar="ANTHROPIC_API_KEY", default="", help="Anthropic API key"
)
@click.option(
    "--openai-key", envvar="OPENAI_API_KEY", default="", help="OpenAI API key"
)
def run_tests(
    test_file: str,
    model: str | None,
    provider: str | None,
    anthropic_key: str,
    openai_key: str,
):
    import asyncio

    from skillprobe.testing.llm_client import HttpLLMClient
    from skillprobe.testing.loader import load_test_suite
    from skillprobe.testing.reporter import format_results
    from skillprobe.testing.runner import TestRunner

    suite = load_test_suite(Path(test_file))
    if model:
        suite.model = model
    if provider:
        suite.provider = provider

    client = HttpLLMClient(
        anthropic_api_key=anthropic_key,
        openai_api_key=openai_key,
    )
    runner = TestRunner(client)

    click.echo(f"Running: {test_file}")
    click.echo(f"  Model: {suite.model}")
    click.echo(f"  Provider: {suite.provider}")
    click.echo(f"  Tests: {len(suite.tests)}")
    click.echo()

    results = asyncio.run(runner.run_suite(suite))
    click.echo(format_results(results))

    asyncio.run(client.close())
    any_failed = any(r.pass_rate < 1.0 for r in results)
    raise SystemExit(1 if any_failed else 0)


@main.command("assert")
@click.argument("test_file", type=click.Path(exists=True))
@click.option("--db", default="skillprobe.db", type=click.Path(), help="Database path")
@click.option(
    "--capture",
    "capture_ids",
    multiple=True,
    type=int,
    help="Specific capture IDs to check",
)
@click.option("--last", default=None, type=int, help="Check last N captures")
def assert_captures(
    test_file: str, db: str, capture_ids: tuple[int, ...], last: int | None
):
    from skillprobe.parsers import parse_request
    from skillprobe.proxy.handler import _extract_response_text
    from skillprobe.storage.database import Database
    from skillprobe.testing.assertions import check_assertion, check_when_conditions
    from skillprobe.testing.loader import load_test_suite

    suite = load_test_suite(Path(test_file))
    database = Database(Path(db))
    database.initialize()

    if capture_ids:
        captures = [database.get_capture(cid) for cid in capture_ids]
        captures = [c for c in captures if c is not None]
    else:
        captures = database.list_captures(limit=last or 20)
    database.close()

    if not captures:
        click.echo("No captures found.")
        return

    captures_with_response = [c for c in captures if c.response_body]
    if not captures_with_response:
        click.echo(f"Found {len(captures)} captures but none have response bodies.")
        click.echo("Make sure streaming support is enabled (restart proxy).")
        return

    click.echo(
        f"Checking {len(captures_with_response)} captures against {len(suite.tests)} test cases\n"
    )

    for c in captures_with_response:
        parsed = parse_request(c.path, c.request_body)
        system_prompt = parsed.system_prompt if parsed else ""
        provider = parsed.provider if parsed else c.provider
        response_text = _extract_response_text(c.response_body, provider)
        if not response_text:
            continue

        user_msg = _last_user_message(c.request_body)
        click.echo(
            f'  Capture #{c.id} - "{user_msg[:60]}{"..." if len(user_msg) > 60 else ""}"'
        )

        if c.parsed_data and c.parsed_data.get("detected_skills"):
            skills = c.parsed_data["detected_skills"]
            skill_str = ", ".join(f"{s['name']}({s['score']:.0%})" for s in skills)
            click.echo(f"    Skills detected: {skill_str}")

        for tc in suite.tests:
            if not check_when_conditions(tc.when, response_text, system_prompt):
                click.echo(f"    [SKIP] {tc.name}")
                continue
            results = [
                check_assertion(
                    a, response_text, system_prompt, parsed_data=c.parsed_data
                )
                for a in tc.assertions
            ]
            all_passed = all(r.passed for r in results)
            icon = "PASS" if all_passed else "FAIL"
            click.echo(f"    [{icon}] {tc.name}")
            if not all_passed:
                for r in results:
                    if not r.passed:
                        click.echo(f"           {r.details}")
        click.echo()


def _last_user_message(request_body: dict) -> str:
    for msg in reversed(request_body.get("messages", [])):
        if msg.get("role") != "user":
            continue
        content = msg.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    return block["text"]
    return "(no user message)"


@main.command()
@click.option("--db", default="skillprobe.db", type=click.Path(), help="Database path")
@click.option(
    "--skills", multiple=True, type=click.Path(exists=True), help="Skill directories"
)
@click.option("--last", default=50, type=int, help="Analyze last N captures")
def report(db: str, skills: tuple[str, ...], last: int):
    from collections import Counter

    from skillprobe.analysis.skill_detector import SkillDetector
    from skillprobe.analysis.token_counter import TokenCounter
    from skillprobe.parsers import parse_request
    from skillprobe.storage.database import Database

    database = Database(Path(db))
    database.initialize()
    captures = database.list_captures(limit=last)
    database.close()

    if not captures:
        click.echo("No captures to analyze.")
        return

    click.echo(f"Analyzing {len(captures)} captures...\n")

    model_counts: Counter[str] = Counter()
    provider_counts: Counter[str] = Counter()
    total_system_tokens = 0
    counter = TokenCounter()
    skill_hits: Counter[str] = Counter()

    detector = SkillDetector([Path(s) for s in skills]) if skills else None

    for c in captures:
        parsed = parse_request(c.path, c.request_body)
        if not parsed:
            continue
        model_counts[parsed.model] += 1
        provider_counts[parsed.provider] += 1
        tc = counter.count_system(parsed.system_prompt)
        total_system_tokens += tc.total

        if detector:
            matches = detector.detect(parsed.system_prompt)
            for m in matches:
                skill_hits[m.name] += 1

    click.echo("Provider breakdown:")
    for prov, count in provider_counts.most_common():
        click.echo(f"  {prov}: {count}")

    click.echo("\nModel breakdown:")
    for model, count in model_counts.most_common():
        click.echo(f"  {model}: {count}")

    avg_tokens = total_system_tokens // len(captures) if captures else 0
    click.echo(f"\nAvg system prompt tokens: {avg_tokens:,}")

    if skill_hits:
        click.echo("\nSkill activation frequency:")
        for name, count in skill_hits.most_common():
            click.echo(
                f"  {name}: {count}/{len(captures)} ({count / len(captures):.0%})"
            )


@main.command()
@click.argument("test_file", type=click.Path(exists=True))
@click.option(
    "--session", "sessions", multiple=True, required=True, help="Sessions to compare"
)
@click.option("--db", default="skillprobe.db", type=click.Path(), help="Database path")
def diff(test_file: str, sessions: tuple[str, ...], db: str):
    from skillprobe.storage.database import Database
    from skillprobe.testing.diff import compute_session_results, format_diff
    from skillprobe.testing.loader import load_test_suite

    suite = load_test_suite(Path(test_file))
    database = Database(Path(db))
    database.initialize()

    results = []
    for session_name in sessions:
        captures = database.list_captures_by_session(session_name)
        if not captures:
            click.echo(f"No captures found for session '{session_name}'.")
            continue
        result = compute_session_results(captures, suite)
        results.append(result)
    database.close()

    if len(results) < 2:
        click.echo("Need at least 2 sessions with captures to diff.")
        return

    click.echo(format_diff(results))


@main.command()
@click.argument("test_file", type=click.Path(exists=True))
@click.option("--db", default="skillprobe.db", type=click.Path(), help="Database path")
@click.option("--session", default=None, help="Analyze specific session")
@click.option("--last", default=50, type=int, help="Analyze last N captures")
def analyze(test_file: str, db: str, session: str | None, last: int):
    from skillprobe.optimization.analyzer import analyze_failures
    from skillprobe.optimization.mutations import suggest_mutations
    from skillprobe.storage.database import Database
    from skillprobe.testing.loader import load_test_suite

    suite = load_test_suite(Path(test_file))
    database = Database(Path(db))
    database.initialize()
    if session:
        captures = database.list_captures_by_session(session)
    else:
        captures = database.list_captures(limit=last)
    database.close()

    if not captures:
        click.echo("No captures to analyze.")
        return

    failures = analyze_failures(captures, suite)
    if not failures:
        click.echo(f"All assertions passing across {len(captures)} captures.")
        return

    click.echo(f"Failure Analysis ({len(captures)} captures)\n")
    for f in failures:
        passed = int(f.evaluated_count * (1 - f.failure_rate))
        click.echo(
            f'  "{f.test_name}" -- {f.failure_rate:.0%} failure rate ({passed}/{f.evaluated_count} passed)'
        )
        click.echo(f"    Assertion: {f.assertion_type} '{f.assertion_value}'")
        for sample in f.sample_failures[:2]:
            click.echo(f"    Example: {sample}")

    skill_path = suite.skill
    if skill_path and Path(skill_path).exists():
        skill_content = Path(skill_path).read_text(encoding="utf-8")
        mutations = suggest_mutations(skill_content, failures)
        if mutations:
            click.echo(f"\nSuggested mutations:")
            for i, m in enumerate(mutations, 1):
                click.echo(f"  {i}. [{m.operator}] {m.description}")
                click.echo(f"     Add: {m.addition}")


@main.command()
@click.argument("skill_file", type=click.Path(exists=True))
@click.option(
    "--mutation",
    required=True,
    help="Mutation operator to apply (add_constraint, add_negative_example, etc.)",
)
@click.option(
    "--test",
    "test_file",
    required=True,
    type=click.Path(exists=True),
    help="Test YAML for failure analysis",
)
@click.option("--db", default="skillprobe.db", type=click.Path(), help="Database path")
@click.option("--session", default=None, help="Session to analyze")
@click.option("--last", default=50, type=int, help="Last N captures")
@click.option("--revert", is_flag=True, help="Revert last mutation")
def optimize(
    skill_file: str,
    mutation: str,
    test_file: str,
    db: str,
    session: str | None,
    last: int,
    revert: bool,
):
    from skillprobe.optimization.analyzer import analyze_failures
    from skillprobe.optimization.mutations import (
        apply_mutation,
        revert_mutation,
        suggest_mutations,
    )
    from skillprobe.storage.database import Database
    from skillprobe.testing.loader import load_test_suite

    skill_path = Path(skill_file)

    if revert:
        if revert_mutation(skill_path):
            click.echo(f"Reverted {skill_path} to previous version.")
        else:
            click.echo(f"No backup found for {skill_path}.")
        return

    suite = load_test_suite(Path(test_file))
    database = Database(Path(db))
    database.initialize()
    if session:
        captures = database.list_captures_by_session(session)
    else:
        captures = database.list_captures(limit=last)
    database.close()

    failures = analyze_failures(captures, suite)
    mutations = suggest_mutations(skill_path.read_text(encoding="utf-8"), failures)

    target = None
    for m in mutations:
        if m.operator == mutation:
            target = m
            break

    if not target:
        click.echo(f"No '{mutation}' mutation suggested for current failures.")
        click.echo(f"Available: {', '.join(m.operator for m in mutations)}")
        return

    click.echo(f"Applying [{target.operator}]: {target.description}")
    click.echo(f"  Adding: {target.addition}")
    apply_mutation(skill_path, target)
    click.echo(f"\nSkill updated. Backup saved as {skill_path.with_suffix('.md.bak')}")
    click.echo(f"Re-test with a new session to compare.")


@main.command()
@click.argument("test_file", type=click.Path(exists=True))
@click.option("--db", default="skillprobe.db", type=click.Path(), help="Database path")
@click.option("--session", default=None, help="Check specific session")
@click.option("--last", default=50, type=int, help="Check last N captures")
def activation(test_file: str, db: str, session: str | None, last: int):
    from skillprobe.storage.database import Database
    from skillprobe.testing.activation import (
        check_activations,
        format_activation_results,
        load_activation_tests,
    )

    cases = load_activation_tests(Path(test_file))
    database = Database(Path(db))
    database.initialize()
    if session:
        captures = database.list_captures_by_session(session)
    else:
        captures = database.list_captures(limit=last)
    database.close()

    if not captures:
        click.echo("No captures to check.")
        return

    click.echo(
        f"Checking {len(cases)} skill activations against {len(captures)} captures\n"
    )
    results = check_activations(cases, captures)
    click.echo(format_activation_results(results))


@main.command()
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
@click.option("--proxy-port", default=9339, type=int, help="Proxy port for Claude Code")
@click.option("--fail-fast", is_flag=True, help="Stop on first scenario failure")
@click.option("--verbose", is_flag=True, help="Show raw CLI output per step")
def harness(
    test_file: str,
    harness_name: str | None,
    model: str | None,
    parallel: int,
    timeout: int | None,
    max_cost: float | None,
    proxy_port: int,
    fail_fast: bool,
    verbose: bool,
):
    import asyncio

    from skillprobe.harness.adapters import get_adapter
    from skillprobe.harness.adapters.base import HarnessConfig
    from skillprobe.harness.loader import load_scenario_suite
    from skillprobe.harness.orchestrator import ScenarioOrchestrator
    from skillprobe.harness.reporter import format_harness_results

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
        proxy_port=proxy_port,
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


@main.command("init")
@click.argument("skill_dir", type=click.Path(exists=True))
@click.option("--harness", "harness_name", default="claude-code", help="Target harness")
@click.option("--output", default=None, type=click.Path(), help="Output YAML path")
@click.option("--model", default="claude-sonnet-4-6", help="Model for generation")
@click.option(
    "--anthropic-key", envvar="ANTHROPIC_API_KEY", default="", help="Anthropic API key"
)
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
    model: str,
    anthropic_key: str,
    fixtures_dir: str,
):
    import asyncio

    from skillprobe.harness.init_generator import generate_test_scaffold

    skill_path = Path(skill_dir)
    output_path = Path(output) if output else Path(f"tests/{skill_path.name}.yaml")

    click.echo(f"Generating tests for: {skill_path}")
    click.echo(f"  Harness: {harness_name}")
    click.echo(f"  Model: {model}")
    click.echo()

    result = asyncio.run(
        generate_test_scaffold(
            skill_path=skill_path,
            harness=harness_name,
            model=model,
            api_key=anthropic_key,
            output_path=output_path,
            fixtures_dir=Path(fixtures_dir),
        )
    )

    click.echo(result)
