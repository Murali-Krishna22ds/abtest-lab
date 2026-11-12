"""Empirical demonstrations of the core ideas behind A/B testing.

Run:  python scripts/fundamentals_demo.py
Each block simulates many experiments and checks a textbook claim against the simulation.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.services.power import power_two_sample_t, sample_size_two_means  # noqa: E402

rng = np.random.default_rng(2024)
N_SIM = 5000


def welch(a: np.ndarray, b: np.ndarray):
    """Vectorised Welch t-test across simulations (rows) -> (p-values, diffs, ci_low, ci_high)."""
    na, nb = a.shape[1], b.shape[1]
    va, vb = a.var(axis=1, ddof=1), b.var(axis=1, ddof=1)
    se = np.sqrt(va / na + vb / nb)
    diff = b.mean(axis=1) - a.mean(axis=1)
    df = (va / na + vb / nb) ** 2 / ((va / na) ** 2 / (na - 1) + (vb / nb) ** 2 / (nb - 1))
    p = 2 * stats.t.sf(np.abs(diff / se), df)
    tc = stats.t.isf(0.025, df)
    return p, diff, diff - tc * se, diff + tc * se


def main() -> None:
    n = 100
    print("1. p-values under the null are uniform; the false-positive rate equals alpha")
    a = rng.normal(0, 1, (N_SIM, n))
    b = rng.normal(0, 1, (N_SIM, n))
    p, *_ = welch(a, b)
    print(f"   P(p < 0.05) = {np.mean(p < 0.05):.3f}  (expected 0.050)")
    print(f"   P(p < 0.50) = {np.mean(p < 0.50):.3f}  (expected 0.500, i.e. uniform)")

    print("2. A 95% confidence interval covers the true difference ~95% of the time")
    true_diff = 0.3
    b = rng.normal(true_diff, 1, (N_SIM, n))
    _, _, lo, hi = welch(a, b)
    print(f"   coverage = {np.mean((lo <= true_diff) & (true_diff <= hi)):.3f}  (expected 0.950)")

    print("3. Power: share of experiments that detect a real effect")
    for d, size in [(0.3, 100), (0.5, 64), (0.2, 394)]:
        a = rng.normal(0, 1, (N_SIM, size))
        b = rng.normal(d, 1, (N_SIM, size))
        p, *_ = welch(a, b)
        print(f"   d={d}, n={size}/arm: simulated {np.mean(p < 0.05):.3f} vs formula {power_two_sample_t(d, size, size):.3f}")

    print("4. Sample size needed to hit 80% power grows with 1/d^2")
    for d in (0.8, 0.5, 0.2, 0.1):
        n1, _, pw = sample_size_two_means(d)
        print(f"   d={d}: n={n1} per arm (power {pw:.3f}); n*d^2 = {n1 * d * d:.1f}  (roughly constant ~15.7)")

    print("5. Underpowered tests exaggerate the effects they do detect (winner's curse)")
    d, size = 0.2, 40
    a = rng.normal(0, 1, (N_SIM, size))
    b = rng.normal(d, 1, (N_SIM, size))
    p, diff, *_ = welch(a, b)
    sig = p < 0.05
    print(f"   power = {sig.mean():.2f}; true effect = {d}; mean estimate among significant results = {diff[sig].mean():.2f}")

    print("6. Many looks at many metrics: the chance of at least one false positive")
    for m in (1, 5, 20):
        print(f"   {m:>2} independent null metrics -> P(any p<0.05) = {1 - 0.95 ** m:.3f}")


if __name__ == "__main__":
    main()
