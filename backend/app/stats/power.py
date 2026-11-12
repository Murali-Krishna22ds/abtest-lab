"""Power, sample-size and minimum-detectable-effect (MDE) calculations.

Proportions use the classical Fleiss two-sample formula (unpooled variance under
the alternative, pooled under the null, no continuity correction). Means use the
exact non-central t distribution through statsmodels.

Conventions
-----------
* ``n1`` is the control arm, ``n2 = ratio * n1`` is the treatment arm.
* ``delta = p2 - p1`` (treatment minus control).
"""
from __future__ import annotations

import math

import numpy as np
from scipy import optimize, stats
from statsmodels.stats.power import TTestIndPower

_EPS = 1e-9


def _check_prob(name: str, p: float) -> None:
    if not (0.0 < p < 1.0):
        raise ValueError(f"{name} must be strictly between 0 and 1 (got {p}).")


def _check_design(alpha: float, power: float | None = None, ratio: float = 1.0) -> None:
    if not (0.0 < alpha < 1.0):
        raise ValueError("alpha must be strictly between 0 and 1.")
    if power is not None and not (0.0 < power < 1.0):
        raise ValueError("power must be strictly between 0 and 1.")
    if ratio <= 0:
        raise ValueError("ratio (treatment size / control size) must be positive.")


def _z_alpha(alpha: float, two_sided: bool) -> float:
    return float(stats.norm.isf(alpha / 2 if two_sided else alpha))


def resolve_p2(p1: float, p2: float | None, mde: float | None, relative: bool) -> float:
    """Return the treatment rate from either an explicit ``p2`` or an MDE."""
    _check_prob("baseline rate", p1)
    if (p2 is None) == (mde is None):
        raise ValueError("Provide exactly one of 'p2' (target rate) or 'mde' (effect size).")
    if p2 is None:
        p2 = p1 * (1 + mde) if relative else p1 + mde  # type: ignore[operator]
    _check_prob("treatment rate", p2)
    if math.isclose(p1, p2):
        raise ValueError("Treatment rate equals baseline rate: the effect is zero.")
    return float(p2)


# --------------------------------------------------------------------------- proportions
def sample_size_proportions(
    p1: float, p2: float, alpha: float = 0.05, power: float = 0.8,
    ratio: float = 1.0, two_sided: bool = True,
) -> tuple[int, int]:
    """Smallest (n_control, n_treatment) achieving the requested power."""
    _check_prob("p1", p1)
    _check_prob("p2", p2)
    _check_design(alpha, power, ratio)
    if math.isclose(p1, p2):
        raise ValueError("p1 and p2 are equal: no finite sample size detects a zero effect.")
    za, zb = _z_alpha(alpha, two_sided), float(stats.norm.ppf(power))
    pbar = (p1 + ratio * p2) / (1 + ratio)
    num = za * math.sqrt((1 + 1 / ratio) * pbar * (1 - pbar)) + zb * math.sqrt(
        p1 * (1 - p1) + p2 * (1 - p2) / ratio
    )
    n1 = math.ceil(num**2 / (p2 - p1) ** 2)
    return n1, math.ceil(ratio * n1)


def power_proportions(
    p1: float, p2: float, n1: int, n2: int, alpha: float = 0.05, two_sided: bool = True,
) -> float:
    """Power of the two-proportion z / chi-square test for the given sample sizes."""
    _check_prob("p1", p1)
    _check_prob("p2", p2)
    _check_design(alpha)
    if n1 < 2 or n2 < 2:
        raise ValueError("Each arm needs at least 2 observations.")
    delta = abs(p2 - p1)
    pbar = (n1 * p1 + n2 * p2) / (n1 + n2)
    se0 = math.sqrt(pbar * (1 - pbar) * (1 / n1 + 1 / n2))
    se1 = math.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    za = _z_alpha(alpha, two_sided)
    pw = stats.norm.cdf((delta - za * se0) / se1)
    if two_sided:  # probability of rejecting in the wrong direction (negligible but exact)
        pw += stats.norm.cdf((-delta - za * se0) / se1)
    return float(min(pw, 1.0))


def mde_proportions(
    p1: float, n1: int, n2: int, alpha: float = 0.05, power: float = 0.8,
    two_sided: bool = True, direction: str = "increase",
) -> float:
    """Smallest absolute change in the rate detectable with the given sample sizes."""
    _check_prob("p1", p1)
    _check_design(alpha, power)
    if direction not in {"increase", "decrease"}:
        raise ValueError("direction must be 'increase' or 'decrease'.")
    sign = 1.0 if direction == "increase" else -1.0
    hi = (1 - p1 if sign > 0 else p1) - _EPS

    def gap(d: float) -> float:
        return power_proportions(p1, p1 + sign * d, n1, n2, alpha, two_sided) - power

    if gap(hi) < 0:
        raise ValueError("The requested power is not achievable with this sample size.")
    return float(optimize.brentq(gap, _EPS, hi, xtol=1e-12))


# --------------------------------------------------------------------------- means
def _alt(two_sided: bool) -> str:
    return "two-sided" if two_sided else "larger"


