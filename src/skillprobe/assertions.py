import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from skillprobe.evidence import StepEvidence


@dataclass
class HarnessAssertionResult:
    assertion_type: str
    passed: bool
    details: str


def check_harness_assertion(
    assertion: dict[str, Any],
    evidence: StepEvidence,
    workspace: Path | None = None,
) -> HarnessAssertionResult:
    atype = assertion.get("type", "")
    value = assertion.get("value", "")
    negate = assertion.get("negate", False)

    handler = _HANDLERS.get(atype)
    if handler is None:
        return HarnessAssertionResult(atype, False, f"Unknown assertion type: {atype}")

    if atype in ("file_exists", "file_contains"):
        result = handler(value, evidence, workspace)
    else:
        result = handler(value, evidence)

    if negate:
        result = HarnessAssertionResult(
            assertion_type=result.assertion_type,
            passed=not result.passed,
            details=f"(negated) {result.details}",
        )

    return result


def _check_contains(value: str, evidence: StepEvidence) -> HarnessAssertionResult:
    passed = value.lower() in evidence.response_text.lower()
    details = f"'{value}' {'found' if passed else 'not found'} in response"
    return HarnessAssertionResult("contains", passed, details)


def _check_not_contains(value: str, evidence: StepEvidence) -> HarnessAssertionResult:
    passed = value.lower() not in evidence.response_text.lower()
    details = f"'{value}' {'not found' if passed else 'found'} in response"
    return HarnessAssertionResult("not_contains", passed, details)


def _check_regex(value: str, evidence: StepEvidence) -> HarnessAssertionResult:
    try:
        match = re.search(value, evidence.response_text)
    except re.error as e:
        return HarnessAssertionResult("regex", False, f"Invalid regex '{value}': {e}")
    passed = match is not None
    details = f"Pattern '{value}' {'matched' if passed else 'did not match'}"
    return HarnessAssertionResult("regex", passed, details)


def _check_tool_called(value: str, evidence: StepEvidence) -> HarnessAssertionResult:
    called = any(tc.tool_name.lower() == value.lower() for tc in evidence.tool_calls)
    details = f"Tool '{value}' {'was called' if called else 'was not called'}"
    return HarnessAssertionResult("tool_called", called, details)


def _check_file_exists(
    value: str, evidence: StepEvidence, workspace: Path | None
) -> HarnessAssertionResult:
    if workspace is None:
        return HarnessAssertionResult("file_exists", False, "No workspace provided")
    target = (workspace / value).resolve()
    if not str(target).startswith(str(workspace.resolve())):
        return HarnessAssertionResult(
            "file_exists", False, f"Path '{value}' escapes workspace"
        )
    exists = target.exists()
    details = f"'{value}' {'exists' if exists else 'not found'} in workspace"
    return HarnessAssertionResult("file_exists", exists, details)


def _check_file_contains(
    value: str, evidence: StepEvidence, workspace: Path | None
) -> HarnessAssertionResult:
    if workspace is None:
        return HarnessAssertionResult("file_contains", False, "No workspace provided")
    parts = value.split(":", 1)
    if len(parts) != 2:
        return HarnessAssertionResult(
            "file_contains", False, f"Invalid format: {value} (expected path:content)"
        )
    file_path, content = parts
    target = (workspace / file_path).resolve()
    if not str(target).startswith(str(workspace.resolve())):
        return HarnessAssertionResult(
            "file_contains", False, f"Path '{file_path}' escapes workspace"
        )
    if not target.exists():
        return HarnessAssertionResult(
            "file_contains", False, f"File '{file_path}' not found"
        )
    file_text = target.read_text(encoding="utf-8", errors="replace")
    found = content in file_text
    details = f"'{content}' {'found' if found else 'not found'} in {file_path}"
    return HarnessAssertionResult("file_contains", found, details)


_HANDLERS = {
    "contains": _check_contains,
    "not_contains": _check_not_contains,
    "regex": _check_regex,
    "tool_called": _check_tool_called,
    "file_exists": _check_file_exists,
    "file_contains": _check_file_contains,
}
