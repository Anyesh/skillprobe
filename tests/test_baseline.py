import pytest

from skillprobe.baseline import (
    AssertionBaseline,
    BaselineClassification,
    classify_baseline,
)


def _mk(solo_a, solo_b, combined, total=10):
    return AssertionBaseline(
        assertion_index=0,
        assertion_type="regex",
        assertion_value="x",
        solo_a_passed=solo_a,
        solo_b_passed=solo_b,
        combined_passed=combined,
        total_runs=total,
    )


class TestClassifyBaseline:
    def test_ok_when_all_three_pass_equally(self):
        a = _mk(solo_a=9, solo_b=9, combined=9)
        assert classify_baseline(a, margin=0.15) == BaselineClassification.OK

    def test_regression_when_combined_drops_below_both_lowers(self):
        a = _mk(solo_a=10, solo_b=10, combined=3)
        assert classify_baseline(a, margin=0.15) == BaselineClassification.REGRESSION

    def test_shared_failure_when_both_solos_are_below_half(self):
        a = _mk(solo_a=2, solo_b=3, combined=1)
        assert (
            classify_baseline(a, margin=0.15) == BaselineClassification.SHARED_FAILURE
        )

    def test_flaky_when_drop_is_small(self):
        a = _mk(solo_a=10, solo_b=10, combined=8)
        assert classify_baseline(a, margin=0.15) == BaselineClassification.FLAKY

    def test_ok_when_combined_matches_solo(self):
        a = _mk(solo_a=8, solo_b=9, combined=8)
        assert classify_baseline(a, margin=0.15) == BaselineClassification.OK

    def test_regression_respects_tighter_margin(self):
        a = _mk(solo_a=10, solo_b=10, combined=7)
        assert classify_baseline(a, margin=0.05) == BaselineClassification.REGRESSION

    def test_flaky_at_larger_margin(self):
        a = _mk(solo_a=10, solo_b=10, combined=7)
        assert classify_baseline(a, margin=0.30) == BaselineClassification.FLAKY

    def test_shared_failure_takes_precedence_over_regression(self):
        a = _mk(solo_a=2, solo_b=2, combined=0)
        assert (
            classify_baseline(a, margin=0.15) == BaselineClassification.SHARED_FAILURE
        )
