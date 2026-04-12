# skillprobe

[![PyPI version](https://img.shields.io/pypi/v/skillprobe.svg)](https://pypi.org/project/skillprobe/)
[![Python versions](https://img.shields.io/pypi/pyversions/skillprobe.svg)](https://pypi.org/project/skillprobe/)
[![Tests](https://img.shields.io/github/actions/workflow/status/Anyesh/skillprobe/test.yml?branch=main&label=tests)](https://github.com/Anyesh/skillprobe/actions/workflows/test.yml)
[![License](https://img.shields.io/pypi/l/skillprobe.svg)](https://github.com/Anyesh/skillprobe/blob/main/LICENSE)

Release notes: see [CHANGELOG.md](CHANGELOG.md) or the [GitHub Releases page](https://github.com/Anyesh/skillprobe/releases).

![skillprobe demo](demo/skillprobe-demo.gif)

Automated testing for LLM skills. Launches Claude Code or Cursor as subprocesses, runs scenarios in isolated workspaces, and reports what passed and what didn't.

Skills are just text injected into the LLM context, and LLMs are probabilistic, so they'll get ignored some percentage of the time no matter how carefully you word them. If you want hard enforcement, hooks are the right tool since they run deterministically every time. But hooks can only check things after the fact (linting, file restrictions, blocked commands). They cant guide the model toward better architectural decisions, teach it your team's domain conventions, set the tone of code review feedback, or help it reason through a multi-step workflow. Skills handle that side, and skillprobe measures how reliably they do it.

## When you need this

If you write a few personal skills and tweak them by feel, you probably dont need this. That loop is fast and good enough for individual use.

Where it breaks down:

- **Model updates break skills silently.** Anthropic ships a new Sonnet, Cursor updates their agent, and a skill that worked last week now produces different output. Nobody notices because nobody retested.
- **Teams sharing skills.** When 20 engineers share a "code review" skill, one person's gut check isnt representative. You need coverage across scenarios to know whether the skill holds up.
- **Publishing to marketplaces.** At that point you're distributing software, not vibing with your own tool. "Ask the LLM to fix it" doesnt scale to reproducing someone else's problem.
- **The endless tweak loop.** After three rounds of edits you cant tell if the latest version is better or if you just moved the problem around. skillprobe gives you a definitive signal by running the same scenarios against both versions and comparing pass rates.

## Installation

```bash
pip install skillprobe
```

Or with uv:

```bash
uv tool install skillprobe
```

Or from source:

```bash
git clone https://github.com/Anyesh/skillprobe.git
cd skillprobe
uv sync
```

## Quick start

The repo ships with example skills and test scenarios you can run immediately:

```bash
git clone https://github.com/Anyesh/skillprobe.git
cd skillprobe
uv sync
uv run skillprobe run examples/tests/test-clean-python.yaml
```

```
Running: examples/tests/test-clean-python.yaml
  Harness: claude-code
  Model: claude-haiku-4-5-20251001
  Scenarios: 5
  Parallel: 1

  [PASS] no docstrings on simple functions (11.6s $0.0204)
  [PASS] imports at top level (7.2s $0.0199)
  [PASS] no obvious comments (7.2s $0.0187)
  [FAIL] uses type hints (6.8s $0.0191)
         step 1: "Write a Python function that takes a list of integ"
           Pattern 'def \w+\(.*:.*\)' did not match
           Pattern '-> ' did not match
  [PASS] skill does not block normal functionality (11.3s $0.0202)

  4/5 passed (44.0s)
  Total cost: $0.10
```

Requires Claude Code or Cursor CLI installed and authenticated.

To generate tests for your own skill, use the bundled `write-tests` skill. Open Claude Code or Cursor in the skillprobe repo and ask it to write tests for your skill. It knows the YAML format and will generate both behavioral and activation test files. No API key needed since it runs through your existing subscription.

## Writing scenarios

Scenarios are YAML files describing what to test. Each scenario can have multiple conversational steps, a workspace fixture that gets copied fresh for every run, setup commands that prepare the workspace, and post-run assertions that check workspace state after everything finishes:

```yaml
harness: claude-code
model: claude-haiku-4-5-20251001
timeout: 120
skill: ./skills/commit

scenarios:
  - name: "commit skill activates on request"
    workspace: fixtures/dirty-repo
    setup:
      - run: "echo 'change' >> file.txt && git add ."
    steps:
      - prompt: "commit my changes"
        assert:
          - type: contains
            value: "commit"
          - type: tool_called
            value: "Bash"
    after:
      - type: file_exists
        value: ".git/COMMIT_EDITMSG"

  - name: "does not activate for unrelated request"
    steps:
      - prompt: "explain what this project does"
        assert:
          - type: not_contains
            value: "commit"
```

Assertion types: `contains`, `not_contains`, `regex`, `tool_called`, `skill_activated`, `file_exists`, `file_contains`. Any assertion can be inverted with `negate: true`.

### Multi-run for measuring reliability

Since skills are probabilistic, a single pass/fail isnt always meaningful. Run the same prompt multiple times and set a pass rate threshold:

```yaml
steps:
  - prompt: "Write a function with type hints"
    runs: 5
    min_pass_rate: 0.8
    assert:
      - type: regex
        value: "-> "
```

```
  [PASS] uses type hints (21.0s $0.0416)
         step 1: [ok] 4/5 passed (80%)
```

### Testing skill combinations

Skills loaded together can interact in unexpected ways: one skill's rules can contradict another's, two skills can fight over which one handles a prompt, or a workflow that works in isolation can deadlock when combined. Load multiple skills in a single scenario suite using a `skills:` list at suite level:

```yaml
harness: claude-code
model: claude-haiku-4-5-20251001
skills:
  - ./examples/skills/clean-code
  - ./examples/skills/bad-python

scenarios:
  - name: "contradicting docstring rules surface clearly"
    steps:
      - prompt: "Write a Python function called add that takes two integers"
        runs: 5
        min_pass_rate: 0.8
        assert:
          - type: regex
            value: 'def add\(.*: int.*: int.*\) -> int'
          - type: not_contains
            value: '"""'
```

The single-skill `skill:` field still works unchanged for existing test files. Use `skill:` for single-skill tests and `skills:` when you want to load two or more at once. Both keys in the same file is a parse error.

See `examples/tests/test-combo-sample.yaml` for a runnable example.

### Testing combinations at scale with a matrix

When you want to test one skill against many others, for example a new skill paired against every popular skill in a reference set, a `matrix:` block at suite level expands one YAML into N scenario runs, one per pairing:

```yaml
harness: claude-code
model: claude-haiku-4-5-20251001

matrix:
  base: ./skills/commit
  pair_with:
    - ./skills/verification-before-completion
    - ./skills/clean-python
    - ./skills/systematic-debugging

scenarios:
  - name: "commit respects the paired skill's conventions"
    steps:
      - prompt: "commit my changes"
        runs: 5
        min_pass_rate: 0.8
        assert:
          - type: regex
            value: '(conventional|feat|fix|chore)'
```

Each scenario runs once per `pair_with` entry with `base` and that entry loaded together. Reporter output groups results by pairing so you can see at a glance which combinations regressed and which held up. Total cost is linear in the length of the `pair_with` list. Cache entries apply per cell, so rerunning the same matrix after editing one skill only repays for the cells that actually changed.

`matrix:` cannot coexist with `skill:` or `skills:` at the suite level; pick one. Use `skill:` for a single test, `skills:` for a hand-authored combination, and `matrix:` when you want to sweep one base against many pairings from a single file.

### Detecting real combination regressions with baseline mode

A matrix run gives you a pile of pass/fail results but does not tell you whether a combined failure is a genuine combination regression or just natural model variance. The `--baseline` mode runs each matrix pairing three times per scenario (base skill alone, paired skill alone, both loaded) and classifies every assertion into one of four buckets:

- `regression` means both solo runs passed cleanly and the combined run dropped beyond the regression margin. This is the bucket you should act on.
- `shared_failure` means both solo and combined failed. Not a combination problem; fix your scenario or one of the skills.
- `flaky` means combined dropped but the drop is within the margin. Reported for visibility but does not fail the exit code.
- `ok` means combined matches or exceeds the solo pass rates.

```bash
skillprobe run my-matrix.yaml --baseline --baseline-runs 20
```

`--baseline-runs` defaults to 5, but you should use at least 10 and preferably 20 because at small N the Wilson confidence interval on each configuration is so wide that the regression test becomes permissive and everything comes back `ok` or `flaky`. A warning prints when the value is below 10. `--regression-margin` (default 0.15) sets how far the combined rate must drop below the narrowest solo lower bound before it counts as a regression.

Cost is roughly three times a regular matrix run because every pair needs two solo baselines plus the combined run. Treat this as a nightly or on-demand audit, not a per-PR check. skillprobe prints a per-pairing and grand-total cost line at the end of baseline runs so you can see what the session actually spent.

### Measuring variance before you set thresholds

Skills on modern models are probabilistic. Before picking a `min_pass_rate`, measure the scenario's natural variance with the bundled `measure` command:

```bash
skillprobe measure examples/tests/test-combo-sample.yaml --runs 20
```

Output is a per-assertion pass rate, a 95 percent Wilson confidence interval, and a variance classification of `deterministic`, `probabilistic`, `noisy`, or `unreliable`. Use this to pick a threshold from real numbers instead of guessing. As an example of how much variance is normal, `test-combo-sample.yaml` measured against claude-haiku-4-5 on a 10-run probe landed at a 90 percent pass rate on one assertion and a 70 percent pass rate on another with a 95 percent CI spanning 0.40 to 0.89, so a single pass/fail run against that scenario genuinely cannot tell you whether it is working.

`skillprobe measure` deliberately does not use the run cache so every invocation characterizes fresh variance.

### Caching runs

Repeated runs of the same scenario against the same skill files, model, and harness read from a local cache at `~/.cache/skillprobe/runs/` (or `$XDG_CACHE_HOME/skillprobe/runs/`). The cache key is a SHA256 of skill file contents, prompt, model, harness, and skillprobe version, so any change to any of those invalidates the entry automatically. TTL is 24 hours by default, configurable via `SKILLPROBE_CACHE_TTL_HOURS`.

A scenario whose runs all hit the cache is shown in the reporter as `[cache hit]` next to the scenario line. The cost number in parentheses on a cached line is the replayed cost from the original run, not new spend, so a cached scenario header looks like `[PASS] scenario name (0.0s $0.0516) [cache hit]`.

Disable caching entirely with `--no-cache` or `SKILLPROBE_NO_CACHE=1`. Bypass cache reads but keep writing fresh results with `--force-refresh`. Override the cache directory with `--cache-dir /some/other/path` for testing or isolation.

## Commands

**`skillprobe run <test.yaml>`** runs test scenarios against a real coding tool.

| Flag | Default | Description |
|---|---|---|
| `--harness` | from YAML | `claude-code` or `cursor` |
| `--model` | from YAML | Model to use for the tool under test |
| `--parallel` | 1 | Number of scenarios to run concurrently |
| `--timeout` | from YAML | Per-scenario timeout in seconds |
| `--max-cost` | none | Max USD spend per subprocess (Claude Code only; ignored on cursor with a warning) |
| `--no-cache` | false | Disable the local run cache entirely for this invocation |
| `--force-refresh` | false | Bypass cache reads but still write fresh results |
| `--cache-dir` | `~/.cache/skillprobe/runs/` | Override the cache directory |
| `--baseline` | false | Run each matrix pairing in solo / solo / combined baseline diff mode |
| `--regression-margin` | 0.15 | Regression margin used by the baseline classifier |
| `--baseline-runs` | 5 | Number of runs per configuration in baseline mode (use 10+ for meaningful results) |

**`skillprobe measure <test.yaml>`** runs each scenario N times and reports a per-assertion pass rate, 95 percent Wilson confidence interval, and a variance classification. Use this to pick `min_pass_rate` from data instead of guessing. Does not use the run cache.

| Flag | Default | Description |
|---|---|---|
| `--runs` | 20 | Number of runs per scenario |
| `--harness` | from YAML | `claude-code` or `cursor` |
| `--model` | from YAML | Model to use |
| `--timeout` | from YAML | Per-prompt timeout in seconds |
| `--json` | false | Emit JSON instead of the human-readable report |

**`skillprobe activation <test.yaml>`** tests whether a skill loads for relevant prompts and stays quiet for irrelevant ones. Detects skill loading by checking for Skill tool calls in the CLI output rather than fuzzy matching response text.

| Flag | Default | Description |
|---|---|---|
| `--harness` | from YAML | `claude-code` or `cursor` |
| `--model` | from YAML | Model to use |
| `--timeout` | from YAML | Per-prompt timeout in seconds |

## CI

skillprobe works in CI for catching regressions when models update or skills change. The CI runner needs the target tool's CLI installed and authenticated.

```yaml
name: skill-tests
on:
  push:
    paths: ["skills/**", "tests/**"]
  schedule:
    - cron: "0 6 * * 1"

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm install -g @anthropic-ai/claude-code
      - uses: astral-sh/setup-uv@v4
      - run: uv tool install skillprobe
      - run: skillprobe run tests/my-skill.yaml --harness claude-code
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

## Security

Scenario YAML files are executable content. Setup commands run with your full user permissions, and the harness launches the AI tool with `--dangerously-skip-permissions` (or `--force` for Cursor), giving it full filesystem access. The temporary workspace is the working directory for the subprocess, but the tool is not sandboxed to it and can read or modify files elsewhere on your system. Treat test YAML files like shell scripts and don't run YAML from untrusted sources. File path assertions (`file_exists`, `file_contains`) validate against workspace boundary escapes on the skillprobe side.

## Why not promptfoo

promptfoo tests prompts in isolation via direct API calls, outside the tool that will actually use them. skillprobe runs the real tool as a subprocess in a real workspace, testing the full stack: skill loading, tool use, file system interactions, multi-turn conversations. Works with subscriptions too since the tool under test handles its own auth.
