"""Power, sample-size and minimum-detectable-effect calculations.

Two-sample designs only (control vs treatment), with an allocation ratio
``ratio = n_treatment / n_control``. Effects are always signed as treatment minus control.

* Proportions use the normal approximation (pooled variance under H0, unpooled under H1),
  followed by a verification loop so the reported n really reaches the requested power.
* Means use the exact noncentral-t power, switching to the normal approximation when the
  degrees of freedom are large (the two agree to many digits and the normal path is much faster).
"""
from __future__ import annotations

import math
from typing import Literal

import numpy as np
from scipy import optimize, stats

from ..errors import AnalysisError

Alternative = Literal["two-sided", "greater", "less"]

_LARGE_DF = 2000  # beyond this the noncentral t is indistinguishable from the normal approximation
_MAX_N = 50_000_000


def _crit(alpha: float, alternative: Alternative) -> float:
    return float(stats.norm.isf(alpha / 2 if alternative == "two-sided" else alpha))


# --------------------------------------------------------------------------- proportions
def power_two_proportions(
    p1: float, p2: float, n1: float, n2: float, alpha: float = 0.05, alternative: Alternative = "two-sided"
) -> float:
    """Power of the two-proportion z-test when the true rates are p1 (control) and p2 (treatment)."""
    if n1 <= 0 or n2 <= 0:
        return 0.0
    delta = p2 - p1
    pbar = (n1 * p1 + n2 * p2) / (n1 + n2)
    se0 = math.sqrt(max(pbar * (1 - pbar), 1e-300) * (1 / n1 + 1 / n2))
    se1 = math.sqrt(max(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2, 1e-300))
    z = _crit(alpha, alternative)
    upper = stats.norm.cdf((delta - z * se0) / se1)
    lower = stats.norm.cdf((-delta - z * se0) / se1)
    if alternative == "two-sided":
        return float(upper + lower)
    return float(upper if alternative == "greater" else lower)


