"""Data and Monte-Carlo simulators used for demos, validation and benchmarks."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from . import corrections as cx
from . import sequential as sq

_START = pd.Timestamp("2026-01-05")


# --------------------------------------------------------------------------- A/B data
def simulate_ab(
    n_total: int = 10_000, baseline: float = 0.10, rel_lift: float = 0.10, n_variants: int = 2,
    metric: str = "binary", sd: float = 10.0, days: int = 14, seed: int | None = 0,
) -> pd.DataFrame:
    """Randomised experiment with ``n_variants`` arms (control + treatments).

    Every treatment arm shares the same true relative lift. Timestamps are spread over
    ``days`` so the data can be replayed for sequential testing.
    """
    if n_total < 2 * n_variants:
        raise ValueError("n_total is too small for the number of variants.")
    if n_variants < 2 or n_variants > 6:
        raise ValueError("n_variants must be between 2 and 6.")
    if metric not in {"binary", "continuous"}:
        raise ValueError("metric must be 'binary' or 'continuous'.")
    rng = np.random.default_rng(seed)
    arms = np.array(["control"] + [f"variant_{chr(97 + i)}" for i in range(n_variants - 1)])
    assign = rng.permutation(np.arange(n_total) % n_variants)  # exactly balanced
    variant = arms[assign]
    treated = assign > 0
    ts = _START + pd.to_timedelta(np.sort(rng.uniform(0, days * 86400, n_total)), unit="s")
    df = pd.DataFrame({"user_id": [f"u{i:07d}" for i in range(n_total)], "timestamp": ts, "variant": variant})
    if metric == "binary":
        p = np.where(treated, baseline * (1 + rel_lift), baseline)
        if (p >= 1).any() or baseline <= 0:
            raise ValueError("baseline * (1 + rel_lift) must stay below 1 and baseline must be positive.")
        df["converted"] = rng.random(n_total) < p
    else:
        df["value"] = rng.normal(baseline * np.where(treated, 1 + rel_lift, 1.0), sd)
    return df


# --------------------------------------------------------------------------- peeking
def simulate_peeking(
    baseline: float = 0.10, rel_lift: float = 0.0, n_max: int = 10_000, n_looks: int = 10,
    alpha: float = 0.05, sims: int = 2000, tau: float | None = None, seed: int | None = 0,
) -> dict:
    """Compare false-positive (rel_lift=0) or power (rel_lift>0) of four decision rules
    when the experimenter peeks ``n_looks`` times.

    * ``fixed_horizon``    test once at the end (the textbook procedure)
    * ``naive_peeking``    stop at the first look with p < alpha  (invalid!)
    * ``group_sequential`` O'Brien-Fleming alpha spending
    * ``msprt``            always-valid mixture SPRT
    """
    if n_looks < 2 or n_looks > 50:
        raise ValueError("n_looks must be between 2 and 50.")
    if not (0 < baseline < 1) or not (0 < baseline * (1 + rel_lift) < 1):
        raise ValueError("baseline and baseline*(1+rel_lift) must lie in (0, 1).")
    if sims < 100 or n_max < 2 * n_looks:
        raise ValueError("Need sims >= 100 and n_max >= 2 * n_looks.")
    rng = np.random.default_rng(seed)
    info = np.arange(1, n_looks + 1) / n_looks
    n_k = np.maximum(1, np.round(info * n_max)).astype(int)
    inc = np.diff(np.r_[0, n_k])
    pb_true = baseline * (1 + rel_lift)
    xa = np.cumsum(rng.binomial(inc, baseline, size=(sims, n_looks)), axis=1)
    xb = np.cumsum(rng.binomial(inc, pb_true, size=(sims, n_looks)), axis=1)
    theta, s2_null, _ = sq.binary_sequence(n_k, xa, n_k, xb)
    z = theta / np.sqrt(np.maximum(s2_null, 1e-18))
    za = stats.norm.isf(alpha / 2)
    tau = tau if tau is not None else sq.default_tau(baseline)
    bounds = sq.group_sequential_bounds(info, alpha, "obf")
    p_av = sq.msprt_pvalues(theta, s2_null, tau**2)

    masks = {
        "naive_peeking": np.abs(z) > za,
        "group_sequential": np.abs(z) >= bounds,
        "msprt": p_av <= alpha,
    }
    out = {
        "fixed_horizon": {"reject_rate": float((np.abs(z[:, -1]) > za).mean()), "avg_sample_fraction": 1.0}
    }
    for name, m in masks.items():
        hit = m.any(axis=1)
        first = np.argmax(m, axis=1)
        frac = np.where(hit, info[first], 1.0)
        out[name] = {"reject_rate": float(hit.mean()), "avg_sample_fraction": float(frac.mean())}
    se = {k: float(np.sqrt(v["reject_rate"] * (1 - v["reject_rate"]) / sims)) for k, v in out.items()}
    for k in out:
        out[k]["mc_std_error"] = se[k]
    return {
        "scenario": "null (no true effect)" if rel_lift == 0 else f"true relative lift {rel_lift:+.1%}",
        "is_null": rel_lift == 0, "alpha": alpha, "n_looks": n_looks, "n_max_per_arm": n_max,
        "sims": sims, "tau": float(tau), "methods": out,
    }


# --------------------------------------------------------------------------- multiple testing
def simulate_multiple_testing(
    m: int = 20, m_true: int = 5, effect_z: float = 3.0, alpha: float = 0.05, sims: int = 4000,
    seed: int | None = 0,
) -> dict:
    """Family-wise error rate, false discovery rate and power for each correction."""
    if not (1 <= m <= 1000) or not (0 <= m_true <= m):
        raise ValueError("Need 1 <= m <= 1000 and 0 <= m_true <= m.")
    rng = np.random.default_rng(seed)
    mu = np.zeros(m)
    mu[:m_true] = effect_z
    p = 2 * stats.norm.sf(np.abs(rng.normal(mu, 1.0, size=(sims, m))))
    is_null = np.arange(m) >= m_true
    out = {}
    for method in cx.METHODS:
        rej = cx.adjust_pvalues(p, method) <= alpha
        v = (rej & is_null).sum(axis=1)  # false rejections
        r = rej.sum(axis=1)
        out[method] = {
            "fwer": float((v > 0).mean()),
            "fdr": float((v / np.maximum(r, 1)).mean()),
            "power": float((rej[:, ~is_null].mean()) if m_true else 0.0),
        }
    return {"m": m, "m_true": m_true, "effect_z": effect_z, "alpha": alpha, "sims": sims, "methods": out}


# --------------------------------------------------------------------------- observational
def simulate_observational(
    n: int = 5000, true_effect: float = 2.0, confounding: float = 1.0, seed: int | None = 0,
) -> pd.DataFrame:
    """Observational data where treatment uptake depends on the same covariates that drive
    the outcome. The *naive* difference in means is therefore biased upward; the true
    average treatment effect is ``true_effect`` by construction."""
    if n < 200:
        raise ValueError("n must be at least 200.")
    rng = np.random.default_rng(seed)
    age = rng.normal(40, 10, n)
    income = rng.lognormal(10.5, 0.5, n)
    engagement = rng.normal(0, 1, n)
    plan = rng.choice(["free", "trial", "pro"], n, p=[0.5, 0.3, 0.2])
    za, zi = (age - 40) / 10, (np.log(income) - 10.5) / 0.5
    logit = -0.4 + confounding * (0.5 * za + 0.3 * zi + 0.8 * engagement + 0.6 * (plan == "pro"))
    treated = rng.random(n) < 1 / (1 + np.exp(-logit))
    y = (
        50 + true_effect * treated + 2.0 * za + 1.5 * zi + 4.0 * engagement
        + 3.0 * (plan == "pro") + rng.normal(0, 4, n)
    )
    return pd.DataFrame({
        "user_id": [f"u{i:06d}" for i in range(n)], "age": age.round(1), "income": income.round(0),
        "engagement": engagement.round(3), "plan": plan, "treated": treated.astype(int), "outcome": y.round(3),
    })


# --------------------------------------------------------------------------- panel
def simulate_panel(
    n_units: int = 30, n_periods: int = 40, n_treated: int = 5, intervention_period: int = 28,
    true_effect: float = 5.0, seed: int | None = 0,
) -> pd.DataFrame:
    """Weekly unit x time panel for difference-in-differences and synthetic control.

    Units share common time factors with unit-specific loadings, so a convex combination
    of control units can reproduce a treated unit (the synthetic-control assumption) and
    trends are approximately parallel. Treated units receive a constant ``true_effect``
    from ``intervention_period`` onwards."""
    if not (1 <= n_treated < n_units) or not (4 <= intervention_period <= n_periods - 2):
        raise ValueError("Need 1 <= n_treated < n_units and 4 <= intervention_period <= n_periods - 2.")
    rng = np.random.default_rng(seed)
    t = np.arange(n_periods)
    f1 = 0.15 * t + 3 * np.sin(2 * np.pi * t / 13)  # trend + seasonality
    f2 = np.cumsum(rng.normal(0, 1, n_periods))  # random walk
    load1, load2 = rng.normal(1, 0.2, n_units), rng.normal(0, 0.5, n_units)
    level = rng.normal(50, 8, n_units)
    y = level[:, None] + load1[:, None] * f1[None, :] + load2[:, None] * f2[None, :] + rng.normal(0, 1, (n_units, n_periods))
    treated = np.arange(n_units) < n_treated
    post = t >= intervention_period
    y = y + true_effect * treated[:, None] * post[None, :]
    rows = pd.DataFrame({
        "unit": np.repeat([f"U{i + 1:02d}" for i in range(n_units)], n_periods),
        "date": np.tile(_START + pd.to_timedelta(7 * t, unit="D"), n_units),
        "group": np.repeat(np.where(treated, "treated", "control"), n_periods),
        "outcome": y.ravel().round(3),
    })
    return rows
