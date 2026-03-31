# skillprobe

AI coding tools like Claude Code, Cursor, Copilot etc all inject instructions into the LLM context behind the scenes -- skills, rules, system prompts, whatever you want to call them. Theres no good way to test whether those instructions are actually being followed though. You write a skill that says "never add docstrings" and half the time the model adds them anyway.

skillprobe is a local proxy that sits between your tool and the LLM API, captures the full request and response, and lets you run assertions against them. It works with subscriptions (Claude Pro, Cursor Pro, etc) since your tool handles authentication normally and skillprobe just observes the traffic going through.

It also has a **harness** that automates the entire flow -- no more manually opening Claude Code, typing prompts, and checking results. One command spins up the proxy, launches `claude -p` or Cursor's `agent -p` as subprocesses, runs your test scenarios, evaluates assertions, and tears everything down. Works like a test suite.

## Quick start

```bash
git clone <repo>
cd skillprobe
uv sync
```

```bash
# start the proxy
uv run skillprobe start --watch tests/my-skill.yaml

# in another terminal, point your tool at it
ANTHROPIC_BASE_URL=http://localhost:9339 claude "write a prime checker"
```

You'll see assertion results in real time as responses come back:

```
12:30:45 [anthropic] POST /v1/messages model=claude-opus-4-6 messages=12 tools=15
12:30:47   -> 200 (1823ms) capture=#42 system=45230 chars, 28 sections, response=892 chars
           [PASS] no docstrings
           [SKIP] imports at top (when condition not met)
           [FAIL] uses type hints -- Pattern '-> ' did not match
```

## Writing tests

Test suites are YAML files where you define assertions that run against LLM responses. The `when` field lets you make assertions conditional, so something like "no docstrings" only gets checked when the response actually contains a function definition.

```yaml
skill: ./skills/clean-python.md
tests:
  - name: no docstrings on simple functions
    when:
      - type: regex
        value: "def \\w+\\("
    assert:
      - type: not_contains
        value: '"""'

  - name: uses type hints
    when:
      - type: regex
        value: "def \\w+\\("
    assert:
      - type: regex
        value: "-> "
```

Supported assertion types are `contains`, `not_contains`, `regex`, `skill_present`, and `skill_loaded`.

## Automated harness testing

Instead of manually running prompts through Claude Code or Cursor, the harness automates the full lifecycle. Write scenario YAML, run one command:

```bash
uv run skillprobe harness tests/my-skill.yaml --harness claude-code --model claude-haiku-4-5-20251001
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

### Scenario format

Scenarios support multi-step conversations, workspace fixtures, setup commands, and post-run assertions:

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

The harness supports `contains`, `not_contains`, `regex`, `skill_present`, `skill_loaded`, `tool_called`, `file_exists`, and `file_contains` assertions. Any assertion can be inverted with `negate: true`.

### Harness support

| Harness | Command | Proxy capture | Behavioral testing |
|---|---|---|---|
| Claude Code | `claude -p` | yes (full system prompt, skill detection) | yes |
| Cursor | `agent -p` | no (Cursor routes through its own API) | yes |

### Generating tests

Point `init` at a skill directory and it uses the LLM to generate a starter test suite:

```bash
uv run skillprobe init ./skills/commit --harness claude-code
```

This reads the SKILL.md, generates scenarios covering positive activation, negative activation, behavioral correctness, and edge cases, then writes a YAML file you can review and tweak.

## Optimizing skills

This part borrows from Karpathy's autoresearch idea -- you tag your captures with session names, look at whats failing, apply mutations to the skill, and then compare before/after.

```bash
# run with your current skill and tag captures as v1
skillprobe start --session v1 --watch skill-tests/my-skill.yaml
# ... use your tool for a bit ...

# see whats failing and get suggestions
skillprobe analyze skill-tests/my-skill.yaml --session v1

# apply one of the suggested mutations
skillprobe optimize skills/clean-python.md --mutation add_constraint --test skill-tests/my-skill.yaml

# run again with the updated skill, tag as v2
skillprobe start --session v2 --watch skill-tests/my-skill.yaml
# ... use your tool again ...

# see what changed
skillprobe diff skill-tests/my-skill.yaml --session v1 --session v2
```

```
Test                                 v1          v2      Delta
no docstrings                       80%         95%   +15% improved
uses type hints                     90%         85%    -5% regressed
```

There are six mutation operators (add_constraint, add_negative_example, restructure, tighten_language, remove_bloat, add_counterexample) and you can revert if something makes things worse with `skillprobe optimize --revert`.

## Activation testing

Separate from whether a skill is being followed, theres also the question of whether it gets loaded at the right time. Skills arent always in context -- tools like Claude Code and Cursor load them dynamically based on relevance. If your skill's description or keywords are off, it might not load when it should, or load when it shouldnt.

Activation tests let you define when a skill should and shouldnt be present:

```yaml
activations:
  - skill: sqlalchemy
    should_load_when:
      - "write a sqlalchemy model"
      - "create a database migration"
    should_not_load_when:
      - "write a hello world in python"
      - "what is recursion"
```

Then check against your captures:

```bash
skillprobe activation tests/test-activation.yaml --last 50
```

```
  sqlalchemy:
    [OK] "write a sqlalchemy model" -- correctly loaded
    [OK] "create a database migration" -- correctly loaded
    [OK] "write a hello world in python" -- correctly not loaded
    [!!] "what is recursion" -- expected not loaded, was loaded
```

This isnt about testing Claude Code or Cursor's loading logic -- its about making sure your skill file has the right description and content so the tool picks it up when it should.

## Commands

- `start` - run the proxy (`--watch`, `--session`, `--skills`)
- `captures` - list whats been captured
- `inspect <id>` - look at a specific capture in detail
- `assert <test.yaml>` - check captures against assertions
- `harness <test.yaml>` - automated end-to-end skill testing (`--harness`, `--parallel`, `--model`)
- `init <skill-dir>` - generate test YAML from a skill using LLM
- `analyze <test.yaml>` - find failure patterns, suggest mutations
- `optimize <skill.md>` - apply a mutation (backs up the original)
- `diff <test.yaml>` - compare sessions
- `test <test.yaml>` - run tests via direct API calls (needs API key)
- `activation <test.yaml>` - check if skills load at the right time
- `report` - aggregate stats

## What gets captured

The full API request including the system prompt with all injected skills, tool definitions, conversation messages, model name, and temperature settings. For streaming responses (which is what most tools use), skillprobe reassembles the SSE chunks into a complete response while still passing them through to your tool in real time so nothing breaks. Both Anthropic and OpenAI API formats are supported, and everything is stored in a local SQLite database.

## Why not promptfoo or similar

Tools like promptfoo test prompts in isolation by making their own API calls. They dont see what Claude Code or Cursor actually sends to the API, they cant tell you which skills got loaded or if two skills are conflicting, and they all require API keys which doesnt work if you're on a subscription plan. skillprobe captures the real traffic from real tools so what you test is what actually happens in practice.


## References:
- https://github.com/karpathy/autoresearch
- https://www.news.aakashg.com/p/autoresearch-guide-for-pms
- https://fortune.com/2026/03/17/andrej-karpathy-loop-autonomous-ai-agents-future/
