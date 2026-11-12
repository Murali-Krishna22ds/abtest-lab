import numpy as np
import pandas as pd
import pytest

from app.stats import simulate as sim
from app.stats.causal import difference_in_differences as did
from app.stats.causal import propensity_score_matching as psm
from app.stats.causal import synthetic_control as sc

COVS = ["age", "income", "engagement", "plan"]


@pytest.fixture(scope="module")
def obs():
    return sim.simulate_observational(n=6000, true_effect=2.0, seed=11)


@pytest.mark.slow
def test_psm_removes_confounding_bias(obs):
    r = psm(obs, "treated", "outcome", COVS, n_boot=40, seed=0)
    assert r["naive_difference"] > 5            # badly biased
    assert r["ci_low"] <= 2.0 <= r["ci_high"]   # truth inside the CI
    assert abs(r["estimate"] - 2.0) < 0.6
    assert r["balance_ok"] and r["max_abs_smd_after"] < 0.1
    assert max(abs(b["smd_before"]) for b in r["balance"]) > 0.3  # imbalance existed before matching
    assert r["cross_checks"]["econml_dr"]["ci_low"] < 2.0 < r["cross_checks"]["econml_dr"]["ci_high"]
    assert abs(r["cross_checks"]["dowhy_psm"]["estimate"] - 2.0) < 1.2


def test_psm_no_confounding_recovers_naive(obs):
    d = sim.simulate_observational(n=4000, true_effect=2.0, confounding=0.0, seed=5)
    r = psm(d, "treated", "outcome", COVS, n_boot=30, cross_check=False)
    assert r["ci_low"] <= 2.0 <= r["ci_high"]
    assert abs(r["estimate"] - r["naive_difference"]) < 0.7


def test_psm_input_validation(obs):
    with pytest.raises(ValueError):
        psm(obs, "treated", "outcome", [])
    with pytest.raises(ValueError):
        psm(obs, "treated", "outcome", ["treated"])
    with pytest.raises(ValueError):
        psm(obs, "treated", "nope", COVS)
    with pytest.raises(ValueError):
        psm(obs.head(30), "treated", "outcome", COVS)


def test_psm_treated_value_for_categorical(obs):
    d = obs.assign(arm=np.where(obs.treated == 1, "new", "old")).drop(columns="treated")
    r = psm(d, "arm", "outcome", COVS, treated_value="new", n_boot=20, cross_check=False)
    assert r["n_treated"] == int((obs.treated == 1).sum())
    with pytest.raises(ValueError):
        psm(d, "arm", "outcome", COVS, n_boot=20)  # which level is treated?


@pytest.fixture(scope="module")
def panel():
    return sim.simulate_panel(n_units=30, n_periods=40, n_treated=5, intervention_period=28, true_effect=5.0, seed=2)


def test_did_recovers_effect_and_matches_dowhy(panel):
    cut = panel.date.min() + pd.Timedelta(weeks=28)
    r = did(panel, "outcome", "group", "treated", "date", cut, unit_col="unit")
    assert r["ci_low"] <= 5.0 <= r["ci_high"]
    assert r["se_type"] == "cluster-robust"
    assert r["cross_check"]["estimate"] == pytest.approx(r["estimate"], abs=1e-6)
    assert r["pre_trend"]["p_value"] > 0.05
    assert r["means"]["treated_change"] - r["means"]["control_change"] == pytest.approx(r["estimate"], abs=1e-6)
    assert r["ref_x"] == "2026-07-20" and any(row["counterfactual"] is not None for row in r["series"])


def test_did_exact_on_toy_data():
    rows = []
    for g, base in (("t", 10), ("c", 5)):
        for post in (0, 1):
            for i in range(10):
                rows.append({"g": g, "time": post, "y": base + 2 * post + (3 if (g == "t" and post) else 0)})
    r = did(pd.DataFrame(rows), "y", "g", "t", "time", 1)
    assert r["estimate"] == pytest.approx(3.0)


def test_did_flags_violated_parallel_trends():
    rng = np.random.default_rng(0)
    rows = [{"g": g, "time": t, "y": (0.0 if g == "c" else 1.5) * t + rng.normal(0, 0.5)}
            for g in ("t", "c") for t in range(20) for _ in range(5)]
    r = did(pd.DataFrame(rows), "y", "g", "t", "time", 10)
    assert r["pre_trend"]["p_value"] < 0.001


def test_did_validation(panel):
    with pytest.raises(ValueError):
        did(panel, "outcome", "group", "nobody", "date", "2026-07-20")
    with pytest.raises(ValueError):
        did(panel, "outcome", "group", "treated", "unit", 3)


def test_synthetic_control_recovers_effect_with_placebo_inference(panel):
    cut = panel.date.min() + pd.Timedelta(weeks=28)
    units = sorted(panel[panel.group == "treated"].unit.unique())
    r = sc(panel, "outcome", "unit", "date", units, cut)
    assert abs(r["estimate"] - 5.0) < 1.5
    assert r["pre_fit_ratio"] < 0.3
    assert r["p_value"] == pytest.approx(1 / 26)  # treated is the most extreme of 26 units
    assert sum(w["weight"] for w in r["weights"]) <= 1.0 + 1e-9 and r["weights"][0]["weight"] >= r["weights"][-1]["weight"]
    assert len(r["series"]) == 40 and r["n_placebo_lines"] > 0


def test_synthetic_control_null_effect_not_significant():
    p = sim.simulate_panel(n_units=30, n_periods=40, n_treated=3, intervention_period=28, true_effect=0.0, seed=8)
    units = sorted(p[p.group == "treated"].unit.unique())
    r = sc(p, "outcome", "unit", "date", units, p.date.min() + pd.Timedelta(weeks=28))
    assert r["p_value"] > 0.05 and abs(r["estimate"]) < 2.0


def test_synthetic_control_few_donors_caveat_and_validation(panel):
    small = panel[panel.unit.isin(["U01", "U10", "U11", "U12", "U13"])]
    r = sc(small, "outcome", "unit", "date", ["U01"], panel.date.min() + pd.Timedelta(weeks=28))
    assert any("smallest attainable p-value" in c for c in r["caveats"])
    with pytest.raises(ValueError):
        sc(panel, "outcome", "unit", "date", ["ZZZ"], "2026-07-20")
    with pytest.raises(ValueError):
        sc(panel, "outcome", "unit", "date", ["U01"], "2026-01-06")  # too few pre periods
    with pytest.raises(ValueError):
        sc(panel, "outcome", "unit", "date", ["U01"], "2030-01-01")  # no post periods
