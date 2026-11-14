"""Turn a dataset plus user choices into experiment arms (counts / moments / raw values)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import stats

from ..errors import AppError
from .datasets import Dataset, column_role


# --------------------------------------------------------------------------- labels
class LabelBook:
    """Friendly names for variants, loaded from an ``ab_test_variants``-style file."""

    def __init__(self, df: pd.DataFrame | None):
        self.rows = df if df is not None else pd.DataFrame()

    def resolve(self, experiment: str) -> tuple[str, dict[str, str]]:
        """Return (display title, {variant_key: variant_name}) for an experiment name."""
        r = self.rows
        if r.empty or "test_name" not in r or "variant_key" not in r:
            return experiment, {}
        exact = r[r["test_name"] == experiment]
        if exact.empty and "test_id" in r:
            norm = re.sub(r"_(variant|arm|group|test)$", "", experiment.lower())
            exact = r[r["test_id"].astype(str).str.lower().str.startswith(norm)]
        if exact.empty:
            return experiment, {}
        name_col = "variant_name" if "variant_name" in exact else "variant_key"
        return str(exact["test_name"].iloc[0]), dict(zip(exact["variant_key"].astype(str), exact[name_col].astype(str)))


# --------------------------------------------------------------------------- data classes
@dataclass
class Arm:
    key: str
    label: str
    n: int
    x: int | None = None            # successes (binary)
    mean: float | None = None
    sd: float | None = None
    values: np.ndarray | None = None  # raw outcomes when available


@dataclass
class Experiment:
    name: str
    title: str
    metric: str  # binary | continuous
    outcome: str
    control: str
    arms: list[Arm]
    notes: list[str] = field(default_factory=list)

    def arm(self, key: str) -> Arm:
        return next(a for a in self.arms if a.key == key)


def _pick_control(levels: list[str], requested: str | None) -> str:
    if requested and requested in levels:
        return requested
    for cand in ("control", "Control", "baseline", "A"):
        if cand in levels:
            return cand
    return levels[0]


def _order(levels: list[str], control: str) -> list[str]:
    return [control] + [lv for lv in levels if lv != control]


def outcome_type(df: pd.DataFrame, outcome: str, requested: str | None) -> str:
    if outcome not in df.columns:
        raise AppError(f"Outcome column '{outcome}' not found.", 422)
    role = column_role(df[outcome])
    if requested:
        if requested == "binary" and role != "binary":
            raise AppError(f"'{outcome}' is not a 0/1 or True/False column, so it cannot be treated as binary.", 422)
        if requested == "continuous" and role not in {"binary", "numeric"}:
            raise AppError(f"'{outcome}' is not numeric.", 422)
        return requested
    if role == "binary":
        return "binary"
    if role == "numeric":
        return "continuous"
    raise AppError(f"Outcome '{outcome}' must be numeric or binary (found {role}).", 422)


# --------------------------------------------------------------------------- collection
def collect_experiments(
    ds: Dataset, outcome: str | None, outcome_kind: str | None, variant_columns: list[str],
    control_level: str | None, labels: LabelBook, keep_values: bool = False,
) -> list[Experiment]:
    df = ds.df
    if ds.kind == "labels":
        raise AppError("This file only describes variants; upload the experiment data instead.", 422)
    if ds.kind == "aggregated":
        return _from_aggregated(df, control_level, labels)

    if not outcome:
        raise AppError("Choose an outcome column.", 422)
    if not variant_columns:
        raise AppError("Choose at least one variant column.", 422)
    kind = outcome_type(df, outcome, outcome_kind)
    exps = []
    for vc in variant_columns:
        if vc not in df.columns:
            raise AppError(f"Variant column '{vc}' not found.", 422)
        if vc == outcome:
            raise AppError("The variant column and the outcome must be different.", 422)
        sub = df[[vc, outcome]].dropna(subset=[vc])
        n_missing = int(sub[outcome].isna().sum())
        sub = sub.dropna(subset=[outcome])
        sub[vc] = sub[vc].astype(str)
        levels = sorted(sub[vc].unique())
        if len(levels) < 2:
            raise AppError(f"'{vc}' has fewer than two variants.", 422)
        if len(levels) > 10:
            raise AppError(f"'{vc}' has {len(levels)} distinct values; pick a column with at most 10 variants.", 422)
        control = _pick_control(levels, control_level)
        title, names = labels.resolve(vc)
        notes = []
        if n_missing:
            notes.append(f"{n_missing:,} rows with a missing '{outcome}' were excluded from '{vc}'.")
        arms = []
        for lv in _order(levels, control):
            vals = sub.loc[sub[vc] == lv, outcome].astype(float).to_numpy()
            if len(vals) < 2:
                raise AppError(f"Variant '{lv}' in '{vc}' has fewer than 2 observations.", 422)
            a = Arm(lv, names.get(lv, lv), len(vals))
            if kind == "binary":
                a.x = int(vals.sum())
            else:
                a.mean, a.sd = float(vals.mean()), float(vals.std(ddof=1))
            if keep_values or kind == "continuous":
                a.values = vals
            arms.append(a)
        exps.append(Experiment(vc, title, kind, outcome, control, arms, notes))
    return exps


def _from_aggregated(df: pd.DataFrame, control_level: str | None, labels: LabelBook) -> list[Experiment]:
    low = {c.lower(): c for c in df.columns}
    vk, tu, cv = low["variant_key"], low["total_users"], low["conversions"]
    group = low.get("test_name")
    exps = []
    for name, sub in (df.groupby(group, sort=False) if group else [("experiment", df)]):
        sub = sub.dropna(subset=[vk, tu, cv])
        levels = [str(v) for v in sub[vk]]
        if len(set(levels)) != len(levels):
            raise AppError(f"Test '{name}' lists the same variant more than once.", 422)
        control = _pick_control(sorted(levels), control_level)
        title, names = labels.resolve(str(name))
        by = {str(r[vk]): r for _, r in sub.iterrows()}
        arms = []
        for lv in _order(sorted(levels), control):
            n, x = int(by[lv][tu]), int(by[lv][cv])
            if n <= 0 or x < 0 or x > n:
                raise AppError(f"Invalid counts for '{name}' / '{lv}': {x} conversions of {n} users.", 422)
            arms.append(Arm(lv, names.get(lv, lv), n, x=x))
        if len(arms) >= 2:
            exps.append(Experiment(str(name), title, "binary", "conversion", control, arms,
                                   ["Built from aggregated counts: only conversion rate can be analysed."]))
    if not exps:
        raise AppError("No test with at least two variants was found in the summary file.", 422)
    return exps


# --------------------------------------------------------------------------- diagnostics
def independence_check(df: pd.DataFrame, columns: list[str]) -> dict | None:
    """Are concurrent tests assigned independently? (needed to analyse each one alone)"""
    if len(columns) < 2:
        return None
    worst = {"p_value": 1.0, "pair": None}
    for i in range(len(columns)):
        for j in range(i + 1, len(columns)):
            t = pd.crosstab(df[columns[i]], df[columns[j]])
            if t.shape[0] < 2 or t.shape[1] < 2:
                continue
            p = float(stats.chi2_contingency(t, correction=False)[1])
            if p < worst["p_value"]:
                worst = {"p_value": p, "pair": [columns[i], columns[j]]}
    return worst
