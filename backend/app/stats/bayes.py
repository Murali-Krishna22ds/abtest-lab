"""Bayesian A/B analysis for conversion rates.

Model (per arm i):  p_i ~ Beta(a0, b0),   x_i ~ Binomial(n_i, p_i)

The posterior is available in closed form (Beta), but the default engine samples it
with PyMC (NUTS) so the same code extends to richer models. ``engine="conjugate"`` draws
directly from the exact Beta posteriors, which is faster and is used to validate PyMC.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

import numpy as np
from scipy import integrate, stats

logging.getLogger("pymc").setLevel(logging.ERROR)
logging.getLogger("pytensor").setLevel(logging.ERROR)

_PYMC_LOCK = threading.Lock()  # PyMC/pytensor compilation is not safe to run concurrently


@dataclass(frozen=True)
class BinaryArm:
    name: str
    n: int
    x: int

    def __post_init__(self):
        if self.n <= 0 or self.x < 0 or self.x > self.n:
            raise ValueError(f"Invalid counts for arm '{self.name}': {self.x}/{self.n}.")


# --------------------------------------------------------------------------- helpers
def hdi(draws: np.ndarray, prob: float = 0.95) -> tuple[float, float]:
    """Highest-density (shortest) interval of a sample."""
    s = np.sort(np.asarray(draws, float))
    m = int(np.floor(prob * len(s)))
    if m < 1 or m >= len(s):
        return float(s[0]), float(s[-1])
    i = int(np.argmin(s[m:] - s[: len(s) - m]))
    return float(s[i]), float(s[i + m])


def exact_prob_better(a: BinaryArm, b: BinaryArm, prior=(1.0, 1.0)) -> float:
    """P(p_b > p_a) by numerical integration of the exact Beta posteriors."""
    da = stats.beta(prior[0] + a.x, prior[1] + a.n - a.x)
    db = stats.beta(prior[0] + b.x, prior[1] + b.n - b.x)
    lo = max(0.0, min(da.ppf(1e-9), db.ppf(1e-9)))
    hi = min(1.0, max(da.ppf(1 - 1e-9), db.ppf(1 - 1e-9)))
    val, _ = integrate.quad(lambda x: da.pdf(x) * db.sf(x), lo, hi, limit=200)
    return float(val)


def _conjugate_draws(arms, prior, draws, seed) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return np.column_stack([
        rng.beta(prior[0] + a.x, prior[1] + a.n - a.x, draws) for a in arms
    ])


def _pymc_draws(arms, prior, draws, tune, chains, seed) -> tuple[np.ndarray, dict]:
    import arviz as az
    import pymc as pm

    ns = np.array([a.n for a in arms])
    xs = np.array([a.x for a in arms])
    with _PYMC_LOCK:
        with pm.Model():
            p = pm.Beta("p", alpha=prior[0], beta=prior[1], shape=len(arms))
            pm.Binomial("obs", n=ns, p=p, observed=xs)
            idata = pm.sample(
                draws=draws, tune=tune, chains=chains, cores=1, random_seed=seed,
                progressbar=False, compute_convergence_checks=False,
            )
    post = idata.posterior["p"].values  # (chain, draw, arm)
    summary = az.summary(idata, var_names=["p"], kind="diagnostics")
    diag = {
        "r_hat_max": float(np.nanmax(summary["r_hat"])),
        "ess_bulk_min": float(np.nanmin(summary["ess_bulk"])),
        "chains": chains,
        "divergences": int(idata.sample_stats["diverging"].sum()),
    }
    return post.reshape(-1, len(arms)), diag


# --------------------------------------------------------------------------- main API
def analyze_ab(
    arms: list[BinaryArm], control: int = 0, prior: tuple[float, float] = (1.0, 1.0),
    rope: float = 0.0, engine: str = "pymc", draws: int = 1000, tune: int = 500,
    chains: int = 4, seed: int | None = 42, hdi_prob: float = 0.95,
) -> dict:
    """Posterior summaries: P(variant beats control), expected lift, expected loss, ROPE."""
    if len(arms) < 2:
        raise ValueError("Need at least two arms.")
    if not (0 <= control < len(arms)):
        raise ValueError("control index out of range.")
    if prior[0] <= 0 or prior[1] <= 0:
        raise ValueError("Beta prior parameters must be positive.")
    if rope < 0:
        raise ValueError("rope must be >= 0.")
    if engine not in {"pymc", "conjugate"}:
        raise ValueError("engine must be 'pymc' or 'conjugate'.")

    t0 = time.perf_counter()
    diag: dict = {"engine": engine}
    if engine == "pymc":
        try:
            samples, d = _pymc_draws(arms, prior, draws, tune, chains, seed)
            diag.update(d)
        except ImportError:  # pragma: no cover - PyMC not installed
            engine = diag["engine"] = "conjugate"
            diag["note"] = "PyMC unavailable; used exact conjugate sampling."
            samples = _conjugate_draws(arms, prior, 20_000, seed)
    else:
        samples = _conjugate_draws(arms, prior, max(draws * chains, 20_000), seed)
    diag["n_draws"] = int(samples.shape[0])
    diag["seconds"] = round(time.perf_counter() - t0, 3)

    best = np.bincount(samples.argmax(axis=1), minlength=len(arms)) / len(samples)
    arm_out = []
    for i, a in enumerate(arms):
        lo, hi = hdi(samples[:, i], hdi_prob)
        arm_out.append({
            "name": a.name, "n": a.n, "x": a.x, "observed_rate": a.x / a.n,
            "posterior_mean": float(samples[:, i].mean()), "hdi_low": lo, "hdi_high": hi,
            "prob_best": float(best[i]),
        })

    pc = samples[:, control]
    comparisons, max_err = [], 0.0
    for i, a in enumerate(arms):
        if i == control:
            continue
        pt = samples[:, i]
        diff = pt - pc
        rel = pt / np.maximum(pc, 1e-12) - 1
        d_lo, d_hi = hdi(diff, hdi_prob)
        r_lo, r_hi = hdi(rel, hdi_prob)
        p_better = float((diff > 0).mean())
        exact = exact_prob_better(arms[control], a, prior)
        max_err = max(max_err, abs(p_better - exact))
        comp = {
            "variant": a.name, "control": arms[control].name,
            "prob_beats_control": p_better, "prob_beats_control_exact": exact,
            "expected_diff": float(diff.mean()), "diff_hdi_low": d_lo, "diff_hdi_high": d_hi,
            "expected_rel_lift": float(rel.mean()), "rel_hdi_low": r_lo, "rel_hdi_high": r_hi,
            "expected_loss_if_choose_variant": float(np.maximum(-diff, 0).mean()),
            "expected_loss_if_keep_control": float(np.maximum(diff, 0).mean()),
        }
        if rope > 0:
            comp["rope"] = rope
            comp["prob_in_rope"] = float((np.abs(diff) <= rope).mean())
            comp["prob_practically_better"] = float((diff > rope).mean())
            comp["prob_practically_worse"] = float((diff < -rope).mean())
        comp["diff_histogram"] = _histogram(diff)
        comparisons.append(comp)
    diag["max_abs_error_vs_exact"] = float(max_err)
    return {
        "prior": {"alpha": prior[0], "beta": prior[1]}, "hdi_prob": hdi_prob, "control": arms[control].name,
        "arms": arm_out, "comparisons": comparisons, "diagnostics": diag,
        "posterior_density": _densities(arms, prior),
    }


def _histogram(diff: np.ndarray, bins: int = 40) -> list[dict]:
    lo, hi = np.percentile(diff, [0.1, 99.9])
    counts, edges = np.histogram(diff, bins=bins, range=(lo, hi))
    dens = counts / (counts.sum() * np.diff(edges))
    return [{"x": float((edges[i] + edges[i + 1]) / 2), "density": float(dens[i])} for i in range(bins)]


def _densities(arms, prior, points: int = 120) -> list[dict]:
    """Exact Beta posterior pdfs on a common grid (for charting)."""
    dists = [stats.beta(prior[0] + a.x, prior[1] + a.n - a.x) for a in arms]
    lo = min(d.ppf(0.0005) for d in dists)
    hi = max(d.ppf(0.9995) for d in dists)
    grid = np.linspace(lo, hi, points)
    return [{"x": float(x), **{a.name: float(d.pdf(x)) for a, d in zip(arms, dists)}} for x in grid]


def warmup() -> None:
    """Pre-compile the PyMC model for 2 and 3 arms so the first user request is fast."""
    for k in (2, 3):
        arms = [BinaryArm(f"a{i}", 100, 10 + i) for i in range(k)]
        try:
            analyze_ab(arms, draws=50, tune=50, chains=1)
        except Exception:  # pragma: no cover - warm-up must never break start-up
            logging.getLogger(__name__).exception("PyMC warm-up failed")
