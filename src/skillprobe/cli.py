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
@click.option("--skills", multiple=True, type=click.Path(exists=True), help="Skill directories to monitor")
def start(host: str, port: int, db: str, skills: tuple[str, ...]):
    from skillprobe.proxy.server import run_proxy

    config = ProxyConfig(
        host=host,
        port=port,
        db_path=Path(db),
        skill_dirs=[Path(s) for s in skills],
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

    click.echo(f"{'ID':>5} {'Time':>20} {'Provider':>10} {'Model':>30} {'Status':>6} {'Duration':>10}")
    click.echo("-" * 85)
    for c in results:
        model = c.request_body.get("model", "?")[:30]
        ts = c.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        dur = f"{c.duration_ms:.0f}ms" if c.duration_ms else "?"
        click.echo(f"{c.id:>5} {ts:>20} {c.provider:>10} {model:>30} {c.response_status or '?':>6} {dur:>10}")


@main.command()
@click.argument("capture_id", type=int)
@click.option("--db", default="skillprobe.db", type=click.Path(), help="Database path")
@click.option("--full", is_flag=True, help="Show full system prompt")
@click.option("--skills", multiple=True, type=click.Path(exists=True), help="Skill directories for detection")
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
@click.option("--anthropic-key", envvar="ANTHROPIC_API_KEY", default="", help="Anthropic API key")
@click.option("--openai-key", envvar="OPENAI_API_KEY", default="", help="OpenAI API key")
def run_tests(test_file: str, model: str | None, provider: str | None, anthropic_key: str, openai_key: str):
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
@click.option("--capture", "capture_ids", multiple=True, type=int, help="Specific capture IDs to check")
@click.option("--last", default=None, type=int, help="Check last N captures")
def assert_captures(test_file: str, db: str, capture_ids: tuple[int, ...], last: int | None):
    from skillprobe.parsers import parse_request
    from skillprobe.proxy.handler import _extract_response_text
    from skillprobe.storage.database import Database
    from skillprobe.testing.assertions import check_assertion
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

    click.echo(f"Checking {len(captures_with_response)} captures against {len(suite.tests)} test cases\n")

    for c in captures_with_response:
        parsed = parse_request(c.path, c.request_body)
        system_prompt = parsed.system_prompt if parsed else ""
        provider = parsed.provider if parsed else c.provider
        response_text = _extract_response_text(c.response_body, provider)
        if not response_text:
            continue

        user_msg = _last_user_message(c.request_body)
        click.echo(f"  Capture #{c.id} - \"{user_msg[:60]}{'...' if len(user_msg) > 60 else ''}\"")

        for tc in suite.tests:
            results = [check_assertion(a, response_text, system_prompt) for a in tc.assertions]
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
@click.option("--skills", multiple=True, type=click.Path(exists=True), help="Skill directories")
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
            click.echo(f"  {name}: {count}/{len(captures)} ({count / len(captures):.0%})")
