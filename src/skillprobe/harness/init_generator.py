from pathlib import Path

import httpx
import yaml


GENERATION_PROMPT = """You are a test generation expert. Given a skill definition (SKILL.md), generate a YAML test suite for automated skill testing.

The YAML format:
```yaml
harness: {harness}
model: claude-sonnet-4-6
timeout: 120
skill: {skill_path}

scenarios:
  - name: "descriptive name"
    workspace: fixtures/basic-project
    setup:
      - run: "shell command"
    steps:
      - prompt: "what the user would type"
        assert:
          - type: contains
            value: "expected text"
          - type: tool_called
            value: "ToolName"
    after:
      - type: file_exists
        value: "path/to/file"
```

Assertion types: contains, not_contains, regex, skill_loaded, skill_present, tool_called, file_exists, file_contains (format: "path:content")
Any assertion can have `negate: true` to invert it.

Generate scenarios covering:
1. Positive activation - prompts that SHOULD trigger the skill
2. Negative activation - prompts that should NOT trigger the skill
3. Behavioral correctness - does the skill produce the right output?
4. Multi-turn if applicable - conversational refinement
5. Edge cases from the skill's instructions

Output ONLY valid YAML. No markdown fences, no explanation.

Here is the skill:

{skill_content}"""


async def generate_test_scaffold(
    skill_path: Path,
    harness: str,
    model: str,
    api_key: str,
    output_path: Path,
    fixtures_dir: Path,
) -> str:
    skill_md = _find_skill_md(skill_path)
    if not skill_md:
        return f"No SKILL.md found in {skill_path}"

    skill_content = skill_md.read_text(encoding="utf-8")
    prompt = GENERATION_PROMPT.format(
        harness=harness,
        skill_path=str(skill_path),
        skill_content=skill_content,
    )

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            json={
                "model": model,
                "max_tokens": 4096,
                "system": "You generate YAML test suites. Output only valid YAML.",
                "messages": [{"role": "user", "content": prompt}],
            },
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        yaml_text = "\n".join(
            block["text"]
            for block in data.get("content", [])
            if block.get("type") == "text"
        )

    yaml_text = yaml_text.strip()
    if yaml_text.startswith("```"):
        lines = yaml_text.split("\n")
        yaml_text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    try:
        parsed = yaml.safe_load(yaml_text)
    except yaml.YAMLError as e:
        return f"Generated YAML failed to parse: {e}\n\nRaw output:\n{yaml_text}"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(yaml_text, encoding="utf-8")

    scenarios = parsed.get("scenarios", [])
    fixture_names = {s.get("workspace") for s in scenarios if s.get("workspace")}
    for fname in fixture_names:
        if fname:
            fpath = fixtures_dir / fname
            fpath.mkdir(parents=True, exist_ok=True)

    lines = [f"Generated: {output_path}"]
    lines.append(f"  {len(scenarios)} scenarios:")
    for s in scenarios:
        lines.append(f"    - {s.get('name', 'unnamed')}")
    if fixture_names:
        lines.append(f"  Fixture directories created:")
        for fname in sorted(fixture_names):
            lines.append(f"    - {fname}")
    lines.append("")
    lines.append("Review and adjust before running.")
    return "\n".join(lines)


def _find_skill_md(skill_path: Path) -> Path | None:
    if skill_path.is_file() and skill_path.name == "SKILL.md":
        return skill_path
    if skill_path.is_dir():
        candidate = skill_path / "SKILL.md"
        if candidate.exists():
            return candidate
    return None
