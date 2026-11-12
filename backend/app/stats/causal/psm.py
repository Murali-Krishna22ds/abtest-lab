"""Propensity-score matching with balance diagnostics, cross-checked by DoWhy and EconML.

Primary estimate
    Logistic-regression propensity score -> nearest-neighbour matching on the logit
    (with replacement, caliper = 0.2 sd of the logit, Austin 2011) -> average treatment
    effect on the treated (ATT). Standard error and CI come from a bootstrap that
    re-estimates the score in every replicate.

Cross-checks (triangulation)
    * DoWhy   ``backdoor.propensity_score_matching`` (ATT) and a placebo-treatment refuter.
    * EconML  ``LinearDRLearner`` doubly-robust estimator (ATE, flexible outcome model).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import LogisticRegression
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler

from . import common as cm


def _fit_scores(Xs: np.ndarray, t: np.ndarray) -> np.ndarray:
    lr = LogisticRegression(max_iter=2000, C=1e6)
    lr.fit(Xs, t)
    p = np.clip(lr.predict_proba(Xs)[:, 1], 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p)), p


def _match(logit: np.ndarray, t: np.ndarray, y: np.ndarray, caliper: float, k: int):
    """Return per-treated matched-control mean outcome (NaN if unmatched) and control weights."""
    ti, ci = np.where(t)[0], np.where(~t)[0]
    nn = NearestNeighbors(n_neighbors=min(k, len(ci))).fit(logit[ci, None])
    dist, idx = nn.kneighbors(logit[ti, None])
    ok = dist <= caliper
    ctrl_y = y[ci][idx]
    counts = ok.sum(axis=1)
    matched = np.where(counts > 0, (ctrl_y * ok).sum(axis=1) / np.maximum(counts, 1), np.nan)
    weights = np.zeros(len(ci))
    for col in range(idx.shape[1]):
        w = np.where(ok[:, col], 1.0 / np.maximum(counts, 1), 0.0)
        np.add.at(weights, idx[:, col], w)
    return ti, ci, matched, weights


def _att(Xs, t, y, caliper_sd, k):
    logit, ps = _fit_scores(Xs, t)
    ti, ci, matched, w = _match(logit, t, y, caliper_sd * logit.std(), k)
    keep = ~np.isnan(matched)
    if keep.sum() < 5:
        return np.nan, logit, ps, ti, ci, matched, w
    return float(np.mean(y[ti][keep] - matched[keep])), logit, ps, ti, ci, matched, w


def propensity_score_matching(
    df: pd.DataFrame, treatment: str, outcome: str, covariates: list[str],
    treated_value=None, caliper: float = 0.2, n_neighbors: int = 1, n_boot: int = 100,
    alpha: float = 0.05, seed: int | None = 0, cross_check: bool = True, refute: bool = False,
) -> dict:
    cm.quiet()
    if not covariates:
        raise ValueError("Select at least one covariate to adjust for.")
    if treatment in covariates or outcome in covariates or treatment == outcome:
        raise ValueError("Treatment, outcome and covariates must be different columns.")
    if n_neighbors < 1 or caliper <= 0:
        raise ValueError("n_neighbors must be >= 1 and caliper > 0.")
    cm.check_columns(df, [treatment, outcome, *covariates])
    if not pd.api.types.is_numeric_dtype(df[outcome]) and not pd.api.types.is_bool_dtype(df[outcome]):
        raise ValueError(f"Outcome '{outcome}' must be numeric or binary.")

    data = df[[treatment, outcome, *covariates]].dropna()
    n_dropped = len(df) - len(data)
    t = cm.treatment_indicator(data[treatment], treated_value).to_numpy(dtype=bool)
    y = data[outcome].astype(float).to_numpy()
    if t.sum() < cm.MIN_GROUP or (~t).sum() < cm.MIN_GROUP:
        raise ValueError(f"Need at least {cm.MIN_GROUP} treated and {cm.MIN_GROUP} control rows (got {int(t.sum())}/{int((~t).sum())}).")
    X = cm.design_matrix(data, covariates)
    if X.shape[1] == 0:
        raise ValueError("None of the selected covariates vary; choose different covariates.")
    Xs = StandardScaler().fit_transform(X.to_numpy())

    est, logit, ps, ti, ci, matched, w = _att(Xs, t, y, caliper, n_neighbors)
    if np.isnan(est):
        raise ValueError("Too few treated units could be matched within the caliper; widen the caliper.")
    keep = ~np.isnan(matched)
    diffs = y[ti][keep] - matched[keep]

    # bootstrap (re-estimates the propensity model each time)
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(n_boot):
        b = rng.integers(0, len(y), len(y))
        tb = t[b]
        if tb.sum() < 10 or (~tb).sum() < 10:
            continue
        try:
            e = _att(Xs[b], tb, y[b], caliper, n_neighbors)[0]
        except Exception:
            continue
        if not np.isnan(e):
            boots.append(e)
    boots = np.asarray(boots)
    if len(boots) >= 20:
        se = float(boots.std(ddof=1))
        lo, hi = (float(v) for v in np.percentile(boots, [100 * alpha / 2, 100 * (1 - alpha / 2)]))
    else:  # fall back to the paired-difference standard error
        se = float(diffs.std(ddof=1) / np.sqrt(len(diffs)))
        z = stats.norm.isf(alpha / 2)
        lo, hi = est - z * se, est + z * se
    z_stat = est / se if se > 0 else np.nan
    p_value = float(2 * stats.norm.sf(abs(z_stat))) if se > 0 else np.nan

    naive = float(y[t].mean() - y[~t].mean())

    # covariate balance (standardised mean differences, pre-match pooled sd as reference)
    xm = X.to_numpy()
    weights_ctrl = w / w.sum() if w.sum() > 0 else w
    keep_t = ti[keep]
    balance = []
    for j, name in enumerate(X.columns):
        col = xm[:, j]
        sd_ref = float(np.sqrt((col[t].var(ddof=1) + col[~t].var(ddof=1)) / 2))
        if sd_ref == 0:
            continue
        before = (col[t].mean() - col[~t].mean()) / sd_ref
        after = (col[keep_t].mean() - float(np.sum(weights_ctrl * col[ci]))) / sd_ref
        balance.append({"covariate": name, "smd_before": float(before), "smd_after": float(after)})
    max_after = max((abs(b["smd_after"]) for b in balance), default=0.0)

    bins = np.linspace(0, 1, 21)
    ct, _ = np.histogram(ps[t], bins=bins)
    cc, _ = np.histogram(ps[~t], bins=bins)
    overlap = [
        {"x": float((bins[i] + bins[i + 1]) / 2), "treated": float(ct[i] / ct.sum()), "control": float(cc[i] / cc.sum())}
        for i in range(20)
    ]

    out = {
        "estimand": "ATT", "estimate": est, "se": se, "ci_low": lo, "ci_high": hi, "p_value": p_value,
        "naive_difference": naive, "bias_removed": naive - est,
        "n": int(len(y)), "n_treated": int(t.sum()), "n_control": int((~t).sum()),
        "n_treated_matched": int(keep.sum()), "n_treated_unmatched": int((~keep).sum()),
        "n_controls_used": int((w > 0).sum()), "n_dropped_missing": int(n_dropped),
        "caliper_sd": caliper, "n_neighbors": n_neighbors, "n_bootstrap": int(len(boots)),
        "balance": balance, "max_abs_smd_after": float(max_after),
        "balance_ok": bool(max_after < 0.1), "overlap": overlap,
        "outcome_mean_treated": float(y[t].mean()), "outcome_mean_control": float(y[~t].mean()),
    }
    if cross_check:
        out["cross_checks"] = _cross_checks(X, t, y, alpha, seed, refute)
    return out


# --------------------------------------------------------------------------- DoWhy / EconML
def _cross_checks(X: pd.DataFrame, t: np.ndarray, y: np.ndarray, alpha: float, seed, refute: bool) -> dict:
    res: dict = {}
    cols = [f"x{i}" for i in range(X.shape[1])]
    Xr = pd.DataFrame(X.to_numpy(), columns=cols)
    try:
        from dowhy import CausalModel

        data = Xr.copy()
        data["T"], data["Y"] = t, y
        model = CausalModel(data=data, treatment="T", outcome="Y", common_causes=cols)
        estimand = model.identify_effect(proceed_when_unidentifiable=True)
        est = model.estimate_effect(estimand, method_name="backdoor.propensity_score_matching", target_units="att")
        res["dowhy_psm"] = {"estimand": "ATT", "estimate": float(est.value), "library": "DoWhy"}
        if refute:
            ref = model.refute_estimate(
                estimand, est, method_name="placebo_treatment_refuter", placebo_type="permute",
                num_simulations=20, random_seed=seed or 0,
            )
            res["dowhy_placebo_refutation"] = {
                "original_effect": float(ref.estimated_effect), "placebo_effect": float(ref.new_effect),
                "p_value": None if ref.refutation_result is None else float(ref.refutation_result["p_value"]),
                "interpretation": "With the treatment labels randomly permuted, the estimated effect should be close to zero.",
            }
    except Exception as e:  # cross-checks must never take down the main analysis
        res["dowhy_error"] = f"{type(e).__name__}: {e}"[:300]
    try:
        from econml.dr import LinearDRLearner
        from sklearn.ensemble import HistGradientBoostingRegressor

        dr = LinearDRLearner(
            model_propensity=LogisticRegression(max_iter=2000, C=1e6),
            model_regression=HistGradientBoostingRegressor(max_depth=3, random_state=seed or 0),
            cv=3, random_state=seed or 0,
        )
        dr.fit(y, t.astype(int), X=None, W=X.to_numpy())
        inf = dr.ate_inference()
        lo, hi = inf.conf_int_mean(alpha=alpha)
        res["econml_dr"] = {
            "estimand": "ATE", "estimate": float(np.ravel(inf.mean_point)[0]),
            "ci_low": float(np.ravel(lo)[0]), "ci_high": float(np.ravel(hi)[0]), "library": "EconML",
        }
    except Exception as e:
        res["econml_error"] = f"{type(e).__name__}: {e}"[:300]
    return res
