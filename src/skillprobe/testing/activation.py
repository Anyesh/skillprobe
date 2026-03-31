from dataclasses import dataclass
from pathlib import Path

import yaml

from skillprobe.parsers import parse_request
from skillprobe.storage.models import Capture


@dataclass
class ActivationCase:
    skill: str
    should_load_when: list[str]
    should_not_load_when: list[str]


@dataclass
class ActivationResult:
    skill: str
    trigger: str
    expected_loaded: bool
    actually_loaded: bool
    capture_id: int | None

    @property
    def passed(self) -> bool:
        return self.expected_loaded == self.actually_loaded


def load_activation_tests(path: Path) -> list[ActivationCase]:
    if not path.exists():
        raise FileNotFoundError(f"Activation test file not found: {path}")
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    cases = []
    for item in data.get("activations", []):
        cases.append(ActivationCase(
            skill=item["skill"],
            should_load_when=item.get("should_load_when", []),
            should_not_load_when=item.get("should_not_load_when", []),
        ))
    return cases


def _skill_in_system_prompt(skill_name: str, system_prompt: str) -> bool:
    return skill_name.lower() in system_prompt.lower()


def _message_matches_trigger(user_message: str, trigger: str) -> bool:
    return trigger.lower() in user_message.lower()


def _get_last_user_message(request_body: dict) -> str:
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
    return ""


def check_activations(cases: list[ActivationCase], captures: list[Capture]) -> list[ActivationResult]:
    results = []
    for case in cases:
        for trigger in case.should_load_when:
            matched_capture = None
            actually_loaded = False
            for c in captures:
                user_msg = _get_last_user_message(c.request_body)
                if not _message_matches_trigger(user_msg, trigger):
                    continue
                parsed = parse_request(c.path, c.request_body)
                if not parsed:
                    continue
                matched_capture = c.id
                actually_loaded = _skill_in_system_prompt(case.skill, parsed.system_prompt)
                break

            results.append(ActivationResult(
                skill=case.skill,
                trigger=trigger,
                expected_loaded=True,
                actually_loaded=actually_loaded,
                capture_id=matched_capture,
            ))

        for trigger in case.should_not_load_when:
            matched_capture = None
            actually_loaded = False
            for c in captures:
                user_msg = _get_last_user_message(c.request_body)
                if not _message_matches_trigger(user_msg, trigger):
                    continue
                parsed = parse_request(c.path, c.request_body)
                if not parsed:
                    continue
                matched_capture = c.id
                actually_loaded = _skill_in_system_prompt(case.skill, parsed.system_prompt)
                break

            results.append(ActivationResult(
                skill=case.skill,
                trigger=trigger,
                expected_loaded=False,
                actually_loaded=actually_loaded,
                capture_id=matched_capture,
            ))

    return results


def format_activation_results(results: list[ActivationResult]) -> str:
    lines = []
    current_skill = None
    passed = 0
    failed = 0
    no_capture = 0

    for r in results:
        if r.skill != current_skill:
            if current_skill is not None:
                lines.append("")
            current_skill = r.skill
            lines.append(f"  {r.skill}:")

        if r.capture_id is None:
            lines.append(f"    [--] \"{r.trigger}\" (no matching capture found)")
            no_capture += 1
        elif r.passed:
            action = "loaded" if r.expected_loaded else "not loaded"
            lines.append(f"    [OK] \"{r.trigger}\" -- correctly {action}")
            passed += 1
        else:
            expected = "loaded" if r.expected_loaded else "not loaded"
            actual = "loaded" if r.actually_loaded else "not loaded"
            lines.append(f"    [!!] \"{r.trigger}\" -- expected {expected}, was {actual}")
            failed += 1

    lines.append("")
    total = passed + failed
    if total > 0:
        lines.append(f"  {passed}/{total} passed ({passed/total:.0%})")
    if no_capture > 0:
        lines.append(f"  {no_capture} triggers had no matching captures")
    return "\n".join(lines)
