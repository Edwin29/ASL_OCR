from __future__ import annotations

import pytest

from book_scanner.evaluation.footer_identity_statistics import (
    block_bootstrap_mean_interval,
    effective_sample_size,
    independent_any_match_probability,
    independent_no_match_probability,
    lag_autocorrelations,
    wilson_interval,
    zero_error_upper_bound,
)


def test_pre_registered_independence_reference_values():
    assert independent_no_match_probability(0.5, 10) == pytest.approx(0.0009765625)
    assert independent_no_match_probability(0.5, 14) == pytest.approx(0.00006103515625)
    assert independent_any_match_probability(0.01, 10) == pytest.approx(1.0 - 0.99**10)


def test_zero_errors_do_not_report_zero_probability():
    low, high = wilson_interval(0, 10)
    assert low == 0.0
    assert high > 0.0
    assert zero_error_upper_bound(10) > 0.0


def test_perfectly_correlated_sequence_has_small_effective_n():
    values = [1] * 20
    assert lag_autocorrelations(values, 5) == (1.0,) * 5
    assert effective_sample_size(values, 5) < 2.0


def test_block_bootstrap_is_deterministic():
    values = [0, 0, 1, 1, 0, 1, 1, 1]
    first = block_bootstrap_mean_interval(values, block_size=2, iterations=200, seed=7)
    second = block_bootstrap_mean_interval(values, block_size=2, iterations=200, seed=7)
    assert first == second
    assert 0.0 <= first[0] <= first[1] <= 1.0
