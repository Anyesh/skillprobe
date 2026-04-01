# skillprobe

AI coding tools like Claude Code and Cursor inject instructions into the LLM context behind the scenes, whether they call them skills, rules, or system prompts. There's no good way to test whether those instructions are actually being followed. You write a skill that says "never add docstrings" and half the time the model adds them anyway.

skillprobe automates the testing. It launches Claude Code or Cursor as subprocesses, runs your test scenarios in real workspaces, checks the output against assertions, and reports what passed and what didn't, all from a single command with no manual prompting required.

## Who this is for (and who it isn't)

If you write a few skills for your own use and tweak them when something feels off, you probably don't need this. Most people create skills by asking an LLM to write one, try it a couple times, and if the output looks wrong they ask the LLM to adjust it. That loop is fast, cheap, and good enough for personal use.

Where that loop breaks down:

**Model updates break skills silently.** Anthropic ships a new Sonnet, Cursor updates their agent behavior, and a skill that worked last week now produces subtly different output. Nobody notices because nobody retested, and skillprobe exists to catch exactly that kind of silent regression.

**Teams sharing skills across engineers.** When 20 developers share a "code review" skill, one person's gut check isn't representative because everyone is hitting it with different prompts, different codebases, and different expectations. You need actual coverage across scenarios to know whether the skill holds up.

**Publishing to marketplaces.** Both Claude Code and Cursor now have plugin marketplaces where skill authors ship to thousands of users. At that point you're distributing software, not vibing with your own tool. User reports from strangers don't come with context, and "ask the LLM to fix it" doesn't scale to reproducing someone else's problem.

**Breaking the endless tweak loop.** You named a skill "clean-python" and told it to never add docstrings, but after three rounds of edits you're not sure if the latest version is actually better or if you just moved the problem around. skillprobe gives you a definitive "this version is better than the last one" signal by running the same scenarios against both and comparing pass rates.

If none of those situations apply to you, a simpler workflow (write skill, try it, adjust) is probably the right call. skillprobe is for when you need more confidence than vibing can provide.

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

Generate test scenarios from an existing skill, then run them:

```bash
skillprobe init ./skills/my-skill --harness claude-code
skillprobe run tests/my-skill.yaml
```

```
Running: tests/my-skill.yaml
  Harness: claude-code
  Model: claude-haiku-4-5-20251001
  Scenarios: 3
  Parallel: 1

  [PASS] commit skill activates on request (9.1s)
  [PASS] multi-turn refinement (12.3s)
  [FAIL] negative activation -- 'commit' found in response
         step 1: "explain what this project does"
           'commit' found in response

  2/3 passed (27.8s)
```

## Writing scenarios

Scenarios are YAML files describing what to test. Each scenario can have multiple conversational steps, a workspace fixture that gets copied fresh for every run, setup commands, and post-run assertions that check workspace state after everything finishes:

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

Supported assertion types: `contains`, `not_contains`, `regex`, `tool_called`, `file_exists`, and `file_contains`. Any assertion can be inverted with `negate: true`.

## Generating tests

You don't have to write scenario YAML from scratch. Point `init` at a skill directory and it reads the SKILL.md, uses an LLM to figure out what should be tested (positive activation, negative activation, behavioral correctness, edge cases), and writes a starter YAML file you can review and tweak:

```bash
skillprobe init ./skills/commit --harness claude-code
```

The `init` command supports both Anthropic and OpenAI as providers for test generation. Pass `--provider openai` and `--model gpt-4o` if you prefer, or it defaults to Anthropic with `claude-sonnet-4-6`. This requires an API key for whichever provider you choose (via `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`).

## Commands

**`skillprobe run <test.yaml>`** runs test scenarios against a real coding tool.

| Flag | Default | Description |
|---|---|---|
| `--harness` | from YAML | `claude-code` or `cursor` |
| `--model` | from YAML | Model to use for the tool under test |
| `--parallel` | 1 | Number of scenarios to run concurrently |
| `--timeout` | from YAML | Per-scenario timeout in seconds |
| `--max-cost` | none | Max USD spend (Claude Code only) |

**`skillprobe init <skill-dir>`** generates starter test YAML from a skill definition.

| Flag | Default | Description |
|---|---|---|
| `--harness` | `claude-code` | Target harness |
| `--output` | `tests/<skill>.yaml` | Output YAML path |
| `--provider` | `anthropic` | LLM provider for generation |
| `--model` | auto | Model for generation |
| `--fixtures-dir` | `fixtures` | Where to write fixture directories |

## Using in CI

skillprobe works well in CI for catching regressions when models update or skills change. The CI environment needs the target tool's CLI installed and authenticated, since skillprobe spawns it as a subprocess.

```yaml
# .github/workflows/skill-tests.yml
name: skill-tests

on:
  push:
    paths: ["skills/**", "tests/**"]
  schedule:
    - cron: "0 6 * * 1"  # weekly Monday 6am

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

## Why not promptfoo

Tools like promptfoo test prompts in isolation by making their own API calls, outside the tool that will actually use them. skillprobe runs the real tools as subprocesses in real workspaces, so it tests the full stack: skill loading, tool use, file system interactions, multi-turn conversations. It also works with subscriptions (no API key required for the tool under test, only for `init` if you use it).

## References

- https://github.com/karpathy/autoresearch
- https://www.news.aakashg.com/p/autoresearch-guide-for-pms
- https://fortune.com/2026/03/17/andrej-karpathy-loop-autonomous-ai-agents-future/
