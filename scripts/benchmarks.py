"""Accuracy and performance benchmarks. Writes docs/benchmark_results.md and docs/benchmark_results.json.

Run:  python scripts/benchmarks.py [--quick]
Accuracy is measured against simulated data with a known truth; latency is measured through the HTTP layer.
"""
from __future__ import annotations

import json
import statistics
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.stats import bayes, power, simulate, tests  # noqa: E402
from app.stats.causal import difference_in_differences, propensity_score_matching, synthetic_control  # noqa: E402

QUICK = "--quick" in sys.argv
rng = np.random.default_rng(11)
R: dict = {}


def pct(x: float) -> str:
    return f"{100 * x:.1f}%"


# ------------------------------------------------------------------ classical tests
def classical() -> dict:
    sims = 1000 if QUICK else 3000
    out = {}
    # chi-square / two-proportion: null false-positive rate and CI coverage
    p0, n = 0.10, 2000
    rej, cover = 0, 0
    for _ in range(sims):
        r = tests.two_proportion_test(rng.binomial(n, p0), n, rng.binomial(n, p0), n, 0.05)
        rej += r.p_value < 0.05
    p1 = 0.12
    for _ in range(sims):
        r = tests.two_proportion_test(rng.binomial(n, p0), n, rng.binomial(n, p1), n, 0.05)
        cover += r.ci_low <= (p1 - p0) <= r.ci_high
    out["chi_square"] = {"false_positive_rate": rej / sims, "ci_coverage": cover / sims, "sims": sims}
    # Welch t-test
    rej, cover = 0, 0
    for _ in range(sims):
        a, b = rng.normal(0, 1, 60), rng.normal(0, 2.5, 90)  # unequal variance and size on purpose
        rej += tests.welch_t_test(a, b).p_value < 0.05
    for _ in range(sims):
        a, b = rng.normal(0, 1, 60), rng.normal(0.5, 2.5, 90)
        r = tests.welch_t_test(a, b)
        cover += r.ci_low <= 0.5 <= r.ci_high
    out["welch_t"] = {"false_positive_rate": rej / sims, "ci_coverage": cover / sims, "sims": sims}
    # power formula vs simulation
    n1, n2 = power.sample_size_proportions(0.10, 0.12)
    hit = sum(tests.two_proportion_test(rng.binomial(n1, 0.10), n1, rng.binomial(n2, 0.12), n2, 0.05).p_value < 0.05 for _ in range(sims))
    out["power_proportions"] = {"n_per_arm": int(n1), "target": 0.80, "simulated": hit / sims}
    return out


def multiple_and_sequential() -> dict:
    sims = 2000 if QUICK else 6000
    mt = simulate.simulate_multiple_testing(m=20, m_true=5, effect_z=3.0, sims=sims, seed=3)["methods"]
    pk = simulate.simulate_peeking(baseline=0.10, rel_lift=0.0, n_max=5000, n_looks=10, alpha=0.05, sims=2000 if QUICK else 5000, seed=3)["methods"]
    pk_alt = simulate.simulate_peeking(baseline=0.10, rel_lift=0.15, n_max=5000, n_looks=10, alpha=0.05, sims=2000 if QUICK else 5000, seed=4)["methods"]
    return {"multiple_testing": mt, "peeking_null": pk, "peeking_alt": pk_alt, "sims": sims}


# ------------------------------------------------------------------ Bayesian
def bayesian() -> dict:
    scen = [(1000, 100, 1000, 130), (500, 40, 500, 45), (20000, 2000, 20000, 2100), (300, 30, 300, 29), (5000, 250, 5000, 300)]
    diffs, secs = [], []
    for n1, x1, n2, x2 in scen:
        arms = [bayes.BinaryArm("control", n1, x1), bayes.BinaryArm("v", n2, x2)]
        t = time.perf_counter()
        pm = bayes.analyze_ab(arms, engine="pymc", draws=2000, chains=4, seed=1)
        secs.append(time.perf_counter() - t)
        c = pm["comparisons"][0]
        diffs.append(abs(c["prob_beats_control"] - c["prob_beats_control_exact"]))
    # frequentist-style calibration of the 95% credible interval for the difference (uniform prior)
    sims, cover = 1500 if QUICK else 4000, 0
    for _ in range(sims):
        pa, pb = rng.uniform(0.05, 0.3), rng.uniform(0.05, 0.3)
        arms = [bayes.BinaryArm("control", 800, rng.binomial(800, pa)), bayes.BinaryArm("v", 800, rng.binomial(800, pb))]
        c = bayes.analyze_ab(arms, engine="conjugate", draws=1000, seed=int(rng.integers(1e6)))["comparisons"][0]
        cover += c["diff_hdi_low"] <= pb - pa <= c["diff_hdi_high"]
    return {"max_abs_diff_pymc_vs_exact": max(diffs), "pymc_seconds_median": statistics.median(secs), "hdi_coverage": cover / sims, "hdi_sims": sims}


