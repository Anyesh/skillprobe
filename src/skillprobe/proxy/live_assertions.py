import collections
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from skillprobe.testing.assertions import check_assertion, check_when_conditions
from skillprobe.testing.loader import TestSuite

log = logging.getLogger("skillprobe.proxy")


@dataclass
class LiveAssertionResult:
    test_name: str
    capture_id: int
    passed: bool
    skipped: bool
    details: list[str]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class LiveAssertionEvaluator:
    def __init__(self, suite: TestSuite):
        self.suite = suite
        self.log: collections.deque[LiveAssertionResult] = collections.deque(maxlen=500)

    def evaluate(
        self,
        capture_id: int,
        response_text: str,
        system_prompt: str,
        parsed_data: dict[str, Any] | None = None,
    ) -> list[LiveAssertionResult]:
        results = []
        for tc in self.suite.tests:
            if not check_when_conditions(tc.when, response_text, system_prompt):
                result = LiveAssertionResult(
                    test_name=tc.name,
                    capture_id=capture_id,
                    passed=False,
                    skipped=True,
                    details=[],
                )
                results.append(result)
                self.log.append(result)
                log.info("           [SKIP] %s", tc.name)
                continue

            assertion_results = [
                check_assertion(a, response_text, system_prompt, parsed_data)
                for a in tc.assertions
            ]
            all_passed = all(r.passed for r in assertion_results)
            failed_details = [r.details for r in assertion_results if not r.passed]

            result = LiveAssertionResult(
                test_name=tc.name,
                capture_id=capture_id,
                passed=all_passed,
                skipped=False,
                details=failed_details,
            )
            results.append(result)
            self.log.append(result)

            if all_passed:
                log.info("           [PASS] %s", tc.name)
            else:
                log.info("           [FAIL] %s -- %s", tc.name, "; ".join(failed_details))

        return results
