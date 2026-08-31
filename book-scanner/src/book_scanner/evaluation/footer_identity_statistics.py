"""Small dependency-free statistical helpers for V3-A.4 offline replay."""

from __future__ import annotations

import math
import random
from typing import Sequence


def independent_no_match_probability(match_probability: float, n: int) -> float:
    _probability(match_probability)
    _positive_int(n)
    return (1.0 - match_probability) ** n


def independent_any_match_probability(collision_probability: float, n: int) -> float:
    _probability(collision_probability)
    _positive_int(n)
    return 1.0 - (1.0 - collision_probability) ** n


def wilson_interval(successes: int, trials: int, confidence: float = 0.95) -> tuple[float, float]:
    if trials <= 0 or not 0 <= successes <= trials:
        raise ValueError("successes/trials are invalid")
    if confidence != 0.95:
        raise ValueError("only the pre-registered 95% Wilson interval is supported")
    z = 1.959963984540054
    estimate = successes / trials
    denominator = 1.0 + z * z / trials
    center = (estimate + z * z / (2.0 * trials)) / denominator
    radius = z * math.sqrt(estimate * (1.0 - estimate) / trials + z * z / (4.0 * trials * trials)) / denominator
    return max(0.0, center - radius), min(1.0, center + radius)


def zero_error_upper_bound(trials: int, alpha: float = 0.05) -> float:
    _positive_int(trials)
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be in (0, 1)")
    return 1.0 - alpha ** (1.0 / trials)


def lag_autocorrelations(values: Sequence[bool | int | float], max_lag: int = 10) -> tuple[float, ...]:
    if len(values) < 2:
        return ()
    if max_lag <= 0:
        raise ValueError("max_lag must be positive")
    numeric = [float(item) for item in values]
    mean = sum(numeric) / len(numeric)
    denominator = sum((item - mean) ** 2 for item in numeric)
    if denominator <= 1e-12:
        return tuple(1.0 for _ in range(min(max_lag, len(numeric) - 1)))
    result = []
    for lag in range(1, min(max_lag, len(numeric) - 1) + 1):
        numerator = sum((numeric[index] - mean) * (numeric[index + lag] - mean) for index in range(len(numeric) - lag))
        result.append(max(-1.0, min(1.0, numerator / denominator)))
    return tuple(result)


def effective_sample_size(values: Sequence[bool | int | float], max_lag: int = 10) -> float:
    n = len(values)
    if n == 0:
        return 0.0
    correlations = lag_autocorrelations(values, max_lag)
    positive_sum = 0.0
    for correlation in correlations:
        if correlation <= 0.0:
            break
        positive_sum += correlation
    return max(1.0, min(float(n), n / (1.0 + 2.0 * positive_sum)))


def block_bootstrap_mean_interval(
    values: Sequence[bool | int | float],
    *,
    block_size: int,
    iterations: int = 2000,
    seed: int = 3404,
) -> tuple[float, float]:
    if not values:
        raise ValueError("values must be non-empty")
    _positive_int(block_size)
    _positive_int(iterations)
    numeric = [float(item) for item in values]
    block_size = min(block_size, len(numeric))
    starts = list(range(0, len(numeric) - block_size + 1))
    generator = random.Random(seed)
    estimates = []
    for _ in range(iterations):
        sample: list[float] = []
        while len(sample) < len(numeric):
            start = generator.choice(starts)
            sample.extend(numeric[start : start + block_size])
        sample = sample[: len(numeric)]
        estimates.append(sum(sample) / len(sample))
    estimates.sort()
    low = estimates[max(0, round(iterations * 0.025) - 1)]
    high = estimates[min(iterations - 1, round(iterations * 0.975) - 1)]
    return low, high


def _probability(value: float) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError("probability must be in [0, 1]")


def _positive_int(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("value must be a positive integer")
