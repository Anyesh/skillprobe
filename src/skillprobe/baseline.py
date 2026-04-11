from dataclasses import dataclass, field
from enum import Enum

from skillprobe.measure import wilson_confidence_interval


class BaselineClassification(Enum):
    OK = "ok"
    REGRESSION = "regression"
    SHARED_FAILURE = "shared_failure"
    FLAKY = "flaky"


@dataclass
class AssertionBaseline:
    assertion_index: int
    assertion_type: str
    assertion_value: str
    solo_a_passed: int
    solo_b_passed: int
    combined_passed: int
    total_runs: int
    solo_a_skills_activated: list[str] = field(default_factory=list)
    solo_b_skills_activated: list[str] = field(default_factory=list)
    combined_skills_activated: list[str] = field(default_factory=list)


@dataclass
class ScenarioBaseline:
    scenario_name: str
    prompt: str
    pairing_label: str
    per_assertion: list[AssertionBaseline]


def classify_baseline(
    assertion: AssertionBaseline, margin: float
) -> BaselineClassification:
    total = assertion.total_runs
    if total == 0:
        return BaselineClassification.OK

    solo_a_rate = assertion.solo_a_passed / total
    solo_b_rate = assertion.solo_b_passed / total
    combined_rate = assertion.combined_passed / total

    if solo_a_rate < 0.5 and solo_b_rate < 0.5:
        return BaselineClassification.SHARED_FAILURE

    min_solo_rate = min(solo_a_rate, solo_b_rate)
    raw_drop = min_solo_rate - combined_rate

    comb_lo, comb_hi = wilson_confidence_interval(assertion.combined_passed, total)
    ci_half = (comb_hi - comb_lo) / 2

    if raw_drop - margin > ci_half:
        return BaselineClassification.REGRESSION

    if combined_rate < min_solo_rate:
        return BaselineClassification.FLAKY

    return BaselineClassification.OK
