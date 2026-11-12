"""Sequential testing: look at the data as often as you like without inflating
the false-positive rate.

Two complementary tools are provided.

1. **Group-sequential boundaries** (Lan-DeMets alpha spending, O'Brien-Fleming or
   Pocock shape). Best when the number/timing of looks is roughly planned.
   Boundaries are computed by exact numerical integration of the joint
   distribution of the score process under H0 (Armitage-McPherson-Rowe recursion).

2. **mSPRT / always-valid inference** (mixture sequential probability ratio test
   with a Gaussian mixing prior, Johari et al.). Valid after *any* number of
   unplanned looks: the always-valid p-value is the running minimum of
   ``1 / Lambda_n`` and the confidence sequence is the inversion of the test.

Everything is expressed in terms of the effect estimate ``theta`` (treatment minus
control) and its sampling variance ``s2``, so binary and continuous metrics share code.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
from scipy import optimize, stats

_VAR_FLOOR = 1e-18


# --------------------------------------------------------------------------- spending
def obf_spending(t, alpha: float):
    """Lan-DeMets O'Brien-Fleming-type spending: very little alpha spent early."""
    t = np.asarray(t, float)
    return 2 * stats.norm.sf(stats.norm.isf(alpha / 2) / np.sqrt(t))


def pocock_spending(t, alpha: float):
    """Lan-DeMets Pocock-type spending: roughly constant boundaries."""
    t = np.asarray(t, float)
    return alpha * np.log(1 + (np.e - 1) * t)


_SPENDING = {"obf": obf_spending, "pocock": pocock_spending}


def _validate_info(info) -> np.ndarray:
    t = np.asarray(info, float)
    if t.ndim != 1 or len(t) == 0:
        raise ValueError("information fractions must be a non-empty 1-D sequence.")
    if (t <= 0).any() or (t > 1 + 1e-9).any() or (np.diff(t) <= 0).any():
        raise ValueError("information fractions must be strictly increasing and within (0, 1].")
    return np.minimum(t, 1.0)


@lru_cache(maxsize=256)
def _bounds(t_key: tuple, alpha: float, spending: str, grid: int) -> tuple:
    t = np.array(t_key)
    cum = _SPENDING[spending](t, alpha)
    inc = np.diff(np.r_[0.0, cum])
    K = len(t)
    c = np.zeros(K)
    c[0] = stats.norm.isf(inc[0] / 2)
    x = w = g = None
    for k in range(K):
        if k > 0:
            dt = t[k] - t[k - 1]
            sd = np.sqrt(dt)

            def crossing(ck: float) -> float:
                up = stats.norm.sf((ck * np.sqrt(t[k]) - x) / sd)
                lo = stats.norm.cdf((-ck * np.sqrt(t[k]) - x) / sd)
                return float(np.sum(w * g * (up + lo)) - inc[k])

            c[k] = optimize.brentq(crossing, 0.3, 14.0, xtol=1e-10)
        if k == K - 1:
            break
        # propagate the sub-density of the score process through the continuation region
        half = c[k] * np.sqrt(t[k])
        xn = np.linspace(-half, half, grid)
        wn = np.full(grid, xn[1] - xn[0])
        wn[[0, -1]] /= 2  # trapezoid weights
        if k == 0:
            gn = stats.norm.pdf(xn, scale=np.sqrt(t[0]))
        else:
            kern = stats.norm.pdf((xn[:, None] - x[None, :]) / sd) / sd
            gn = kern @ (w * g)
        x, w, g = xn, wn, gn
    return tuple(c)


def group_sequential_bounds(info_fractions, alpha: float = 0.05, spending: str = "obf", grid: int = 1200) -> np.ndarray:
    """Two-sided critical z-values at each planned look."""
    if spending not in _SPENDING:
        raise ValueError(f"spending must be one of {list(_SPENDING)}.")
    if not (0 < alpha < 1):
        raise ValueError("alpha must be in (0, 1).")
    t = _validate_info(info_fractions)
    return np.array(_bounds(tuple(np.round(t, 12)), float(alpha), spending, grid))


# --------------------------------------------------------------------------- mSPRT
def msprt_log_lr(theta, s2, tau2: float):
    """log of the mixture likelihood ratio for H0: effect = 0 with a N(0, tau2) prior."""
    theta, s2 = np.asarray(theta, float), np.maximum(np.asarray(s2, float), _VAR_FLOOR)
    return 0.5 * np.log(s2 / (s2 + tau2)) + tau2 * theta**2 / (2 * s2 * (s2 + tau2))


def msprt_pvalues(theta, s2, tau2: float):
    """Always-valid p-values along the last axis (running minimum of 1/Lambda)."""
    p = np.minimum(1.0, np.exp(-msprt_log_lr(theta, s2, tau2)))
    return np.minimum.accumulate(p, axis=-1)


