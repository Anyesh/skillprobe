import re
from dataclasses import dataclass
from typing import Any


@dataclass
class AssertionResult:
    assertion_type: str
    passed: bool
    details: str


def check_assertion(
    assertion: dict[str, Any],
    response_text: str,
    system_prompt: str = "",
    parsed_data: dict[str, Any] | None = None,
) -> AssertionResult:
    atype = assertion.get("type", "")
    value = assertion.get("value", "")
    handler = _HANDLERS.get(atype)
    if handler is None:
        return AssertionResult(atype, False, f"Unknown assertion type: {atype}")
    if atype == "skill_loaded":
        return handler(value, response_text, system_prompt, parsed_data)
    return handler(value, response_text, system_prompt)


def _check_contains(value: str, response: str, _system: str) -> AssertionResult:
    passed = value.lower() in response.lower()
    details = f"'{value}' {'found' if passed else 'not found'} in response"
    return AssertionResult("contains", passed, details)


def _check_not_contains(value: str, response: str, _system: str) -> AssertionResult:
    passed = value.lower() not in response.lower()
    details = f"'{value}' {'not found' if passed else 'found'} in response"
    return AssertionResult("not_contains", passed, details)


def _check_regex(value: str, response: str, _system: str) -> AssertionResult:
    match = re.search(value, response)
    passed = match is not None
    details = f"Pattern '{value}' {'matched' if passed else 'did not match'}"
    return AssertionResult("regex", passed, details)


def _check_skill_present(value: str, _response: str, system: str) -> AssertionResult:
    passed = value.lower() in system.lower()
    details = f"Skill '{value}' {'detected' if passed else 'not detected'} in system prompt"
    return AssertionResult("skill_present", passed, details)


def _check_skill_loaded(value: str, _response: str, system: str, parsed_data: dict | None = None) -> AssertionResult:
    min_score = 0.3
    if parsed_data and "detected_skills" in parsed_data:
        for skill in parsed_data["detected_skills"]:
            if value.lower() in skill["name"].lower() and skill["score"] >= min_score:
                return AssertionResult("skill_loaded", True, f"Skill '{value}' detected (score: {skill['score']:.0%})")
        return AssertionResult("skill_loaded", False, f"Skill '{value}' not detected in captured skills")
    passed = value.lower() in system.lower()
    return AssertionResult("skill_loaded", passed, f"Skill '{value}' {'found' if passed else 'not found'} in system prompt (fallback)")


_HANDLERS = {
    "contains": _check_contains,
    "not_contains": _check_not_contains,
    "regex": _check_regex,
    "skill_present": _check_skill_present,
    "skill_loaded": _check_skill_loaded,
}


def check_when_conditions(conditions: list[dict[str, Any]], response_text: str, system_prompt: str = "") -> bool:
    if not conditions:
        return True
    return all(check_assertion(c, response_text, system_prompt).passed for c in conditions)
