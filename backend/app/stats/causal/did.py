"""Difference-in-differences (2 groups x pre/post) with parallel-trends diagnostics.

    y = b0 + b1*treated + b2*post + b3*(treated*post) + covariates + e

``b3`` is the DiD estimate. Standard errors are cluster-robust when a unit column with
at least 10 clusters is supplied, heteroskedasticity-robust (HC1) otherwise. The same
effect is re-estimated through DoWhy as an independent cross-check.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

from . import common as cm

MIN_CELL = 5
MIN_CLUSTERS = 10


def _fit(y, X, groups, ):
    model = sm.OLS(y, X)
    if groups is not None:
        return model.fit(cov_type="cluster", cov_kwds={"groups": groups})
    return model.fit(cov_type="HC1")


def difference_in_differences(
    df: pd.DataFrame, outcome: str, group_col: str, treated_value, time_col: str, cutoff,
    unit_col: str | None = None, covariates: list[str] | None = None, alpha: float = 0.05,
    max_points: int = 40, cross_check: bool = True,
) -> dict:
    cm.quiet()
    covariates = covariates or []
    cols = [outcome, group_col, time_col] + ([unit_col] if unit_col else []) + covariates
    cm.check_columns(df, cols)
    if len(set(cols)) != len(cols):
        raise ValueError("Outcome, group, time, unit and covariate columns must all be different.")
    if not pd.api.types.is_numeric_dtype(df[outcome]) and not pd.api.types.is_bool_dtype(df[outcome]):
        raise ValueError(f"Outcome '{outcome}' must be numeric or binary.")
    data = df[cols].dropna().reset_index(drop=True)
    n_dropped = len(df) - len(data)

    treated = (data[group_col].astype(str) == str(treated_value)).to_numpy()
    tcol = data[time_col]
    if pd.api.types.is_datetime64_any_dtype(tcol):
        cut = pd.Timestamp(cutoff)
        post = (tcol >= cut).to_numpy()
        tmin = tcol.min()
        unit_days = 7.0
        tnum = ((tcol - tmin).dt.total_seconds() / 86400 / unit_days).to_numpy()
        cut_num = float((cut - tmin).total_seconds() / 86400 / unit_days)
        time_unit, is_date = "weeks", True
    elif pd.api.types.is_numeric_dtype(tcol):
        cut = float(cutoff)
        post = (tcol >= cut).to_numpy()
        tnum, cut_num = tcol.astype(float).to_numpy(), cut
        time_unit, is_date = "time units", False
    else:
        raise ValueError(f"Time column '{time_col}' must be a date or a number.")
    y = data[outcome].astype(float).to_numpy()

    cells = {(g, p): int(((treated == g) & (post == p)).sum()) for g in (True, False) for p in (True, False)}
    if min(cells.values()) < MIN_CELL:
        raise ValueError(
            "Each of the four groups (treated/control x before/after) needs at least "
            f"{MIN_CELL} rows; got {cells}. Check the treated value and the cutoff."
        )

    X = pd.DataFrame({"const": 1.0, "treated": treated.astype(float), "post": post.astype(float)})
    X["did"] = X["treated"] * X["post"]
    if covariates:
        X = pd.concat([X, cm.design_matrix(data, covariates).reset_index(drop=True)], axis=1)

    caveats: list[str] = []
    groups = None
    if unit_col:
        codes, uniques = pd.factorize(data[unit_col])
        if len(uniques) >= MIN_CLUSTERS:
            groups = codes
            n_tr_units = data.loc[treated, unit_col].nunique()
            if n_tr_units < 5:
                caveats.append(f"Only {n_tr_units} treated unit(s): cluster-robust standard errors can be too optimistic with so few treated clusters.")
        else:
            caveats.append(f"Only {len(uniques)} units (<{MIN_CLUSTERS}) so cluster-robust errors were not used; standard errors may be too small.")
    res = _fit(y, X, groups)
    est, se = float(res.params["did"]), float(res.bse["did"])
    ci = res.conf_int(alpha=alpha).loc["did"]

    means = {
        "control_pre": float(y[~treated & ~post].mean()), "control_post": float(y[~treated & post].mean()),
        "treated_pre": float(y[treated & ~post].mean()), "treated_post": float(y[treated & post].mean()),
    }
    means["treated_change"] = means["treated_post"] - means["treated_pre"]
    means["control_change"] = means["control_post"] - means["control_pre"]

    # parallel-trends diagnostic on pre-period data only
    pre = ~post
    pre_trend = None
    if len(np.unique(tnum[pre])) >= 3:
        Xp = pd.DataFrame({"const": 1.0, "treated": treated[pre].astype(float), "t": tnum[pre]})
        Xp["treated_x_t"] = Xp["treated"] * Xp["t"]
        rp = _fit(y[pre], Xp, groups[pre] if groups is not None else None)
        pre_trend = {
            "slope_difference_per_week" if is_date else "slope_difference_per_unit": float(rp.params["treated_x_t"]),
            "p_value": float(rp.pvalues["treated_x_t"]),
        }
    else:
        caveats.append("Fewer than 3 distinct pre-period times, so parallel trends cannot be tested.")

    series, ref_x = _trend_series(data, time_col, y, treated, post, tnum, cut_num, is_date, max_points)

    if pre_trend is not None:
        pre_trend["n_pre_periods"] = sum(1 for r in series if not r["post"])
    out = {
        "estimate": est, "se": se, "ci_low": float(ci[0]), "ci_high": float(ci[1]),
        "p_value": float(res.pvalues["did"]), "means": means, "cell_sizes": {f"{'treated' if g else 'control'}_{'post' if p else 'pre'}": n for (g, p), n in cells.items()},
        "se_type": "cluster-robust" if groups is not None else "HC1 robust", "n": int(len(y)),
        "n_dropped_missing": int(n_dropped), "pre_trend": pre_trend, "series": series, "ref_x": ref_x,
        "time_unit": time_unit, "caveats": caveats,
    }
    if cross_check:
        out["cross_check"] = _dowhy_check(X, y)
    return out


def _trend_series(data, time_col, y, treated, post, tnum, cut_num, is_date, max_points):
    uniq = np.unique(tnum)
    if len(uniq) <= max_points:
        key = np.searchsorted(uniq, tnum)
    else:
        tmin, tmax = float(tnum.min()), float(tnum.max())
        span_pre, span_post = cut_num - tmin, tmax - cut_num
        total = max(span_pre + span_post, 1e-9)
        nb_pre = int(np.clip(round(max_points * span_pre / total), 1, max_points - 1))
        nb_post = max(1, max_points - nb_pre)
        edges = np.concatenate([np.linspace(tmin, cut_num, nb_pre + 1)[:-1], np.linspace(cut_num, tmax + 1e-9, nb_post + 1)])
        key = np.clip(np.digitize(tnum, edges) - 1, 0, len(edges) - 2)
    frame = pd.DataFrame({"key": key, "treated": treated, "post": post, "y": y, "time": data[time_col].to_numpy()})
    g = frame.groupby(["key", "treated"]).y.mean().unstack("treated")
    if True not in g.columns or False not in g.columns:
        return [], None
    meta = frame.groupby("key").agg(time=("time", "mean"), post=("post", "mean"))
    g = g.dropna().join(meta)
    pre_gap = float((g[g.post < 0.5][True] - g[g.post < 0.5][False]).mean())
    rows = []
    for k, r in g.iterrows():
        label = pd.Timestamp(r["time"]).strftime("%Y-%m-%d") if is_date else round(float(r["time"]), 2)
        rows.append({
            "x": label, "treated": float(r[True]), "control": float(r[False]),
            "counterfactual": float(r[False] + pre_gap) if r["post"] >= 0.5 else None,
            "post": bool(r["post"] >= 0.5),
        })
    first_post = next((r["x"] for r in rows if r["post"]), None)
    return rows, first_post


def _dowhy_check(X: pd.DataFrame, y: np.ndarray) -> dict:
    try:
        from dowhy import CausalModel

        d = X.drop(columns="const").copy()
        d.columns = [f"v{i}" if c not in ("treated", "post", "did") else c for i, c in enumerate(d.columns)]
        d["did"] = d["did"].astype(bool)
        d["Y"] = y
        causes = [c for c in d.columns if c not in ("did", "Y")]
        m = CausalModel(data=d, treatment="did", outcome="Y", common_causes=causes)
        est = m.estimate_effect(m.identify_effect(proceed_when_unidentifiable=True), method_name="backdoor.linear_regression")
        return {"library": "DoWhy", "estimate": float(est.value)}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"[:300]}
