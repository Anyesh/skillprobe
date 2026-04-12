# Changelog

All notable changes to skillprobe are documented here.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project uses [Semantic Versioning](https://semver.org/).

## [0.5.0] - 2026-04-12

Skill combination testing. Multi-skill scenarios, a matrix expansion block for sweeping one skill against many, and a baseline diff mode that separates real combination regressions from natural model variance. A `measure` subcommand for characterizing scenario variance before picking thresholds. A local content-keyed run cache so repeated iterations do not burn the same API budget twice.

### Added
- Multi-skill workspace support: `skills:` list at suite level loads more than one skill per scenario. Backward compatible with the existing singular `skill:` field.
- `matrix:` expansion block for sweeping one base skill against a `pair_with` list. Each scenario runs once per pairing; reporter groups results by pairing.
- `--baseline` mode that runs every matrix pairing three times (solo A, solo B, combined) and classifies each assertion into one of `regression`, `shared_failure`, `flaky`, or `ok`. Accompanied by `--regression-margin` (default 0.15) and `--baseline-runs` (default 5, with a warning when below 10). Per-pairing and grand-total cost lines at the end of baseline runs.
- `skillprobe measure <test.yaml> [--runs N]` subcommand that runs each scenario N times and reports per-assertion pass rate, 95 percent Wilson confidence interval, and a variance classification of `deterministic`, `probabilistic`, `noisy`, or `unreliable`. Human-readable output by default, `--json` for machine-readable.
- Content-keyed local run cache at `~/.cache/skillprobe/runs/` (or `$XDG_CACHE_HOME/skillprobe/runs/`). Key includes SHA256 of skill file contents, prompt, model, harness, and skillprobe version. TTL 24 hours, configurable via `SKILLPROBE_CACHE_TTL_HOURS`. Flags `--no-cache`, `--force-refresh`, `--cache-dir`. Cached scenarios are marked `[cache hit]` in the reporter output.
- Loader validates assertion type names against the real handler registry at parse time. Unknown types raise `ValueError` with the list of valid types, rather than being silently skipped at runtime.
- Loader discriminates scenario files from activation files: a file that contains an `activation:` block is rejected by `load_scenario_suite`, and vice versa for `load_activation_suite`. Files missing both blocks raise a clear error.
- Loader detects skill name collisions in `skills:` lists at parse time: two skill paths that map to the same target directory inside `.claude/skills/` or `.cursor/skills/` raise before any workspace is created.
- Bundled `write-tests` skill teaches the new YAML surface: combination tests, matrix expansion, baseline mode, and the measure command.
- README sections for combinations, matrix expansion, baseline mode, measure, caching behavior, and PyPI/CI badges at the top.
- `CHANGELOG.md` and a GitHub Release creation step in the publish workflow.

### Changed
- `WorkspaceManager.create` signature changed from `skill: Path | None` to `skills: list[Path] | None`. The orchestrator and activation runner are updated to pass the list form. Existing scenario YAMLs using the singular `skill:` field continue to work without modification because the loader normalizes into the list form.
- Cursor adapter now captures stderr from the subprocess and raises a clear `RuntimeError` when the process exited non-zero with stderr content, or when the parsed stdout has no assistant text and no tool calls and stderr is non-empty. Previously, cursor usage-limit and invalid-model errors were silently written to stderr while the adapter returned an empty `response_text` that caused every downstream assertion to fail as "not found in response."
- `--max-cost` now emits a warning and clears the value when used with a harness other than claude-code. It was previously a silent no-op on cursor.
- Reporter adds a `[cache hit]` marker next to scenario lines where every step was fully served from the run cache, so replayed cost numbers on cached lines are not mistaken for new spend.

### Fixed
- `WorkspaceManager.create` no longer silently skips missing skill paths. It collects every missing path and raises `FileNotFoundError` with all of them listed, so typos in `skill:` or `skills:` surface immediately rather than producing workspaces with fewer skills than declared.
- `examples/tests/test-combo-sample.yaml` scenario 2 threshold tuned to `min_pass_rate: 0.6` based on a real 10-run variance probe against claude-haiku-4-5 that measured the observed pass rate at 70 percent with a CI spanning 0.40 to 0.89. The previous 0.8 threshold was above observed variance and produced flaky shipped examples.
- `examples/tests/combo-exemplars/test-activation-formatters.yaml` was using a non-existent `skill_loaded` assertion type; renamed to `skill_activated`. Later deleted along with the rest of the `combo-exemplars/` directory because the exemplar was fundamentally broken by design (identical-description fixture skills made activation a coin flip).

## [0.4.0] - 2026-04-01

First PyPI release after the README and packaging overhaul. Prior versions were tagged in git but not all were published. Adds `[project]` metadata, MIT license file, `py.typed` marker, GitHub Actions publish workflow using PyPI trusted publisher via OIDC.

## [0.3.0], [0.2.0], [0.1.1], [0.1.0]

Pre-release history. See git log and tags for details.
