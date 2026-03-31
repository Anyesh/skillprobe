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
