---
name: write-tests
description: >
  Write skillprobe test scenarios for LLM skills. Generates behavioral test
  YAML (for `skillprobe run`) and activation test YAML (for `skillprobe activation`).
  Triggers on: "write tests for", "test this skill", "create test scenarios",
  "skillprobe test", "test my skill".
---

# Writing skillprobe Tests

Generate test YAML files for skillprobe, the automated skill testing tool.

## Two Test Types

### Behavioral tests (`skillprobe run`)

Test what the model does when the skill is loaded. Each scenario sends prompts and checks the response.

```yaml
harness: claude-code    # or cursor
model: claude-haiku-4-5-20251001
timeout: 120
skill: ./path/to/skill  # directory with SKILL.md, or a .md file

scenarios:
  - name: "descriptive name of what you're testing"
    steps:
      - prompt: "what the user would type"
        assert:
          - type: contains
            value: "expected text"
```

### Activation tests (`skillprobe activation`)

Test whether the skill loads for relevant prompts and stays quiet for irrelevant ones. Checks for actual Skill tool calls, not fuzzy text matching.

```yaml
harness: claude-code
model: claude-haiku-4-5-20251001
timeout: 60
skill: ./path/to/skill

activation:
  skill_name: my-skill   # matches against the loaded skill name
  should_activate:
    - "prompt that should trigger this skill"
    - "another relevant prompt"
  should_not_activate:
    - "unrelated prompt"
    - "another unrelated prompt"
```

## Assertion Types

| Type | What it checks | Example |
|---|---|---|
| `contains` | Response text includes value (case-insensitive) | `value: "deploy-k8s.sh"` |
| `not_contains` | Response text does NOT include value | `value: "helm install"` |
| `regex` | Response matches a regex pattern | `value: "def \\w+\\("` |
| `tool_called` | A specific tool was invoked | `value: "Bash"` |
| `skill_activated` | A specific skill was loaded via Skill tool | `value: "commit"` |
| `file_exists` | File exists in workspace (after block) | `value: ".git/COMMIT_EDITMSG"` |
| `file_contains` | File in workspace contains text (path:content) | `value: "main.py:def hello"` |

Any assertion can be inverted with `negate: true`.

## Multi-Run for Probabilistic Testing

Skills are probabilistic, so a single pass/fail isnt always meaningful. Use `runs` and `min_pass_rate` to measure reliability:

```yaml
steps:
  - prompt: "Write a function with type hints"
    runs: 5
    min_pass_rate: 0.8
    assert:
      - type: regex
        value: "-> "
```

## How to Write Good Tests for Domain Skills

Domain skills teach the model about a specific project (deployment commands, architecture, conventions). Testing them is different from testing generic skills.

### Test specific knowledge, not generic behavior

Bad (passes with any deployment knowledge):
```yaml
- type: contains
  value: "deploy"
```

Good (checks for YOUR project's specific command):
```yaml
- type: contains
  value: "deploy-k8s.sh"
- type: not_contains
  value: "helm install"
```

### Test categories for domain skills

1. **Correct commands**: Does the model use your specific tools and commands, not generic ones?
2. **Specific details**: Does the model know your domains, URLs, architecture names, config values?
3. **Negative cases**: Does the model avoid suggesting tools or patterns your project doesnt use?
4. **Activation boundaries**: Does the skill load for relevant prompts and stay quiet for unrelated ones?

### Template for a domain skill test

Read the skill content, then generate scenarios covering:

1. A prompt asking how to do the primary thing the skill teaches, asserting the response contains your project's specific commands or patterns
2. A prompt asking about a specific detail from the skill (a URL, a config value, an architecture component), asserting the exact value appears
3. A prompt that's tangentially related, asserting the model doesnt suggest tools your project doesnt use (`not_contains`)
4. An activation test with 2-3 should_activate prompts matching the skill's trigger words and 2-3 should_not_activate prompts for unrelated tasks

## Running the Tests

```bash
# Behavioral tests
skillprobe run tests/my-skill.yaml

# Activation tests
skillprobe activation tests/my-activation.yaml

# Override harness or model
skillprobe run tests/my-skill.yaml --harness cursor --model auto
```

## Workspace and Fixtures

Scenarios can use workspace fixtures for testing skills that interact with the filesystem:

```yaml
scenarios:
  - name: "commit skill creates proper commit"
    workspace: fixtures/dirty-repo    # copied fresh per scenario
    setup:
      - run: "echo 'change' >> file.txt && git add ."
    steps:
      - prompt: "commit my changes"
        assert:
          - type: tool_called
            value: "Bash"
    after:
      - type: file_exists
        value: ".git/COMMIT_EDITMSG"
```
