from dataclasses import dataclass
from typing import Any

from skillprobe.parsers import parse_request
from skillprobe.proxy.handler import _extract_response_text
from skillprobe.storage.models import Capture
from skillprobe.testing.assertions import check_assertion, check_when_conditions
from skillprobe.testing.loader import TestSuite


@dataclass
class SessionResult:
    session: str
    test_results: dict[str, float]
    capture_count: int


def compute_session_results(captures: list[Capture], suite: TestSuite) -> SessionResult:
    session_name = captures[0].session or "unnamed" if captures else "empty"
    test_results: dict[str, float] = {}

    for tc in suite.tests:
        passed = 0
        evaluated = 0
        for c in captures:
            if not c.response_body:
                continue
            parsed = parse_request(c.path, c.request_body)
            system_prompt = parsed.system_prompt if parsed else ""
            provider = parsed.provider if parsed else c.provider
            response_text = _extract_response_text(c.response_body, provider)
            if not response_text:
                continue
            if not check_when_conditions(tc.when, response_text, system_prompt):
                continue
            evaluated += 1
            results = [check_assertion(a, response_text, system_prompt, parsed_data=c.parsed_data) for a in tc.assertions]
            if all(r.passed for r in results):
                passed += 1
        rate = passed / evaluated if evaluated > 0 else 0.0
        test_results[tc.name] = rate

    return SessionResult(session=session_name, test_results=test_results, capture_count=len(captures))


def format_diff(results: list[SessionResult]) -> str:
    if len(results) < 2:
        return "Need at least 2 sessions to diff."

    all_tests = []
    for r in results:
        for name in r.test_results:
            if name not in all_tests:
                all_tests.append(name)

    lines = []
    session_names = [r.session for r in results]
    header = f"  {'Test':<35}"
    for name in session_names:
        header += f" {name:>10}"
    if len(results) == 2:
        header += f" {'Delta':>10}"
    lines.append(header)
    lines.append("  " + "-" * (35 + 12 * len(results) + (12 if len(results) == 2 else 0)))

    for test_name in all_tests:
        row = f"  {test_name:<35}"
        rates = []
        for r in results:
            rate = r.test_results.get(test_name, 0.0)
            rates.append(rate)
            row += f" {rate:>9.0%}"
        if len(results) == 2:
            delta = rates[1] - rates[0]
            if delta > 0:
                row += f" {delta:>+9.0%} improved"
            elif delta < 0:
                row += f" {delta:>+9.0%} regressed"
            else:
                row += f" {'--':>10}"
        lines.append(row)

    lines.append("")
    for r in results:
        avg = sum(r.test_results.values()) / len(r.test_results) if r.test_results else 0
        lines.append(f"  {r.session}: {r.capture_count} captures, avg pass rate {avg:.0%}")

    return "\n".join(lines)