def sample_size_two_proportions(
    p1: float,
    p2: float,
    alpha: float = 0.05,
    power: float = 0.8,
    ratio: float = 1.0,
    alternative: Alternative = "two-sided",
) -> tuple[int, int, float]:
    """Return (n_control, n_treatment, achieved_power)."""
    if p1 == p2:
        raise AnalysisError("The control and treatment rates are identical, so no sample size can detect the effect.")
    if alternative == "greater" and p2 < p1 or alternative == "less" and p2 > p1:
        raise AnalysisError("The effect has the opposite sign to the one-sided alternative.")
    za, zb = _crit(alpha, alternative), float(stats.norm.ppf(power))
    k = ratio
    pbar = (p1 + k * p2) / (1 + k)
    num = (za * math.sqrt((1 + 1 / k) * pbar * (1 - pbar)) + zb * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2) / k)) ** 2
    n1 = max(2, math.ceil(num / (p2 - p1) ** 2))
    if n1 > _MAX_N:
        raise AnalysisError("The required sample size exceeds 50 million per group; the effect is too small to be practical.")
    # The closed form is an approximation; step up until the exact-normal power clears the target.
    for _ in range(10_000):
        n2 = math.ceil(k * n1)
        achieved = power_two_proportions(p1, p2, n1, n2, alpha, alternative)
        if achieved >= power:
            return n1, n2, achieved
        n1 += max(1, n1 // 1000)
    raise AnalysisError("Could not converge on a sample size.")  # pragma: no cover


def mde_two_proportions(
    p1: float, n1: int, n2: int, alpha: float = 0.05, power: float = 0.8, alternative: Alternative = "two-sided"
) -> float:
    """Smallest absolute lift in the treatment rate detectable with the given sample sizes."""
    sign = -1.0 if alternative == "less" else 1.0
    lo, hi = 1e-9, (p1 if sign < 0 else 1 - p1) - 1e-9
    if hi <= lo:
        raise AnalysisError("The baseline rate leaves no room for the requested effect direction.")
    f = lambda d: power_two_proportions(p1, p1 + sign * d, n1, n2, alpha, alternative) - power  # noqa: E731
    if f(hi) < 0:
        raise AnalysisError("These sample sizes cannot reach the requested power for any effect on this baseline.")
    return float(optimize.brentq(f, lo, hi, xtol=1e-10))


# --------------------------------------------------------------------------- means
def _nct_tails(tc: float, df: float, nc: float) -> tuple[float, float]:
    """P(T > tc) and P(T < -tc) for T ~ noncentral t. SciPy's nct occasionally returns NaN for large
    noncentrality; fall back to a normal tail around the exact t critical value in that case."""
    upper, lower = float(stats.nct.sf(tc, df, nc)), float(stats.nct.cdf(-tc, df, nc))
    if not (math.isfinite(upper) and math.isfinite(lower)):
        upper, lower = float(stats.norm.sf(tc - nc)), float(stats.norm.cdf(-tc - nc))
    return upper, lower


def power_two_sample_t(
    d: float, n1: float, n2: float, alpha: float = 0.05, alternative: Alternative = "two-sided"
) -> float:
    """Power of the equal-variance two-sample t-test for standardised effect ``d`` (treatment - control)."""
    if n1 < 2 or n2 < 2:
        return 0.0
    df = n1 + n2 - 2
    nc = d * math.sqrt(n1 * n2 / (n1 + n2))
    if df > _LARGE_DF:
        z = _crit(alpha, alternative)
        upper, lower = stats.norm.sf(z - nc), stats.norm.cdf(-z - nc)
    else:
        tc = stats.t.isf(alpha / 2 if alternative == "two-sided" else alpha, df)
        upper, lower = _nct_tails(tc, df, nc)
    if alternative == "two-sided":
        return float(upper + lower)
    return float(upper if alternative == "greater" else lower)


def sample_size_two_means(
    d: float, alpha: float = 0.05, power: float = 0.8, ratio: float = 1.0, alternative: Alternative = "two-sided"
) -> tuple[int, int, float]:
    """Return (n_control, n_treatment, achieved_power) for standardised effect ``d``."""
    if d == 0:
        raise AnalysisError("An effect of zero cannot be detected; choose a non-zero minimum effect.")
    if alternative == "greater" and d < 0 or alternative == "less" and d > 0:
        raise AnalysisError("The effect has the opposite sign to the one-sided alternative.")
    za, zb = _crit(alpha, alternative), float(stats.norm.ppf(power))
    n1 = max(2, math.ceil((1 + 1 / ratio) * ((za + zb) / abs(d)) ** 2))
    if n1 > _MAX_N:
        raise AnalysisError("The required sample size exceeds 50 million per group; the effect is too small to be practical.")

    def pw(n: int) -> float:
        return power_two_sample_t(d, n, math.ceil(ratio * n), alpha, alternative)

    # Walk to the smallest n that meets the target (start is within a few units of the answer).
    while pw(n1) < power:
        n1 += max(1, n1 // 500)
    while n1 > 2 and pw(n1 - 1) >= power:
        n1 -= 1
    n2 = math.ceil(ratio * n1)
    return n1, n2, pw(n1)


def mde_two_means(
    n1: int, n2: int, alpha: float = 0.05, power: float = 0.8, alternative: Alternative = "two-sided"
) -> float:
    """Smallest standardised effect (|d|) detectable with the given sample sizes."""
    sign = -1.0 if alternative == "less" else 1.0
    f = lambda d: power_two_sample_t(sign * d, n1, n2, alpha, alternative) - power  # noqa: E731
    hi = 1.0
    while f(hi) < 0 and hi < 1e3:
        hi *= 2
    return float(optimize.brentq(f, 1e-9, hi, xtol=1e-10))


# --------------------------------------------------------------------------- curves
def _grid(n_required: int, points: int = 25) -> np.ndarray:
    n = np.unique(np.linspace(max(2, n_required * 0.1), n_required * 1.8, points).round().astype(int))
    return n[n >= 2]


def power_curve_proportions(
    p1: float, p2: float, n_required: int, ratio: float, alpha: float, alternative: Alternative
) -> list[dict]:
    return [
        {"n_per_group": int(n), "power": power_two_proportions(p1, p2, n, math.ceil(ratio * n), alpha, alternative)}
        for n in _grid(n_required)
    ]


def power_curve_means(d: float, n_required: int, ratio: float, alpha: float, alternative: Alternative) -> list[dict]:
    return [
        {"n_per_group": int(n), "power": power_two_sample_t(d, n, math.ceil(ratio * n), alpha, alternative)}
        for n in _grid(n_required)
    ]