def msprt_conf_seq(theta, s2, tau2: float, alpha: float = 0.05):
    """Confidence sequence (nested by running intersection) at each look."""
    theta, s2 = np.asarray(theta, float), np.maximum(np.asarray(s2, float), _VAR_FLOOR)
    half = np.sqrt(
        2 * s2 * (s2 + tau2) / tau2 * (np.log(1 / alpha) + 0.5 * np.log((s2 + tau2) / s2))
    )
    lo = np.maximum.accumulate(theta - half, axis=-1)
    hi = np.minimum.accumulate(theta + half, axis=-1)
    return lo, hi


def default_tau(scale: float) -> float:
    """Prior sd of the effect: 10% of the metric's scale (baseline rate or sd)."""
    return max(1e-6, 0.1 * float(scale))


# --------------------------------------------------------------------------- evaluation
def analyze_sequence(
    theta, s2_test, s2_ci, info, alpha: float = 0.05, tau: float | None = None,
    spending: str = "obf", scale: float | None = None,
) -> dict:
    """Evaluate a sequence of cumulative looks with every method side by side.

    ``theta``    effect estimate at each look (treatment - control)
    ``s2_test``  sampling variance of theta used for testing (null-pooled for proportions)
    ``s2_ci``    sampling variance used for the confidence sequence
    ``info``     information fraction at each look (cumulative n / planned n)
    """
    theta, s2t, s2c = (np.asarray(a, float) for a in (theta, s2_test, s2_ci))
    K = len(theta)
    info = _validate_info(info)
    if not (len(s2t) == len(s2c) == len(info) == K):
        raise ValueError("All per-look sequences must have the same length.")
    if tau is None:
        # prior sd of the effect: 10% of the metric scale if known, otherwise roughly the
        # effect the final sample size is powered to detect (~2.8 standard errors)
        tau = default_tau(scale) if scale else 2.8 * float(np.sqrt(max(s2t[-1], _VAR_FLOOR)))
    if tau <= 0:
        raise ValueError("tau must be positive.")
    s2t_safe = np.maximum(s2t, _VAR_FLOOR)
    z = theta / np.sqrt(s2t_safe)
    p_naive = 2 * stats.norm.sf(np.abs(z))
    bounds = group_sequential_bounds(info, alpha, spending)
    p_av = msprt_pvalues(theta, s2t_safe, tau**2)
    cs_lo, cs_hi = msprt_conf_seq(theta, s2c, tau**2, alpha)
    gs_reject = np.abs(z) >= bounds
    first = lambda mask: int(np.argmax(mask)) + 1 if mask.any() else None  # noqa: E731
    return {
        "alpha": alpha, "tau": float(tau), "spending": spending,
        "looks": [
            {
                "look": i + 1, "info_fraction": float(info[i]), "theta": float(theta[i]), "z": float(z[i]),
                "naive_p": float(p_naive[i]), "always_valid_p": float(p_av[i]),
                "cs_low": float(cs_lo[i]), "cs_high": float(cs_hi[i]),
                "gs_bound": float(bounds[i]), "gs_reject": bool(gs_reject[i]),
                "msprt_reject": bool(p_av[i] <= alpha), "naive_reject": bool(p_naive[i] <= alpha),
            }
            for i in range(K)
        ],
        "first_look": {
            "naive": first(p_naive <= alpha),
            "group_sequential": first(gs_reject),
            "msprt": first(p_av <= alpha),
        },
        "final": {
            "z": float(z[-1]), "naive_p": float(p_naive[-1]), "always_valid_p": float(p_av[-1]),
            "stopped_gs": bool(gs_reject.any()), "stopped_msprt": bool((p_av <= alpha).any()),
        },
    }


def binary_sequence(n_a, x_a, n_b, x_b) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """theta, null-pooled variance and unpooled variance for cumulative binary data."""
    n_a, x_a, n_b, x_b = (np.asarray(v, float) for v in (n_a, x_a, n_b, x_b))
    if (n_a <= 0).any() or (n_b <= 0).any():
        raise ValueError("Every look needs at least one observation in each arm.")
    if (x_a > n_a).any() or (x_b > n_b).any() or (x_a < 0).any() or (x_b < 0).any():
        raise ValueError("Successes must be between 0 and the sample size.")
    pa, pb = x_a / n_a, x_b / n_b
    pooled = (x_a + x_b) / (n_a + n_b)
    s2_null = pooled * (1 - pooled) * (1 / n_a + 1 / n_b)
    s2_alt = pa * (1 - pa) / n_a + pb * (1 - pb) / n_b
    return pb - pa, s2_null, s2_alt


def continuous_sequence(n_a, mean_a, var_a, n_b, mean_b, var_b):
    n_a, n_b = np.asarray(n_a, float), np.asarray(n_b, float)
    s2 = np.asarray(var_a, float) / n_a + np.asarray(var_b, float) / n_b
    return np.asarray(mean_b, float) - np.asarray(mean_a, float), s2, s2
