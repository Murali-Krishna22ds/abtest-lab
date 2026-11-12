"""Multiple-testing corrections (vectorised along the last axis).

* ``bonferroni`` - controls the family-wise error rate (FWER), most conservative.
* ``holm``       - step-down Bonferroni; controls FWER and is uniformly more powerful.
* ``bh``         - Benjamini-Hochberg step-up; controls the false discovery rate (FDR)
                   under independence / positive dependence.
"""
from __future__ import annotations

import numpy as np

METHODS = ("none", "bonferroni", "holm", "bh")


def adjust_pvalues(p, method: str = "holm") -> np.ndarray:
    """Return adjusted p-values with the same shape as ``p``.

    Hypothesis ``i`` is rejected at level ``alpha`` when ``adjusted[i] <= alpha``.
    """
    p = np.asarray(p, dtype=float)
    if p.size == 0:
        return p.copy()
    if np.isnan(p).any() or (p < 0).any() or (p > 1).any():
        raise ValueError("p-values must lie in [0, 1] and must not be NaN.")
    method = method.lower()
    if method not in METHODS:
        raise ValueError(f"Unknown correction '{method}'. Choose from {METHODS}.")
    if method == "none":
        return p.copy()
    m = p.shape[-1]
    if method == "bonferroni":
        return np.minimum(1.0, p * m)

    order = np.argsort(p, axis=-1, kind="stable")
    ps = np.take_along_axis(p, order, axis=-1)
    ranks = np.arange(1, m + 1)
    if method == "holm":
        adj_sorted = np.maximum.accumulate(ps * (m - ranks + 1), axis=-1)
    else:  # Benjamini-Hochberg
        adj_sorted = np.minimum.accumulate((ps * m / ranks)[..., ::-1], axis=-1)[..., ::-1]
    adj_sorted = np.minimum(1.0, adj_sorted)
    out = np.empty_like(adj_sorted)
    np.put_along_axis(out, order, adj_sorted, axis=-1)
    return out


def reject(p, method: str = "holm", alpha: float = 0.05) -> np.ndarray:
    return adjust_pvalues(p, method) <= alpha
