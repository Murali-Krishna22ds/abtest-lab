"""Synthetic control (Abadie-Diamond-Hainmueller) with placebo-in-space inference.

A weighted average of untreated "donor" units (weights >= 0, summing to 1) is fitted to the
treated unit's pre-intervention outcomes. The post-intervention gap between the treated
unit and its synthetic twin is the estimated effect. Inference compares that gap's
post/pre RMSPE ratio with the same statistic for every donor treated as a placebo.

Neither DoWhy nor EconML ship a classical synthetic-control estimator, so the optimiser
(constrained least squares via SLSQP) is implemented here.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import optimize

from . import common as cm

MIN_PRE = 3
MIN_DONORS = 2
MAX_PLACEBOS = 100


def _weights(y1: np.ndarray, Y0: np.ndarray) -> np.ndarray:
    J = Y0.shape[1]
    scale = max(float(np.std(y1)), 1e-9)
    A, b = Y0 / scale, y1 / scale
    res = optimize.minimize(
        lambda w: float(np.sum((b - A @ w) ** 2)), np.full(J, 1.0 / J),
        jac=lambda w: -2 * A.T @ (b - A @ w), bounds=[(0.0, 1.0)] * J,
        constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1.0, "jac": lambda w: np.ones(J)}],
        method="SLSQP", options={"maxiter": 500, "ftol": 1e-12},
    )
    w = np.clip(res.x, 0, None)
    return w / w.sum()


def _rmspe(a: np.ndarray) -> float:
    return float(np.sqrt(np.mean(a**2)))


def synthetic_control(
    df: pd.DataFrame, outcome: str, unit_col: str, time_col: str, treated_units: list, intervention,
    freq: str = "W", seed: int | None = 0,
) -> dict:
    cm.quiet()
    cm.check_columns(df, [outcome, unit_col, time_col])
    if not treated_units:
        raise ValueError("Select at least one treated unit.")
    if not pd.api.types.is_numeric_dtype(df[outcome]) and not pd.api.types.is_bool_dtype(df[outcome]):
        raise ValueError(f"Outcome '{outcome}' must be numeric or binary.")
    data = df[[outcome, unit_col, time_col]].dropna()
    tcol = data[time_col]
    if pd.api.types.is_datetime64_any_dtype(tcol):
        if freq not in {"D", "W", "M"}:
            raise ValueError("freq must be 'D', 'W' or 'M'.")
        period = tcol.dt.to_period(freq).dt.start_time
        cut = pd.Timestamp(intervention).to_period(freq).start_time
        is_date = True
    elif pd.api.types.is_numeric_dtype(tcol):
        period, cut, is_date = tcol.astype(float), float(intervention), False
    else:
        raise ValueError(f"Time column '{time_col}' must be a date or a number.")
    panel = (
        pd.DataFrame({"unit": data[unit_col].astype(str).to_numpy(), "period": period.to_numpy(), "y": data[outcome].astype(float).to_numpy()})
        .groupby(["unit", "period"]).y.mean().unstack("period").sort_index(axis=1)
    )
    tr = [str(u) for u in treated_units]
    unknown = [u for u in tr if u not in panel.index]
    if unknown:
        raise ValueError(f"Treated unit(s) not found: {', '.join(unknown)}.")
    donors_all = [u for u in panel.index if u not in tr]
    periods = panel.columns[~panel.loc[tr].isna().any(axis=0).to_numpy()]
    panel = panel[periods]
    dropped = [u for u in donors_all if panel.loc[u].isna().any()]
    donors = [u for u in donors_all if u not in dropped]
    if len(donors) < MIN_DONORS:
        raise ValueError(f"Need at least {MIN_DONORS} donor units with complete data (found {len(donors)}).")
    pre = np.array([p < cut for p in panel.columns])
    if pre.sum() < MIN_PRE:
        raise ValueError(f"Need at least {MIN_PRE} pre-intervention periods (found {int(pre.sum())}).")
    if (~pre).sum() < 1:
        raise ValueError("No post-intervention periods: the intervention date is after the data ends.")

    y1 = panel.loc[tr].mean(axis=0).to_numpy()
    Y0 = panel.loc[donors].to_numpy().T  # (T, J)
    w = _weights(y1[pre], Y0[pre])
    synth = Y0 @ w
    gap = y1 - synth
    pre_rm, post_rm = _rmspe(gap[pre]), _rmspe(gap[~pre])
    ratio = post_rm / max(pre_rm, 1e-8 * max(np.std(y1), 1.0))

    # placebo-in-space
    rng = np.random.default_rng(seed)
    pl_units = donors if len(donors) <= MAX_PLACEBOS else list(rng.choice(donors, MAX_PLACEBOS, replace=False))
    placebos = []
    if len(donors) >= 3:
        for u in pl_units:
            others = [d for d in donors if d != u]
            j = donors.index(u)
            Yo = np.delete(Y0, j, axis=1)
            wp = _weights(Y0[pre][:, j], Yo[pre])
            gp = Y0[:, j] - Yo @ wp
            pr, po = _rmspe(gp[pre]), _rmspe(gp[~pre])
            placebos.append({"unit": u, "gap": gp, "pre_rmspe": pr, "post_rmspe": po, "ratio": po / max(pr, 1e-8 * max(np.std(Y0[:, j]), 1.0))})
    n_pl = len(placebos)
    p_value = (1 + sum(p["ratio"] >= ratio for p in placebos)) / (1 + n_pl) if n_pl else None
    good = [p for p in placebos if p["pre_rmspe"] <= 2 * max(pre_rm, 1e-12)]
    p_filtered = (1 + sum(p["ratio"] >= ratio for p in good)) / (1 + len(good)) if good else None

    avg_gap = float(gap[~pre].mean())
    synth_post = float(synth[~pre].mean())
    fmt = (lambda p: pd.Timestamp(p).strftime("%Y-%m-%d")) if is_date else (lambda p: float(p))
    labels = [fmt(p) for p in panel.columns]
    first_post = next(labels[i] for i in range(len(labels)) if not pre[i])
    order = np.argsort(-w)
    shown = [p for p in sorted(placebos, key=lambda p: p["pre_rmspe"]) if p["pre_rmspe"] <= 5 * max(pre_rm, 1e-12)][:25]
    fit_ratio = pre_rm / max(float(np.std(y1[pre])), 1e-9)
    caveats = []
    if fit_ratio > 0.3:
        caveats.append("The synthetic control only loosely tracks the treated unit before the intervention, so treat the estimate with caution.")
    if p_value is not None and 1 / (1 + n_pl) > 0.05:
        caveats.append(f"With only {n_pl} donor placebos the smallest attainable p-value is {1/(1+n_pl):.3f}; significance at 5% is impossible. Add donor units.")
    if dropped:
        caveats.append(f"{len(dropped)} donor unit(s) were excluded because of missing periods.")
    if len(tr) > 1:
        caveats.append(f"The {len(tr)} treated units were averaged into a single treated series.")
    return {
        "estimate": avg_gap, "relative_effect": avg_gap / synth_post if synth_post else None,
        "cumulative_effect": float(gap[~pre].sum()), "pre_rmspe": pre_rm, "post_rmspe": post_rm,
        "rmspe_ratio": float(ratio), "p_value": p_value, "p_value_filtered": p_filtered,
        "n_placebos": n_pl, "n_donors": len(donors), "n_pre_periods": int(pre.sum()), "n_post_periods": int((~pre).sum()),
        "pre_fit_ratio": float(fit_ratio), "treated_units": tr, "ref_x": first_post, "caveats": caveats,
        "weights": [{"unit": donors[i], "weight": float(w[i])} for i in order if w[i] > 0.005][:15],
        "series": [
            {"x": labels[i], "treated": float(y1[i]), "synthetic": float(synth[i]), "gap": float(gap[i])}
            for i in range(len(labels))
        ],
        "placebo_gaps": [
            {"x": labels[i], "treated_gap": float(gap[i]), **{f"p{k}": float(p["gap"][i]) for k, p in enumerate(shown)}}
            for i in range(len(labels))
        ],
        "n_placebo_lines": len(shown),
    }
