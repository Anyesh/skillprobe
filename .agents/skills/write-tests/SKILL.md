---
name: write-tests
description: >
  Write skillprobe YAML tests for LLM skills. Use when asked to write tests,
  create test scenarios, test a skill, generate skillprobe tests, or check
  whether a skill activates correctly.
---

# Writing skillprobe Tests

Generate YAML test files for skillprobe. Always read the skill content first before writing tests.

When asked to write tests for a skill, generate BOTH files unless the user asks for only one:
1. A behavioral test file (for `skillprobe run`)
2. An activation test file (for `skillprobe activation`)

## Behavioral Tests (for `skillprobe run`)

Test what the model DOES when the skill is loaded.

```yaml
harness: claude-code    # or cursor
model: claude-haiku-4-5-20251001
timeout: 120
skill: ./path/to/skill  # directory with SKILL.md, or a .md file

scenarios:
  - name: "descriptive name"
    steps:
      - prompt: "what the user would type"
        assert:
          - type: contains
            value: "expected text"
```

## Activation Tests (for `skillprobe activation`)

Test whether the skill LOADS for relevant prompts and stays quiet for irrelevant ones. This is a separate YAML format from behavioral tests.

```yaml
harness: claude-code
model: claude-haiku-4-5-20251001
timeout: 60
skill: ./path/to/skill

activation:
  skill_name: my-skill
  should_activate:
    - "prompt that should trigger this skill"
    - "another relevant prompt"
  should_not_activate:
    - "completely unrelated prompt"
    - "another unrelated prompt"
```

The `activation` key replaces `scenarios`. These are two different file formats. Do not mix them.

## Assertion Types

| Type | Checks | Example |
|---|---|---|
| `contains` | Response includes value (case-insensitive) | `value: "deploy-k8s.sh"` |
| `not_contains` | Response does NOT include value | `value: "helm install"` |
| `regex` | Response matches pattern | `value: "def \\w+\\("` |
| `tool_called` | A tool was invoked | `value: "Bash"` |
| `skill_activated` | A skill was loaded | `value: "commit"` |
| `file_exists` | File exists in workspace (after block) | `value: ".git/COMMIT_EDITMSG"` |
| `file_contains` | File contains text (path:content) | `value: "main.py:def hello"` |

Any assertion supports `negate: true` to invert it.

## Multi-Run

Skills are probabilistic. Use `runs` and `min_pass_rate` to measure reliability:

```yaml
steps:
  - prompt: "Write a function with type hints"
    runs: 5
    min_pass_rate: 0.8
    assert:
      - type: regex
        value: "-> "
```

## Writing Good Domain Skill Tests

Domain skills teach project-specific knowledge. Test for YOUR specifics, not generic behavior.

Bad: `value: "deploy"` (any deployment knowledge passes)
Good: `value: "deploy-k8s.sh"` with `not_contains: "helm install"` (checks your exact tool)

For every domain skill, cover:
1. **Correct commands**: your specific tools, not generic alternatives
2. **Specific details**: URLs, config values, architecture names from the skill
3. **Negative cases**: tools or patterns your project doesnt use
4. **Activation**: prompts from the skill's trigger words, plus unrelated prompts that should not trigger it

## Running

```bash
skillprobe run tests/my-skill.yaml
skillprobe activation tests/my-activation.yaml
skillprobe run tests/my-skill.yaml --harness cursor --model auto
```