# ------------------------------------------------------------------ causal
def causal() -> dict:
    k = 6 if QUICK else 15
    psm_est, psm_naive, psm_cov = [], [], 0
    for s in range(k):
        df = simulate.simulate_observational(n=3000, true_effect=2.0, confounding=1.5, seed=100 + s)
        r = propensity_score_matching(df, "treated", "outcome", ["age", "income", "engagement", "plan"], n_boot=60, cross_check=False, seed=s)
        psm_est.append(r["estimate"]); psm_naive.append(r["naive_difference"]); psm_cov += r["ci_low"] <= 2.0 <= r["ci_high"]
    did_est, did_cov, sc_est, sc_sig = [], 0, [], 0
    for s in range(k):
        pn = simulate.simulate_panel(true_effect=5.0, seed=200 + s)
        cut = pn["date"].min() + pd.Timedelta(weeks=28)
        d = difference_in_differences(pn, "outcome", "group", "treated", "date", cut, unit_col="unit", cross_check=False)
        did_est.append(d["estimate"]); did_cov += d["ci_low"] <= 5.0 <= d["ci_high"]
        units = sorted(pn.loc[pn.group == "treated", "unit"].unique())
        sc = synthetic_control(pn, "outcome", "unit", "date", units, cut)
        sc_est.append(sc["estimate"]); sc_sig += sc["p_value"] < 0.05
    f = lambda v, t: {"mean": float(np.mean(v)), "bias": float(np.mean(v) - t), "rmse": float(np.sqrt(np.mean((np.array(v) - t) ** 2)))}
    return {"runs": k, "psm": {**f(psm_est, 2.0), "naive_mean": float(np.mean(psm_naive)), "ci_coverage": psm_cov / k},
            "did": {**f(did_est, 5.0), "ci_coverage": did_cov / k}, "synthetic": {**f(sc_est, 5.0), "placebo_p_below_0.05": sc_sig / k}}


# ------------------------------------------------------------------ latency
def pymc_cold_start() -> dict:
    """First PyMC request in a fresh process: includes importing PyMC and compiling the model."""
    import subprocess

    code = (
        "import sys,time,warnings; warnings.filterwarnings('ignore'); sys.path.insert(0,'backend')\n"
        "t=time.perf_counter()\n"
        "from app.stats import bayes\n"
        "t_import=time.perf_counter()-t\n"
        "t=time.perf_counter(); bayes.analyze_ab([bayes.BinaryArm('control',1000,100),bayes.BinaryArm('v',1000,130)],engine='pymc',draws=1000,chains=4,seed=1)\n"
        "t_first=time.perf_counter()-t\n"
        "t=time.perf_counter(); bayes.analyze_ab([bayes.BinaryArm('control',900,90),bayes.BinaryArm('v',900,100)],engine='pymc',draws=1000,chains=4,seed=1)\n"
        "print(t_import, t_first, time.perf_counter()-t)\n"
    )
    res = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=600)
    a, b, c = (float(x) for x in res.stdout.strip().splitlines()[-1].split())
    return {"import_s": a, "first_request_s": b, "second_request_s": c}


