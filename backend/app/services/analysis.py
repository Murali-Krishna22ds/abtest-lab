"""Orchestration: dataset + user choices -> statistics -> plain-English narrative."""
from __future__ import annotations

import time
from functools import wraps
from typing import Any, Callable

import numpy as np
import pandas as pd

from ..errors import AppError
from ..stats import bayes, corrections, sequential as seq, simulate, tests
from ..stats.causal import difference_in_differences, propensity_score_matching, synthetic_control
from ..utils import clean, heavy_slot
from . import narrate
from .datasets import Dataset
from .experiments import LabelBook, _pick_control, collect_experiments, independence_check, outcome_type


def _guard(fn: Callable[..., dict]) -> Callable[..., dict]:
    """Time the run, turn statistical ValueErrors into 422s, and make the result JSON-safe."""

    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> dict:
        t0 = time.perf_counter()
        try:
            out = fn(*args, **kwargs)
        except AppError:
            raise
        except (ValueError, KeyError, np.linalg.LinAlgError) as e:
            raise AppError(str(e).strip("'\"") or "The analysis could not be completed with this data.", 422) from e
        out["runtime_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        return clean(out)

    return wrapper


def _envelope(method: str, ds: Dataset, result: dict, narrative: dict) -> dict:
    return {"method": method, "dataset": {"id": ds.id, "name": ds.name}, "result": result, "narrative": narrative,
            "truth": ds.meta.get("truth")}


def _need(df: pd.DataFrame, cols: list[str | None]) -> None:
    missing = [c for c in cols if c and c not in df.columns]
    if missing:
        raise AppError(f"Column(s) not found in the data: {', '.join(missing)}.", 422)


def _arm_view(a) -> dict:
    return {"key": a.key, "label": a.label, "n": a.n, "x": a.x, "mean": a.mean, "sd": a.sd,
            "rate": (a.x / a.n) if a.x is not None else None}


# --------------------------------------------------------------------------- frequentist
@_guard
def run_frequentist(ds: Dataset, p, labels: LabelBook) -> dict:
    exps = collect_experiments(ds, p.outcome, p.outcome_kind, p.variant_columns, p.control_level, labels)
    comps, srm = [], []
    for e in exps:
        c = e.arm(e.control)
        srm.append({"experiment": e.name, "title": e.title, **tests.srm_check([a.n for a in e.arms])})
        for v in (a for a in e.arms if a.key != e.control):
            base = {"experiment": e.name, "title": e.title, "metric": e.metric, "outcome": e.outcome,
                    "control": c.key, "control_label": c.label, "variant": v.key, "variant_label": v.label,
                    "n_control": c.n, "n_variant": v.n}
            if e.metric == "binary":
                r = tests.two_proportion_test(c.x, c.n, v.x, v.n, p.alpha)
                comps.append({**base, "mean_control": r.p_control, "mean_variant": r.p_treatment, "diff": r.diff,
                              "rel_lift": r.rel_lift, "ci_low": r.ci_low, "ci_high": r.ci_high, "statistic": r.statistic,
                              "p_value": r.p_value, "effect_size": r.cohens_h, "effect_size_name": "Cohen's h", "test": r.test})
            else:
                r = tests.welch_t_test_from_stats(c.mean, c.sd, c.n, v.mean, v.sd, v.n, p.alpha)
                comps.append({**base, "mean_control": r.mean_control, "mean_variant": r.mean_treatment, "diff": r.diff,
                              "rel_lift": r.rel_lift, "ci_low": r.ci_low, "ci_high": r.ci_high, "statistic": r.statistic,
                              "p_value": r.p_value, "effect_size": r.cohens_d, "effect_size_name": "Cohen's d", "test": r.test})
    adj = corrections.adjust_pvalues([c["p_value"] for c in comps], p.correction)
    for c, a in zip(comps, adj):
        c["p_adjusted"], c["significant"] = float(a), bool(a <= p.alpha)
    ind = independence_check(ds.df, p.variant_columns) if ds.kind == "rows" else None
    res = {
        "alpha": p.alpha, "correction": {"method": p.correction, "n_comparisons": len(comps)},
        "comparisons": comps, "srm": srm, "independence": ind,
        "experiments": [{"name": e.name, "title": e.title, "metric": e.metric, "outcome": e.outcome, "control": e.control,
                         "notes": e.notes, "arms": [_arm_view(a) for a in e.arms]} for e in exps],
    }
    return _envelope("frequentist", ds, res, narrate.frequentist(res))


# --------------------------------------------------------------------------- sequential
@_guard
def run_sequential(ds: Dataset, p, labels: LabelBook) -> dict:
    if ds.kind != "rows":
        raise AppError("Sequential monitoring needs row-level data (one row per user), not aggregated counts.", 422)
    df = ds.df
    _need(df, [p.variant_column, p.outcome, p.time_column])
    kind = outcome_type(df, p.outcome, p.outcome_kind)
    cols = [p.variant_column, p.outcome] + ([p.time_column] if p.time_column else [])
    sub = df[cols].dropna().copy()
    sub[p.variant_column] = sub[p.variant_column].astype(str)
    levels = sorted(sub[p.variant_column].unique())
    if len(levels) < 2:
        raise AppError(f"'{p.variant_column}' has fewer than two variants.", 422)
    control = _pick_control(levels, p.control_level)
    variant = p.variant_level or next(lv for lv in levels if lv != control)
    if variant not in levels or variant == control:
        raise AppError(f"Variant '{variant}' is not a valid comparison arm in '{p.variant_column}'.", 422)
    sub = sub[sub[p.variant_column].isin([control, variant])]
    if p.time_column:
        sub = sub.sort_values(p.time_column, kind="stable")
        ordering_note = f"Rows were ordered by '{p.time_column}' to mimic the order in which data arrived."
    else:
        ordering_note = "No time column was chosen, so rows were taken in file order. If the file is sorted by variant, results are meaningless; choose a timestamp column."
    is_b = (sub[p.variant_column] == variant).to_numpy()
    y = sub[p.outcome].astype(float).to_numpy()
    N = len(y)
    K = int(p.n_looks)
    idx = np.unique(np.round(np.linspace(N / K, N, K)).astype(int))
    ca, cb = np.cumsum(~is_b), np.cumsum(is_b)
    sa, sb = np.cumsum(y * ~is_b), np.cumsum(y * is_b)
    qa, qb = np.cumsum(y * y * ~is_b), np.cumsum(y * y * is_b)
    n_a, n_b = ca[idx - 1].astype(float), cb[idx - 1].astype(float)
    keep = (n_a >= 5) & (n_b >= 5)
    if keep.sum() < 2:
        raise AppError("Not enough data: sequential analysis needs at least two looks with 5+ observations in each arm.", 422)
    idx, n_a, n_b = idx[keep], n_a[keep], n_b[keep]
    s_a, s_b, q_a, q_b = sa[idx - 1], sb[idx - 1], qa[idx - 1], qb[idx - 1]
    if kind == "binary":
        theta, s2_test, s2_ci = seq.binary_sequence(n_a, s_a, n_b, s_b)
        base = float(s_a[-1] / n_a[-1])
        scale = base if 0 < base < 1 else None
    else:
        m_a, m_b = s_a / n_a, s_b / n_b
        v_a = np.maximum((q_a - n_a * m_a**2) / (n_a - 1), 0.0)
        v_b = np.maximum((q_b - n_b * m_b**2) / (n_b - 1), 0.0)
        theta, s2_test, s2_ci = seq.continuous_sequence(n_a, m_a, v_a, n_b, m_b, v_b)
        scale = float(np.sqrt((v_a[-1] + v_b[-1]) / 2)) or None
        if np.any(s2_test <= 0):
            raise AppError("The outcome has no variation at one of the looks; cannot compute test statistics.", 422)
    info = (n_a + n_b) / (n_a[-1] + n_b[-1])
    res = seq.analyze_sequence(theta, s2_test, s2_ci, info, alpha=p.alpha, tau=p.tau, spending=p.spending, scale=scale)
    for look, a, b in zip(res["looks"], n_a, n_b):
        look["n_control"], look["n_variant"] = int(a), int(b)
    title, names = labels.resolve(p.variant_column)
    res.update({
        "metric": kind, "outcome": p.outcome, "n_looks": len(res["looks"]), "n_rows": int(N),
        "title": title, "control": control, "variant": variant,
        "control_label": names.get(control, control), "variant_label": names.get(variant, variant),
        "ordering_note": ordering_note,
    })
    if kind == "binary" and scale:
        sim = simulate.simulate_peeking(baseline=scale, rel_lift=0.0, n_max=int(min(max(N // 2, 200), 20000)),
                                        n_looks=max(2, len(res["looks"])), alpha=p.alpha, sims=800, seed=0)
        res["naive_peeking_false_positive_rate"] = sim["methods"]["naive_peeking"]["reject_rate"]
    return _envelope("sequential", ds, res, narrate.sequential(res))


# --------------------------------------------------------------------------- bayesian
@_guard
def run_bayesian(ds: Dataset, p, labels: LabelBook) -> dict:
    exps = collect_experiments(ds, p.outcome, "binary", p.variant_columns, p.control_level, labels)
    out_exps, r_hats, seconds = [], [], 0.0
    for e in exps:
        arms = [bayes.BinaryArm(a.key, a.n, a.x) for a in e.arms]
        kwargs = dict(control=0, prior=(p.prior_alpha, p.prior_beta), rope=p.rope, engine=p.engine,
                      draws=p.draws, chains=p.chains, hdi_prob=p.hdi_prob, seed=42)
        if p.engine == "pymc":
            with heavy_slot():
                r = bayes.analyze_ab(arms, **kwargs)
        else:
            r = bayes.analyze_ab(arms, **kwargs)
        labs = {a.key: a.label for a in e.arms}
        for c in r["comparisons"]:
            c.update({"title": e.title, "variant_label": labs[c["variant"]], "control_label": labs[c["control"]]})
        for a in r["arms"]:
            a["label"] = labs.get(a["name"], a["name"])
        d = r["diagnostics"]
        seconds += float(d.get("seconds") or 0)
        if d.get("r_hat_max"):
            r_hats.append(float(d["r_hat_max"]))
        out_exps.append({"name": e.name, "title": e.title, "control": e.control, "notes": e.notes, "arms": r["arms"],
                         "comparisons": r["comparisons"], "posterior_density": r["posterior_density"],
                         "diagnostics": d, "labels": labs})
    res = {"prior": {"alpha": p.prior_alpha, "beta": p.prior_beta}, "hdi_prob": p.hdi_prob, "rope": p.rope,
           "engine": p.engine, "experiments": out_exps,
           "diagnostics": {"engine": p.engine, "seconds": seconds, "r_hat_max": max(r_hats) if r_hats else None}}
    return _envelope("bayesian", ds, res, narrate.bayesian(res))


# --------------------------------------------------------------------------- causal
def _coerce_point(series: pd.Series, value: Any, what: str):
    try:
        if pd.api.types.is_datetime64_any_dtype(series):
            return pd.Timestamp(value)
        if pd.api.types.is_numeric_dtype(series):
            return float(value)
    except (ValueError, TypeError) as e:
        raise AppError(f"Could not read {what} '{value}' as a value of the time column.", 422) from e
    raise AppError("The time column must be a date or a number.", 422)


@_guard
def run_psm(ds: Dataset, p) -> dict:
    _need(ds.df, [p.treatment, p.outcome, *p.covariates])
    with heavy_slot():
        res = propensity_score_matching(
            ds.df, p.treatment, p.outcome, p.covariates, treated_value=p.treated_value, caliper=p.caliper,
            n_neighbors=p.n_neighbors, n_boot=p.n_boot, alpha=p.alpha, seed=0, cross_check=p.cross_check, refute=p.refute)
    truth = (ds.meta.get("truth") or {}).get("effect")
    return _envelope("psm", ds, res, narrate.psm(res, p.outcome, p.alpha, truth))


@_guard
def run_did(ds: Dataset, p) -> dict:
    _need(ds.df, [p.outcome, p.group_col, p.time_col, p.unit_col, *p.covariates])
    cutoff = _coerce_point(ds.df[p.time_col], p.cutoff, "intervention time")
    with heavy_slot():
        res = difference_in_differences(
            ds.df, p.outcome, p.group_col, p.treated_value, p.time_col, cutoff, unit_col=p.unit_col,
            covariates=p.covariates or None, alpha=p.alpha, cross_check=p.cross_check)
    truth = (ds.meta.get("truth") or {}).get("effect")
    return _envelope("did", ds, res, narrate.did(res, p.outcome, p.alpha, p.group_col, truth))


@_guard
def run_synthetic(ds: Dataset, p) -> dict:
    df = ds.df
    _need(df, [p.outcome, p.unit_col, p.time_col, p.group_col])
    units = list(p.treated_units)
    if not units:
        if not (p.group_col and p.treated_value is not None):
            raise AppError("Name the treated unit(s), or choose a group column and the value that marks treated units.", 422)
        units = sorted(df.loc[df[p.group_col].astype(str) == str(p.treated_value), p.unit_col].astype(str).unique())
    if not units:
        raise AppError("No treated units were found with those settings.", 422)
    cutoff = _coerce_point(df[p.time_col], p.intervention, "intervention time")
    with heavy_slot():
        res = synthetic_control(df, p.outcome, p.unit_col, p.time_col, units, cutoff, freq=p.freq, seed=0)
    truth = (ds.meta.get("truth") or {}).get("effect")
    return _envelope("synthetic_control", ds, res, narrate.synthetic(res, p.outcome, truth))
