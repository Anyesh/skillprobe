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
) -> AssertionResult:
    atype = assertion.get("type", "")
    value = assertion.get("value", "")
    handler = _HANDLERS.get(atype)
    if handler is None:
        return AssertionResult(atype, False, f"Unknown assertion type: {atype}")
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


_HANDLERS = {
    "contains": _check_contains,
    "not_contains": _check_not_contains,
    "regex": _check_regex,
    "skill_present": _check_skill_present,
}