def latency() -> dict:
    c = TestClient(app)
    s = c.post("/api/samples/ab_test_sessions").json()
    lid = s["meta"]["labels_id"]
    ob = c.post("/api/datasets/simulate", json={"scenario": "observational", "n": 3000}).json()
    pn = c.post("/api/datasets/simulate", json={"scenario": "panel", "true_effect": 5}).json()
    cut = pn["meta"]["suggested"]["cutoff"]
    cases = {
        "power / sample-size": ("/api/power/proportions/sample-size", {"baseline": 0.1, "mde": 0.02}),
        "chi-square (summary)": ("/api/tests/chi-square", {"x_control": 100, "n_control": 1000, "x_treatment": 130, "n_treatment": 1000}),
        "frequentist, 4 tests / 15k rows": ("/api/analyze/frequentist", {"dataset_id": s["id"], "labels_id": lid, "outcome": "converted", "variant_columns": s["suggestions"]["variant_columns"]}),
        "sequential, 10 looks / 15k rows": ("/api/analyze/sequential", {"dataset_id": s["id"], "variant_column": "icon_design_variant", "outcome": "converted", "time_column": "session_date"}),
        "Bayesian, closed form": ("/api/analyze/bayesian", {"dataset_id": s["id"], "outcome": "converted", "variant_columns": ["icon_design_variant"], "engine": "conjugate"}),
        "Bayesian, PyMC (4 chains)": ("/api/analyze/bayesian", {"dataset_id": s["id"], "outcome": "converted", "variant_columns": ["icon_design_variant"], "engine": "pymc"}),
        "PSM, n=3000, 100 bootstraps": ("/api/analyze/psm", {"dataset_id": ob["id"], "treatment": "treated", "outcome": "outcome", "covariates": ["age", "income", "engagement", "plan"], "cross_check": False}),
        "PSM + DoWhy + EconML cross-checks": ("/api/analyze/psm", {"dataset_id": ob["id"], "treatment": "treated", "outcome": "outcome", "covariates": ["age", "income", "engagement", "plan"], "cross_check": True}),
        "difference-in-differences + DoWhy": ("/api/analyze/did", {"dataset_id": pn["id"], "outcome": "outcome", "group_col": "group", "treated_value": "treated", "time_col": "date", "cutoff": cut, "unit_col": "unit"}),
        "synthetic control, 25 placebos": ("/api/analyze/synthetic-control", {"dataset_id": pn["id"], "outcome": "outcome", "unit_col": "unit", "time_col": "date", "intervention": cut, "group_col": "group", "treated_value": "treated"}),
    }
    out = {}
    for name, (path, body) in cases.items():
        times = []
        for i in range(1 if "PyMC" in name or "DoWhy" in name else 5):
            t = time.perf_counter(); r = c.post(path, json=body); times.append((time.perf_counter() - t) * 1000)
            assert r.status_code == 200, (name, r.text[:200])
        out[name] = {"median_ms": statistics.median(times), "runs": len(times)}
    out["_pymc_cold"] = pymc_cold_start()
    # throughput of a light endpoint
    t = time.perf_counter()
    for _ in range(200):
        c.post("/api/power/proportions/sample-size", json={"baseline": 0.1, "mde": 0.02})
    out["_light_endpoint_rps"] = 200 / (time.perf_counter() - t)
    return out


def main() -> None:
    if "--md-only" in sys.argv:  # re-render the report from the saved JSON
        R.update(json.loads((ROOT / "docs" / "benchmark_results.json").read_text()))
        return write_md()
    steps = [("classical", classical), ("sequential_multiple", multiple_and_sequential), ("bayesian", bayesian), ("causal", causal), ("latency", latency)]
    for name, fn in steps:
        t = time.perf_counter(); R[name] = fn(); print(f"{name:22s} {time.perf_counter() - t:6.1f}s", flush=True)
    (ROOT / "docs" / "benchmark_results.json").write_text(json.dumps(R, indent=2, default=float))
    write_md()


