import numpy as np
import pytest
from scipy import stats

from app.stats import bayes as bz

ARMS = [bz.BinaryArm("control", 5026, 1023), bz.BinaryArm("variant_a", 4957, 1148), bz.BinaryArm("variant_b", 5017, 1215)]


def test_hdi_of_normal():
    x = np.random.default_rng(0).normal(0, 1, 200_000)
    lo, hi = bz.hdi(x, 0.95)
    assert lo == pytest.approx(-1.96, abs=0.03) and hi == pytest.approx(1.96, abs=0.03)


def test_exact_probability_matches_known_case():
    a, b = bz.BinaryArm("a", 100, 50), bz.BinaryArm("b", 100, 50)
    assert bz.exact_prob_better(a, b) == pytest.approx(0.5, abs=1e-6)
    assert bz.exact_prob_better(bz.BinaryArm("a", 1000, 100), bz.BinaryArm("b", 1000, 150)) > 0.999


def test_conjugate_engine_structure_and_consistency():
    r = bz.analyze_ab(ARMS, engine="conjugate", rope=0.005, seed=1)
    assert [a["name"] for a in r["arms"]] == ["control", "variant_a", "variant_b"]
    assert sum(a["prob_best"] for a in r["arms"]) == pytest.approx(1.0)
    c = r["comparisons"][0]
    assert 0 <= c["prob_beats_control"] <= 1
    assert c["prob_beats_control"] == pytest.approx(c["prob_beats_control_exact"], abs=0.01)
    assert c["diff_hdi_low"] < c["expected_diff"] < c["diff_hdi_high"]
    assert c["prob_in_rope"] + c["prob_practically_better"] + c["prob_practically_worse"] == pytest.approx(1.0)
    assert len(c["diff_histogram"]) == 40 and len(r["posterior_density"]) == 120


def test_no_difference_gives_near_half():
    r = bz.analyze_ab([bz.BinaryArm("a", 4000, 800), bz.BinaryArm("b", 4000, 800)], engine="conjugate", draws=50_000)
    assert r["comparisons"][0]["prob_beats_control"] == pytest.approx(0.5, abs=0.01)


def test_posterior_mean_is_beta_mean():
    r = bz.analyze_ab(ARMS, engine="conjugate", prior=(2, 5), draws=100_000)
    a = ARMS[0]
    assert r["arms"][0]["posterior_mean"] == pytest.approx((2 + a.x) / (7 + a.n), abs=1e-4)


def test_validation():
    with pytest.raises(ValueError):
        bz.BinaryArm("bad", 10, 11)
    with pytest.raises(ValueError):
        bz.analyze_ab(ARMS[:1])
    with pytest.raises(ValueError):
        bz.analyze_ab(ARMS, engine="gibbs")
    with pytest.raises(ValueError):
        bz.analyze_ab(ARMS, control=7)


@pytest.mark.slow
def test_pymc_agrees_with_exact_posterior():
    r = bz.analyze_ab(ARMS, engine="pymc", seed=7)
    d = r["diagnostics"]
    assert d["r_hat_max"] < 1.01 and d["ess_bulk_min"] > 1000 and d["divergences"] == 0
    for c in r["comparisons"]:
        assert c["prob_beats_control"] == pytest.approx(c["prob_beats_control_exact"], abs=0.01)
    close = bz.analyze_ab([bz.BinaryArm("a", 1000, 100), bz.BinaryArm("b", 1000, 115)], engine="pymc", seed=3)
    c = close["comparisons"][0]
    assert c["prob_beats_control"] == pytest.approx(c["prob_beats_control_exact"], abs=0.015)
    assert 0.8 < c["prob_beats_control"] < 0.95
    assert r["arms"][0]["posterior_mean"] == pytest.approx(stats.beta(1 + 1023, 1 + 5026 - 1023).mean(), abs=5e-4)
