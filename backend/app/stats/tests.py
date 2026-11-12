"""Classical two-sample hypothesis tests with confidence intervals.

Convention: arm A is the control, arm B the treatment; every effect is B - A.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy import stats


@dataclass
class ProportionResult:
    p_control: float
    p_treatment: float
    diff: float
    ci_low: float
    ci_high: float
    rel_lift: float | None
    statistic: float
    p_value: float
    cohens_h: float
    test: str = "chi-square"
    df: int = 1


def wilson_interval(x: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """Wilson score interval for a single proportion."""
    if n <= 0:
        raise ValueError("n must be positive.")
    z = stats.norm.isf(alpha / 2)
    p = x / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def two_proportion_test(
    x_control: int, n_control: int, x_treat: int, n_treat: int, alpha: float = 0.05,
) -> ProportionResult:
    """Pearson chi-square test (equivalent to the pooled two-sided z-test) plus a
    Newcombe-Wilson confidence interval for the difference in proportions."""
    for name, x, n in (("control", x_control, n_control), ("treatment", x_treat, n_treat)):
        if n <= 0 or x < 0 or x > n:
            raise ValueError(f"Invalid counts for {name}: {x} successes out of {n}.")
    pa, pb = x_control / n_control, x_treat / n_treat
    table = np.array([[x_control, n_control - x_control], [x_treat, n_treat - x_treat]])
    if (table.sum(axis=0) == 0).any():  # everybody (or nobody) converted: nothing to test
        chi2, p_value = 0.0, 1.0
    else:
        chi2, p_value, _, _ = stats.chi2_contingency(table, correction=False)
    # Newcombe hybrid-score CI for pB - pA
    la, ua = wilson_interval(x_control, n_control, alpha)
    lb, ub = wilson_interval(x_treat, n_treat, alpha)
    diff = pb - pa
    lo = diff - math.sqrt((pb - lb) ** 2 + (ua - pa) ** 2)
    hi = diff + math.sqrt((ub - pb) ** 2 + (pa - la) ** 2)
    h = 2 * math.asin(math.sqrt(pb)) - 2 * math.asin(math.sqrt(pa))
    return ProportionResult(
        pa, pb, diff, lo, hi, (diff / pa) if pa > 0 else None, float(chi2), float(p_value), h
    )


def chi_square_table(table) -> dict:
    """Omnibus chi-square test of independence for an r x c contingency table."""
    t = np.asarray(table, dtype=float)
    t = t[:, t.sum(axis=0) > 0]
    if t.shape[0] < 2 or t.shape[1] < 2:
        return {"statistic": 0.0, "df": 0, "p_value": 1.0}
    chi2, p, dof, _ = stats.chi2_contingency(t, correction=False)
    return {"statistic": float(chi2), "df": int(dof), "p_value": float(p)}


def srm_check(counts, expected_ratios=None) -> dict:
    """Sample-ratio-mismatch test: does the observed split match the planned allocation?"""
    counts = np.asarray(counts, dtype=float)
    ratios = np.ones(len(counts)) if expected_ratios is None else np.asarray(expected_ratios, float)
    expected = counts.sum() * ratios / ratios.sum()
    chi2, p = stats.chisquare(counts, expected)
    return {"statistic": float(chi2), "df": len(counts) - 1, "p_value": float(p), "counts": counts.tolist()}


@dataclass
class MeanResult:
    mean_control: float
    mean_treatment: float
    diff: float
    ci_low: float
    ci_high: float
    rel_lift: float | None
    statistic: float
    df: float
    p_value: float
    cohens_d: float
    test: str = "welch-t"


def welch_t_test_from_stats(
    mean_c: float, sd_c: float, n_c: int, mean_t: float, sd_t: float, n_t: int, alpha: float = 0.05,
) -> MeanResult:
    """Welch's unequal-variance t-test from summary statistics."""
    if n_c < 2 or n_t < 2:
        raise ValueError("Each arm needs at least 2 observations.")
    vc, vt = sd_c**2 / n_c, sd_t**2 / n_t
    diff = mean_t - mean_c
    se = math.sqrt(vc + vt)
    pooled_sd = math.sqrt(((n_c - 1) * sd_c**2 + (n_t - 1) * sd_t**2) / (n_c + n_t - 2))
    d = diff / pooled_sd if pooled_sd > 0 else 0.0
    if se == 0:  # zero variance in both arms
        p = 1.0 if diff == 0 else 0.0
        return MeanResult(mean_c, mean_t, diff, diff, diff, None, 0.0, float(n_c + n_t - 2), p, d)
    t = diff / se
    df = (vc + vt) ** 2 / (vc**2 / (n_c - 1) + vt**2 / (n_t - 1))
    p = 2 * stats.t.sf(abs(t), df)
    crit = stats.t.isf(alpha / 2, df)
    return MeanResult(
        mean_c, mean_t, diff, diff - crit * se, diff + crit * se,
        (diff / mean_c) if mean_c != 0 else None, float(t), float(df), float(p), d,
    )


def welch_t_test(control, treatment, alpha: float = 0.05) -> MeanResult:
    a, b = np.asarray(control, float), np.asarray(treatment, float)
    a, b = a[~np.isnan(a)], b[~np.isnan(b)]
    return welch_t_test_from_stats(
        a.mean(), a.std(ddof=1), len(a), b.mean(), b.std(ddof=1), len(b), alpha
    )