def write_md() -> None:
    c, s, b, k, l = R["classical"], R["sequential_multiple"], R["bayesian"], R["causal"], R["latency"]
    L = ["# Benchmark results", "", f"Generated by `scripts/benchmarks.py{' --quick' if QUICK else ''}` on a single CPU core. Accuracy figures come from simulated data with a known truth.", "",
         "## Classical tests", "", "| Check | Expected | Measured |", "|---|---|---|",
         f"| Chi-square false-positive rate under H0 ({c['chi_square']['sims']:,} sims) | 5.0% | {pct(c['chi_square']['false_positive_rate'])} |",
         f"| Chi-square 95% CI coverage | 95.0% | {pct(c['chi_square']['ci_coverage'])} |",
         f"| Welch t-test false-positive rate, unequal variances and sizes | 5.0% | {pct(c['welch_t']['false_positive_rate'])} |",
         f"| Welch 95% CI coverage | 95.0% | {pct(c['welch_t']['ci_coverage'])} |",
         f"| Power at the planned n ({c['power_proportions']['n_per_arm']:,}/arm, 10% to 12%) | 80.0% | {pct(c['power_proportions']['simulated'])} |", "",
         f"## Multiple testing (20 metrics, 5 truly affected, {s['sims']:,} sims)", "", "| Method | FWER | FDR | Power |", "|---|---|---|---|"]
    names = {"none": "No correction", "bonferroni": "Bonferroni", "holm": "Holm", "bh": "Benjamini-Hochberg"}
    for key, v in s["multiple_testing"].items():
        L.append(f"| {names[key]} | {pct(v['fwer'])} | {pct(v['fdr'])} | {pct(v['power'])} |")
    L += ["", "## Peeking (10 looks, alpha = 5%)", "", "| Rule | False positives (no effect) | Power (+15% lift) | Avg. sample used (lift) |", "|---|---|---|---|"]
    pn = {"fixed_horizon": "Test once at the end", "naive_peeking": "Peek, stop at first p < 0.05", "group_sequential": "Group-sequential (O'Brien-Fleming)", "msprt": "Always-valid mSPRT"}
    for key, v in s["peeking_null"].items():
        a = s["peeking_alt"][key]
        L.append(f"| {pn[key]} | {pct(v['reject_rate'])} | {pct(a['reject_rate'])} | {pct(a['avg_sample_fraction'])} |")
    L += ["", "Reading the peeking table: naive peeking looks powerful only because it cheats (4x the promised false-positive rate). Group-sequential keeps the 5% guarantee at nearly the fixed-horizon power. "
          "The always-valid mSPRT is valid at *any* stopping time without a pre-planned schedule, but pays for that flexibility with much lower power; prefer group-sequential when a maximum sample size is known.",
          "", "## Bayesian A/B", "", "| Check | Result |", "|---|---|",
          f"| Max |P(B>A)| gap, PyMC (4 chains x 2,000 draws) vs exact integral, 5 scenarios | {b['max_abs_diff_pymc_vs_exact']:.4f} |",
          f"| 95% credible-interval coverage of the true difference ({b['hdi_sims']:,} random worlds) | {pct(b['hdi_coverage'])} |",
          f"| PyMC sampling time per two-arm model (median) | {b['pymc_seconds_median']:.2f} s |", "",
          f"## Observational methods ({k['runs']} independent datasets each)", "", "| Method | True effect | Mean estimate | Bias | RMSE | CI coverage / detection |", "|---|---|---|---|---|---|",
          f"| Raw difference (no adjustment) | 2.0 | {k['psm']['naive_mean']:.2f} | {k['psm']['naive_mean'] - 2:+.2f} | n/a | n/a |",
          f"| Propensity-score matching | 2.0 | {k['psm']['mean']:.2f} | {k['psm']['bias']:+.2f} | {k['psm']['rmse']:.2f} | CI covers truth in {round(k['psm']['ci_coverage'] * k['runs'])}/{k['runs']} runs |",
          f"| Difference-in-differences | 5.0 | {k['did']['mean']:.2f} | {k['did']['bias']:+.2f} | {k['did']['rmse']:.2f} | CI covers truth in {round(k['did']['ci_coverage'] * k['runs'])}/{k['runs']} runs |",
          f"| Synthetic control | 5.0 | {k['synthetic']['mean']:.2f} | {k['synthetic']['bias']:+.2f} | {k['synthetic']['rmse']:.2f} | placebo p < 0.05 in {round(k['synthetic']['placebo_p_below_0.05'] * k['runs'])}/{k['runs']} runs |", "",
          "", f"With only {k['runs']} datasets per method, coverage figures are coarse; the point is that bias is small relative to the effect and the raw difference is badly wrong.",
          "", "## API latency (through the HTTP layer, in-process client)", "", "| Operation | Median |", "|---|---|"]
    for name, v in l.items():
        if name.startswith("_"):
            continue
        L.append(f"| {name} | {v['median_ms']:.0f} ms |")
    cold = l["_pymc_cold"]
    L += ["", f"**PyMC cold start** (fresh process): importing PyMC takes {cold['import_s']:.0f} s, the first model costs {cold['first_request_s']:.1f} s (graph compilation), and later models take {cold['second_request_s']:.1f} s. "
          "Set `ABLAB_WARMUP_PYMC=true` to pay this at server start instead of on the first user request; the closed-form engine answers in milliseconds.",
          "", f"A light endpoint (sample-size calculation) sustains about {l['_light_endpoint_rps']:.0f} requests per second per core."]
    (ROOT / "docs" / "benchmark_results.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
