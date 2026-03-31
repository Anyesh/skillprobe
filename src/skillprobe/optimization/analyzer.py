from dataclasses import dataclass, field
from typing import Any

from skillprobe.parsers import parse_request
from skillprobe.proxy.handler import _extract_response_text
from skillprobe.storage.models import Capture
from skillprobe.testing.assertions import check_assertion, check_when_conditions
from skillprobe.testing.loader import TestSuite


@dataclass
class FailurePattern:
    test_name: str
    assertion_type: str
    assertion_value: str
    failure_rate: float
    evaluated_count: int
    sample_failures: list[str]


def analyze_failures(captures: list[Capture], suite: TestSuite) -> list[FailurePattern]:
    patterns = []
    for tc in suite.tests:
        for assertion in tc.assertions:
            passed = 0
            evaluated = 0
            samples = []
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
                result = check_assertion(assertion, response_text, system_prompt, c.parsed_data)
                if result.passed:
                    passed += 1
                elif len(samples) < 3:
                    samples.append(result.details)

            if evaluated == 0:
                continue
            failure_rate = 1 - (passed / evaluated)
            if failure_rate > 0:
                patterns.append(FailurePattern(
                    test_name=tc.name,
                    assertion_type=assertion.get("type", ""),
                    assertion_value=assertion.get("value", ""),
                    failure_rate=failure_rate,
                    evaluated_count=evaluated,
                    sample_failures=samples,
                ))

    patterns.sort(key=lambda p: p.failure_rate, reverse=True)
    return patterns