def sample_size_means(
    delta: float, sd: float, alpha: float = 0.05, power: float = 0.8,
    ratio: float = 1.0, two_sided: bool = True,
) -> tuple[int, int]:
    _check_design(alpha, power, ratio)
    if sd <= 0 or delta == 0:
        raise ValueError("sd must be positive and delta non-zero.")
    n1 = TTestIndPower().solve_power(
        effect_size=abs(delta) / sd, alpha=alpha, power=power, ratio=ratio, alternative=_alt(two_sided)
    )
    n1 = math.ceil(float(n1))
    return n1, math.ceil(ratio * n1)


def power_means(
    delta: float, sd: float, n1: int, n2: int, alpha: float = 0.05, two_sided: bool = True,
) -> float:
    _check_design(alpha)
    if sd <= 0 or n1 < 2 or n2 < 2:
        raise ValueError("sd must be positive and each arm needs at least 2 observations.")
    return float(TTestIndPower().power(
        effect_size=abs(delta) / sd, nobs1=n1, alpha=alpha, ratio=n2 / n1, alternative=_alt(two_sided)
    ))


def mde_means(
    sd: float, n1: int, n2: int, alpha: float = 0.05, power: float = 0.8, two_sided: bool = True,
) -> float:
    _check_design(alpha, power)
    d = TTestIndPower().solve_power(
        effect_size=None, nobs1=n1, alpha=alpha, power=power, ratio=n2 / n1, alternative=_alt(two_sided)
    )
    return float(d) * sd


# --------------------------------------------------------------------------- curves
def power_curve_proportions(
    p1: float, p2: float, alpha: float = 0.05, ratio: float = 1.0, two_sided: bool = True,
    n_max: int | None = None, points: int = 40,
) -> list[dict]:
    """Power as a function of control-arm sample size."""
    if n_max is None:
        n_max = int(sample_size_proportions(p1, p2, alpha, 0.95, ratio, two_sided)[0] * 1.1)
    ns = np.unique(np.linspace(max(10, n_max // points), n_max, points).astype(int))
    return [
        {"n_per_arm": int(n), "power": power_proportions(p1, p2, int(n), max(2, math.ceil(ratio * n)), alpha, two_sided)}
        for n in ns
    ]


def power_curve_means(
    delta: float, sd: float, alpha: float = 0.05, ratio: float = 1.0, two_sided: bool = True,
    n_max: int | None = None, points: int = 40,
) -> list[dict]:
    if n_max is None:
        n_max = int(sample_size_means(delta, sd, alpha, 0.95, ratio, two_sided)[0] * 1.1)
    ns = np.unique(np.linspace(max(10, n_max // points), n_max, points).astype(int))
    return [
        {"n_per_arm": int(n), "power": power_means(delta, sd, int(n), max(2, math.ceil(ratio * n)), alpha, two_sided)}
        for n in ns
    ]


# --------------------------------------------------------------------------- planning
def plan_proportions(
    baseline: float, mde: float | None = None, target: float | None = None, relative: bool = False,
    alpha: float = 0.05, power: float = 0.8, ratio: float = 1.0, two_sided: bool = True,
    n_comparisons: int = 1, daily_traffic: int | None = None,
) -> dict:
    """Sample-size plan for a conversion-rate test, with optional Bonferroni adjustment."""
    if n_comparisons < 1:
        raise ValueError("n_comparisons must be >= 1.")
    p2 = resolve_p2(baseline, target, mde, relative)
    alpha_adj = alpha / n_comparisons
    n1, n2 = sample_size_proportions(baseline, p2, alpha_adj, power, ratio, two_sided)
    achieved = power_proportions(baseline, p2, n1, n2, alpha_adj, two_sided)
    out = {
        "metric": "proportion", "baseline": baseline, "target": p2,
        "absolute_effect": p2 - baseline, "relative_effect": (p2 - baseline) / baseline,
        "alpha": alpha, "alpha_adjusted": alpha_adj, "power": power, "achieved_power": achieved,
        "ratio": ratio, "two_sided": two_sided, "n_comparisons": n_comparisons,
        "n_control": n1, "n_treatment": n2, "n_total": n1 + n2,
        "curve": power_curve_proportions(baseline, p2, alpha_adj, ratio, two_sided),
    }
    if daily_traffic:
        out["days_needed"] = math.ceil((n1 + n2) / daily_traffic)
    return out


def plan_means(
    delta: float, sd: float, alpha: float = 0.05, power: float = 0.8, ratio: float = 1.0,
    two_sided: bool = True, n_comparisons: int = 1, daily_traffic: int | None = None,
) -> dict:
    if n_comparisons < 1:
        raise ValueError("n_comparisons must be >= 1.")
    alpha_adj = alpha / n_comparisons
    n1, n2 = sample_size_means(delta, sd, alpha_adj, power, ratio, two_sided)
    out = {
        "metric": "mean", "delta": delta, "sd": sd, "standardized_effect": abs(delta) / sd,
        "alpha": alpha, "alpha_adjusted": alpha_adj, "power": power,
        "achieved_power": power_means(delta, sd, n1, n2, alpha_adj, two_sided),
        "ratio": ratio, "two_sided": two_sided, "n_comparisons": n_comparisons,
        "n_control": n1, "n_treatment": n2, "n_total": n1 + n2,
        "curve": power_curve_means(delta, sd, alpha_adj, ratio, two_sided),
    }
    if daily_traffic:
        out["days_needed"] = math.ceil((n1 + n2) / daily_traffic)
    return out
