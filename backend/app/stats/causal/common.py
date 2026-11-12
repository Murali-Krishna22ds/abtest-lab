"""Shared helpers for the observational / quasi-experimental methods."""
from __future__ import annotations

import logging
import warnings

import numpy as np
import pandas as pd

MIN_GROUP = 20
MAX_LEVELS = 25


def quiet() -> None:
    """DoWhy / EconML are very chatty; keep server logs readable."""
    warnings.filterwarnings("ignore")
    for name in ("dowhy", "econml", "causalml", "matplotlib"):
        logging.getLogger(name).setLevel(logging.ERROR)


def design_matrix(df: pd.DataFrame, covariates: list[str]) -> pd.DataFrame:
    """Numeric design matrix: numeric columns as-is, booleans as 0/1, categoricals one-hot
    (first level dropped). Constant columns are removed."""
    parts = []
    for c in covariates:
        s = df[c]
        if pd.api.types.is_bool_dtype(s):
            parts.append(s.astype(float).rename(c))
        elif pd.api.types.is_numeric_dtype(s):
            parts.append(s.astype(float).rename(c))
        elif pd.api.types.is_datetime64_any_dtype(s):
            raise ValueError(f"Covariate '{c}' is a date; derive a numeric feature or remove it.")
        else:
            n_levels = s.nunique()
            if n_levels > MAX_LEVELS:
                raise ValueError(f"Covariate '{c}' has {n_levels} levels (max {MAX_LEVELS}); drop it or group levels.")
            parts.append(pd.get_dummies(s.astype(str), prefix=c, drop_first=True, dtype=float))
    X = pd.concat(parts, axis=1) if parts else pd.DataFrame(index=df.index)
    return X.loc[:, X.std(ddof=0) > 0]


def treatment_indicator(s: pd.Series, treated_value=None) -> pd.Series:
    """Boolean treatment from a column: use ``treated_value`` if given, else True/1."""
    if treated_value is not None:
        return (s.astype(str) == str(treated_value)).rename(s.name)
    if pd.api.types.is_bool_dtype(s):
        return s.rename(s.name)
    vals = set(pd.unique(s.dropna()))
    if vals <= {0, 1}:
        return (s == 1).rename(s.name)
    raise ValueError("Specify which value of the treatment column counts as 'treated'.")


def check_columns(df: pd.DataFrame, cols: list[str]) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"Column(s) not found: {', '.join(missing)}.")


def f(x) -> float:
    return float(x)
